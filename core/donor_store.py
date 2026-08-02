import csv
import io
import json
import os
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import sys
PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))
from safe_json import load_json as _robust_load_json, save_json as _robust_save_json

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PROFILES_FILE = DATA_DIR / "donor_profiles.json"
ADJUSTMENTS_FILE = DATA_DIR / "donor_adjustments.json"
LOCK = threading.RLock()
TOP_CURRENCY = "RUB"


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load(path, fallback):
    return _robust_load_json(path, fallback, retries=16)


def _save(path, data):
    _robust_save_json(path, data, retries=120)


def ensure_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROFILES_FILE.exists():
        _save(PROFILES_FILE, [])
    if not ADJUSTMENTS_FILE.exists():
        _save(ADJUSTMENTS_FILE, [])


def normalize_name(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"\s+", " ", text)


def normalize_source(value):
    return str(value or "unknown").strip().lower() or "unknown"


def alias_key(source, username):
    return f"{normalize_source(source)}|{normalize_name(username)}"


def _normalize_alias(alias):
    if not isinstance(alias, dict):
        return None
    source = normalize_source(alias.get("source"))
    username = str(alias.get("username") or alias.get("name") or "").strip()
    normalized = normalize_name(username)
    if not normalized:
        return None
    return {"source": source, "username": username or normalized, "normalized": normalized}


def _normalize_profile(profile):
    if not isinstance(profile, dict):
        profile = {}
    aliases = []
    seen = set()
    for alias in profile.get("aliases", []):
        item = _normalize_alias(alias)
        if not item:
            continue
        key = alias_key(item["source"], item["username"])
        if key in seen:
            continue
        seen.add(key)
        aliases.append(item)

    display_name = str(profile.get("displayName") or "").strip()
    if not display_name and aliases:
        display_name = aliases[0]["username"]
    if not display_name:
        display_name = "Без имени"

    return {
        "id": str(profile.get("id") or f"donor-{uuid.uuid4()}"),
        "displayName": display_name,
        "aliases": aliases,
        "note": str(profile.get("note") or ""),
        "pinned": bool(profile.get("pinned", False)),
        "pinOrder": int(profile.get("pinOrder") or 0),
        "excludedFromTop": bool(profile.get("excludedFromTop", False)),
        "createdAt": str(profile.get("createdAt") or now_iso()),
        "updatedAt": str(profile.get("updatedAt") or now_iso()),
    }


def load_profiles():
    ensure_files()
    raw = _load(PROFILES_FILE, [])
    if not isinstance(raw, list):
        raw = []
    result = []
    ids = set()
    for item in raw:
        profile = _normalize_profile(item)
        if profile["id"] in ids:
            profile["id"] = f"donor-{uuid.uuid4()}"
        ids.add(profile["id"])
        result.append(profile)
    return result


def save_profiles(profiles):
    with LOCK:
        _save(PROFILES_FILE, [_normalize_profile(item) for item in profiles if isinstance(item, dict)])


def load_adjustments():
    ensure_files()
    raw = _load(ADJUSTMENTS_FILE, [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            amount = float(item.get("amount") or 0)
        except Exception:
            amount = 0
        try:
            amount_for_top = float(item.get("amountForTop") if item.get("amountForTop") is not None else amount)
        except Exception:
            amount_for_top = amount
        result.append({
            "id": str(item.get("id") or f"adjustment-{uuid.uuid4()}"),
            "donorId": str(item.get("donorId") or ""),
            "amount": round(amount, 2),
            "currency": str(item.get("currency") or TOP_CURRENCY).upper(),
            "amountForTop": round(amount_for_top, 2),
            "topCurrency": str(item.get("topCurrency") or TOP_CURRENCY).upper(),
            "note": str(item.get("note") or item.get("reason") or ""),
            "createdAt": str(item.get("createdAt") or now_iso()),
        })
    return result


def save_adjustments(adjustments):
    with LOCK:
        _save(ADJUSTMENTS_FILE, adjustments)


def _profile_maps(profiles):
    by_id = {item["id"]: item for item in profiles}
    by_alias = {}
    for profile in profiles:
        for alias in profile.get("aliases", []):
            by_alias[alias_key(alias.get("source"), alias.get("username"))] = profile["id"]
    return by_id, by_alias


def sync_donations(donations):
    """Назначает donorId по паре source+username. Между разными сервисами ники не объединяются автоматически."""
    with LOCK:
        profiles = load_profiles()
        by_id, by_alias = _profile_maps(profiles)
        changed = False

        for donation in donations:
            if not isinstance(donation, dict):
                continue
            source = normalize_source(donation.get("source"))
            username = str(donation.get("username") or "Аноним").strip() or "Аноним"
            key = alias_key(source, username)
            donor_id = str(donation.get("donorId") or "")
            profile = by_id.get(donor_id)

            if profile is None:
                donor_id = by_alias.get(key, "")
                profile = by_id.get(donor_id)

            if profile is None:
                deterministic = uuid.uuid5(uuid.NAMESPACE_URL, f"vicdonationgoal:{key}").hex[:20]
                donor_id = f"donor-{deterministic}"
                while donor_id in by_id:
                    donor_id = f"donor-{uuid.uuid4()}"
                profile = _normalize_profile({
                    "id": donor_id,
                    "displayName": username,
                    "aliases": [{"source": source, "username": username}],
                })
                profiles.append(profile)
                by_id[donor_id] = profile
                by_alias[key] = donor_id
                changed = True
            elif key not in by_alias:
                alias = _normalize_alias({"source": source, "username": username})
                if alias:
                    profile["aliases"].append(alias)
                    profile["updatedAt"] = now_iso()
                    by_alias[key] = donor_id
                    changed = True

            if donation.get("donorId") != donor_id:
                donation["donorId"] = donor_id
                changed = True

        if changed:
            save_profiles(profiles)
        return donations, profiles


def _donations_for_profile(profile_id, donations, profiles=None):
    profiles = profiles or load_profiles()
    by_id, _ = _profile_maps(profiles)
    profile = by_id.get(str(profile_id))
    if not profile:
        return []
    alias_keys = {alias_key(a.get("source"), a.get("username")) for a in profile.get("aliases", [])}
    result = []
    for donation in donations:
        if not isinstance(donation, dict):
            continue
        if str(donation.get("donorId") or "") == profile["id"]:
            result.append(donation)
            continue
        if alias_key(donation.get("source"), donation.get("username")) in alias_keys:
            result.append(donation)
    return result


def _summary(profile, donations, adjustments):
    included = [d for d in donations if bool(d.get("includeInTop", True))]
    donation_total = round(sum(float(d.get("amountForTop") if d.get("amountForTop") is not None else d.get("amountForGoal") or 0) for d in included), 2)
    own_adjustments = [a for a in adjustments if a.get("donorId") == profile["id"]]
    adjustment_total = round(sum(float(a.get("amountForTop") or 0) for a in own_adjustments), 2)
    dates = [str(d.get("receivedAt") or d.get("createdAt") or "") for d in included if d.get("receivedAt") or d.get("createdAt")]
    total = round(donation_total + adjustment_total, 2)
    return {
        "id": profile["id"],
        "displayName": profile["displayName"],
        "aliases": profile.get("aliases", []),
        "note": profile.get("note", ""),
        "pinned": bool(profile.get("pinned")),
        "pinOrder": int(profile.get("pinOrder") or 0),
        "excludedFromTop": bool(profile.get("excludedFromTop")),
        "donationTotal": donation_total,
        "adjustmentTotal": adjustment_total,
        "total": total,
        "currency": TOP_CURRENCY,
        "donationCount": len(included),
        "allDonationCount": len(donations),
        "adjustmentCount": len(own_adjustments),
        "firstDonationAt": min(dates) if dates else "",
        "lastDonationAt": max(dates) if dates else "",
    }


def build_top(donations, query=""):
    with LOCK:
        donations, profiles = sync_donations(donations)
        adjustments = load_adjustments()
        query_norm = normalize_name(query)
        pinned = []
        ranking = []
        excluded = []

        for profile in profiles:
            own = _donations_for_profile(profile["id"], donations, profiles)
            own_adjustments = [a for a in adjustments if a.get("donorId") == profile["id"]]
            if not own and not own_adjustments:
                continue
            summary = _summary(profile, own, adjustments)
            if summary["donationCount"] == 0 and summary["adjustmentCount"] == 0:
                continue

            if query_norm:
                haystack = [profile.get("displayName", ""), profile.get("note", "")]
                haystack.extend(alias.get("username", "") for alias in profile.get("aliases", []))
                haystack.extend(str(item.get("message") or "") for item in own)
                if query_norm not in normalize_name(" ".join(haystack)):
                    continue

            if summary["excludedFromTop"]:
                excluded.append(summary)
            elif summary["pinned"]:
                pinned.append(summary)
            else:
                ranking.append(summary)

        pinned.sort(key=lambda item: (item.get("pinOrder", 0), -item["total"], normalize_name(item["displayName"])))
        ranking.sort(key=lambda item: (-item["total"], -item["donationCount"], normalize_name(item["displayName"])))
        excluded.sort(key=lambda item: normalize_name(item["displayName"]))
        for index, item in enumerate(ranking, 1):
            item["rank"] = index
        return {
            "currency": TOP_CURRENCY,
            "pinned": pinned,
            "ranking": ranking,
            "excluded": excluded,
            "counts": {
                "pinned": len(pinned),
                "ranking": len(ranking),
                "excluded": len(excluded),
                "totalProfiles": len(pinned) + len(ranking) + len(excluded),
            },
            "grandTotal": round(sum(item["total"] for item in pinned + ranking), 2),
        }


def get_detail(profile_id, donations):
    with LOCK:
        donations, profiles = sync_donations(donations)
        profile = next((item for item in profiles if item["id"] == str(profile_id)), None)
        if not profile:
            return None
        own = _donations_for_profile(profile["id"], donations, profiles)
        adjustments = load_adjustments()
        own_adjustments = [item for item in adjustments if item.get("donorId") == profile["id"]]
        summary = _summary(profile, own, adjustments)
        timeline = []
        for item in own:
            timeline.append({
                "type": "donation",
                "id": str(item.get("uniqueKey") or ""),
                "date": str(item.get("receivedAt") or item.get("createdAt") or ""),
                "source": str(item.get("source") or ""),
                "username": str(item.get("username") or "Аноним"),
                "amount": float(item.get("amount") or 0),
                "currency": str(item.get("currency") or TOP_CURRENCY),
                "amountForTop": float(item.get("amountForTop") if item.get("amountForTop") is not None else item.get("amountForGoal") or 0),
                "topCurrency": TOP_CURRENCY,
                "message": str(item.get("message") or ""),
                "includeInTop": bool(item.get("includeInTop", True)),
                "uniqueKey": str(item.get("uniqueKey") or ""),
            })
        for item in own_adjustments:
            timeline.append({
                "type": "adjustment",
                "id": item["id"],
                "date": item.get("createdAt", ""),
                "amount": float(item.get("amount") or 0),
                "currency": item.get("currency", TOP_CURRENCY),
                "amountForTop": float(item.get("amountForTop") or 0),
                "topCurrency": TOP_CURRENCY,
                "message": item.get("note", ""),
            })
        timeline.sort(key=lambda item: item.get("date") or "", reverse=True)
        return {"profile": profile, "summary": summary, "timeline": timeline}


def update_profile(profile_id, patch):
    with LOCK:
        profiles = load_profiles()
        profile = next((item for item in profiles if item["id"] == str(profile_id)), None)
        if not profile:
            return None
        if "displayName" in patch:
            value = str(patch.get("displayName") or "").strip()
            if value:
                profile["displayName"] = value
        if "note" in patch:
            profile["note"] = str(patch.get("note") or "")
        if "pinned" in patch:
            profile["pinned"] = bool(patch.get("pinned"))
        if "pinOrder" in patch:
            try:
                profile["pinOrder"] = int(patch.get("pinOrder") or 0)
            except Exception:
                profile["pinOrder"] = 0
        if "excludedFromTop" in patch:
            profile["excludedFromTop"] = bool(patch.get("excludedFromTop"))
        profile["updatedAt"] = now_iso()
        save_profiles(profiles)
        return profile


def add_adjustment(profile_id, amount, currency, amount_for_top, note="", created_at=""):
    with LOCK:
        profiles = load_profiles()
        if not any(item["id"] == str(profile_id) for item in profiles):
            return None
        adjustments = load_adjustments()
        item = {
            "id": f"adjustment-{uuid.uuid4()}",
            "donorId": str(profile_id),
            "amount": round(float(amount), 2),
            "currency": str(currency or TOP_CURRENCY).upper(),
            "amountForTop": round(float(amount_for_top), 2),
            "topCurrency": TOP_CURRENCY,
            "note": str(note or ""),
            "createdAt": str(created_at or now_iso()),
        }
        adjustments.append(item)
        save_adjustments(adjustments)
        return item


def delete_adjustment(adjustment_id):
    with LOCK:
        adjustments = load_adjustments()
        kept = [item for item in adjustments if item.get("id") != str(adjustment_id)]
        if len(kept) == len(adjustments):
            return False
        save_adjustments(kept)
        return True


def merge_profiles(target_id, source_id, donations):
    with LOCK:
        if str(target_id) == str(source_id):
            return donations, None
        profiles = load_profiles()
        target = next((item for item in profiles if item["id"] == str(target_id)), None)
        source = next((item for item in profiles if item["id"] == str(source_id)), None)
        if not target or not source:
            return donations, None

        existing = {alias_key(a.get("source"), a.get("username")) for a in target.get("aliases", [])}
        for alias in source.get("aliases", []):
            key = alias_key(alias.get("source"), alias.get("username"))
            if key not in existing:
                target["aliases"].append(alias)
                existing.add(key)
        if not target.get("note") and source.get("note"):
            target["note"] = source.get("note")
        target["pinned"] = bool(target.get("pinned") or source.get("pinned"))
        target["updatedAt"] = now_iso()
        profiles = [item for item in profiles if item["id"] != source["id"]]
        save_profiles(profiles)

        for donation in donations:
            if donation.get("donorId") == source["id"]:
                donation["donorId"] = target["id"]
        adjustments = load_adjustments()
        for item in adjustments:
            if item.get("donorId") == source["id"]:
                item["donorId"] = target["id"]
        save_adjustments(adjustments)
        return donations, target


def delete_all_for_profile(profile_id, donations):
    with LOCK:
        donations, profiles = sync_donations(donations)
        profile = next((item for item in profiles if item["id"] == str(profile_id)), None)
        if not profile:
            return donations, 0
        alias_keys = {alias_key(a.get("source"), a.get("username")) for a in profile.get("aliases", [])}
        kept = []
        removed = 0
        for donation in donations:
            belongs = donation.get("donorId") == profile["id"] or alias_key(donation.get("source"), donation.get("username")) in alias_keys
            if belongs:
                removed += 1
            else:
                kept.append(donation)
        adjustments = [item for item in load_adjustments() if item.get("donorId") != profile["id"]]
        save_adjustments(adjustments)
        save_profiles([item for item in profiles if item["id"] != profile["id"]])
        return kept, removed


def donor_csv_bytes(profile_id, donations):
    detail = get_detail(profile_id, donations)
    if not detail:
        return None, None
    profile = detail["profile"]
    summary = detail["summary"]
    output = io.StringIO(newline="")
    output.write("sep=;\r\n")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Donor", profile["displayName"]])
    writer.writerow(["Donation total", summary["donationTotal"], TOP_CURRENCY])
    writer.writerow(["Adjustments total", summary["adjustmentTotal"], TOP_CURRENCY])
    writer.writerow(["Grand total", summary["total"], TOP_CURRENCY])
    writer.writerow([])
    writer.writerow(["type", "date", "source", "username", "amount", "currency", "amountForTop", "topCurrency", "message", "includedInTop", "id"])
    for item in detail["timeline"]:
        writer.writerow([
            item.get("type", ""), item.get("date", ""), item.get("source", ""), item.get("username", ""),
            item.get("amount", ""), item.get("currency", ""), item.get("amountForTop", ""), item.get("topCurrency", TOP_CURRENCY),
            item.get("message", ""), item.get("includeInTop", ""), item.get("id", "")
        ])
    safe = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", profile["displayName"]).strip("_") or "donor"
    return ("\ufeff" + output.getvalue()).encode("utf-8"), f"{safe}_donations.csv"
