from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
STATUS_FILE = RUNTIME_DIR / "tts_status.json"
SENT_FILE = ROOT / "tts_sent.json"
AUDIO_DIR = ROOT / "audio_cache"
BROKEN_JSON_DIR = PROJECT_ROOT / "backups" / "broken_json"
VERSION_FILE = PROJECT_ROOT / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "dev"
CORE_URL = "http://127.0.0.1:3333"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from safe_json import load_json as _robust_load_json, save_json as _robust_save_json
from providers.base_provider import TTSProviderError
from providers.edge_provider import EdgeTTSProvider
from providers.http_provider import GenericHTTPProvider
from providers.xtts_provider import XTTSHTTPProvider
from providers.yandex_provider import YandexSpeechKitProvider
from providers.speakerbot_provider import SpeakerBotProvider


URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
HTML_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
_BROKEN_JSON_BACKED_UP: set[str] = set()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _backup_broken_json(path: Path, error: Exception) -> None:
    try:
        marker = str(path.resolve())
        if marker in _BROKEN_JSON_BACKED_UP or not path.exists() or path.stat().st_size == 0:
            return
        BROKEN_JSON_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BROKEN_JSON_DIR / f"{path.stem}_{stamp}{path.suffix}.broken.bak"
        shutil.copy2(path, backup)
        _BROKEN_JSON_BACKED_UP.add(marker)
        print(f"[TTS] Повреждённый JSON сохранён: {backup}")
    except Exception:
        pass


def load_json(path: Path, fallback: Any) -> Any:
    return _robust_load_json(path, fallback, retries=16, backup_dir=BROKEN_JSON_DIR)


def save_json(path: Path, data: Any) -> None:
    _robust_save_json(path, data, retries=120)


def write_status(
    status: str = "running",
    running: bool = True,
    connected: bool = False,
    provider: str = "",
    last_error: str | None = None,
    last_event: str | None = None,
    current_job: dict[str, Any] | None = None
) -> None:
    payload = {
        "service": "tts-hub",
        "version": APP_VERSION,
        "status": status,
        "running": running,
        "connected": connected,
        "provider": provider,
        "updatedAt": time.time(),
        "lastError": last_error,
        "lastEvent": last_event,
        "currentJob": current_job
    }
    try:
        save_json(STATUS_FILE, payload)
    except Exception:
        pass


def require_requests() -> None:
    if requests is None:
        raise RuntimeError("Не установлен requests. Запусти 00_INSTALL_ALL.bat")


def core_get(path: str, timeout: float = 8) -> Any:
    require_requests()
    response = requests.get(CORE_URL + path, timeout=timeout)
    response.raise_for_status()
    return response.json()


def core_post(path: str, data: dict[str, Any] | None = None, timeout: float = 12) -> Any:
    require_requests()
    response = requests.post(CORE_URL + path, json=data or {}, timeout=timeout)
    try:
        result = response.json()
    except Exception:
        result = {"ok": response.ok, "message": response.text[:500]}
    if not response.ok:
        raise RuntimeError(result.get("message") or f"Core HTTP {response.status_code}")
    return result


def core_ready() -> bool:
    try:
        data = core_get("/api/health", timeout=2)
        return bool(data.get("ok"))
    except Exception:
        return False


def donation_key(donation: dict[str, Any]) -> str:
    return str(
        donation.get("uniqueKey")
        or f"{donation.get('source', 'unknown')}:{donation.get('externalId', uuid.uuid4())}"
    )


def load_sent() -> dict[str, Any]:
    data = load_json(SENT_FILE, {"initialized": False, "seen": []})
    if not isinstance(data, dict):
        data = {"initialized": False, "seen": []}
    seen = data.get("seen")
    if not isinstance(seen, list):
        seen = []
    return {
        "initialized": bool(data.get("initialized", False)),
        "seen": set(str(x) for x in seen)
    }


def save_sent(data: dict[str, Any]) -> None:
    save_json(SENT_FILE, {
        "initialized": bool(data.get("initialized", True)),
        "seen": sorted(str(x) for x in data.get("seen", set()))
    })


def to_float(value: Any, default: float = 0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def bool_any(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "on", "да", "д"}


def _limit_repeated_characters(text: str, max_count: int) -> tuple[str, list[str]]:
    if max_count <= 0:
        return text, []
    removed: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        if len(value) > max_count:
            removed.append(f"повтор «{value[0]}» × {len(value) - max_count}")
        return value[:max_count]

    pattern = re.compile(rf"(.)\1{{{max_count},}}", re.DOTALL)
    return pattern.sub(replace, text), removed


def clean_text(original: str, config: dict[str, Any]) -> tuple[str, list[str]]:
    settings = config.get("textProcessing", {}) if isinstance(config, dict) else {}
    text = str(original or "")
    removed: list[str] = []

    if bool_any(settings.get("stripHtml"), True):
        tags = HTML_RE.findall(text)
        if tags:
            removed.extend([f"HTML: {tag[:80]}" for tag in tags[:10]])
        text = HTML_RE.sub(" ", text)
        text = html.unescape(text)

    if bool_any(settings.get("removeLinks"), True):
        links = URL_RE.findall(text)
        if links:
            removed.extend([f"ссылка: {link[:160]}" for link in links[:20]])
        text = URL_RE.sub(" ", text)

    max_repeated = int(to_float(settings.get("maxRepeatedCharacters"), 8))
    text, repeated_removed = _limit_repeated_characters(text, max_repeated)
    removed.extend(repeated_removed)

    if bool_any(settings.get("collapseWhitespace"), True):
        text = WHITESPACE_RE.sub(" ", text).strip()

    max_length = max(1, int(to_float(settings.get("maxLength"), 500)))
    if len(text) > max_length:
        removed.append(f"обрезано символов: {len(text) - max_length}")
        text = text[:max_length].rstrip()

    template = str(settings.get("template") or "{message}")
    text = template.replace("{message}", text).strip()
    return text, removed


def _list_lower(value: Any) -> list[str]:
    if isinstance(value, str):
        return [x.strip().lower() for x in value.split(",") if x.strip()]
    if isinstance(value, list):
        return [str(x).strip().lower() for x in value if str(x).strip()]
    return []


def rule_matches(job: dict[str, Any], rule: dict[str, Any]) -> bool:
    if not bool_any(rule.get("enabled"), True):
        return False
    conditions = rule.get("conditions")
    if not isinstance(conditions, dict):
        conditions = {}

    comparisons = [
        ("eventTypes", str(job.get("eventType") or "").lower()),
        ("sources", str(job.get("source") or "").lower()),
        ("userIds", str(job.get("userId") or "").lower()),
        ("usernames", str(job.get("username") or "").lower()),
        ("rewardIds", str(job.get("rewardId") or "").lower())
    ]
    for key, actual in comparisons:
        allowed = _list_lower(conditions.get(key))
        if allowed and actual not in allowed:
            return False

    required_roles = _list_lower(conditions.get("roles"))
    job_roles = set(_list_lower(job.get("roles")))
    if required_roles and not job_roles.intersection(required_roles):
        return False

    amount = to_float(job.get("amountForGoal"), to_float(job.get("amount"), 0))
    minimum = conditions.get("minAmount")
    maximum = conditions.get("maxAmount")
    if minimum not in (None, "") and amount < to_float(minimum):
        return False
    if maximum not in (None, "") and amount > to_float(maximum):
        return False

    return True


def select_profile(
    job: dict[str, Any],
    config: dict[str, Any],
    profiles: list[dict[str, Any]],
    rules: list[dict[str, Any]]
) -> tuple[dict[str, Any], str]:
    profile_by_id = {
        str(profile.get("id")): profile
        for profile in profiles
        if isinstance(profile, dict) and bool_any(profile.get("enabled"), True)
    }

    requested = str(job.get("profileId") or "")
    if requested and requested in profile_by_id:
        return profile_by_id[requested], ""

    for rule in sorted(
        [x for x in rules if isinstance(x, dict)],
        key=lambda x: int(to_float(x.get("priority"), 100))
    ):
        if rule_matches(job, rule):
            profile_id = str(rule.get("profileId") or "")
            if profile_id in profile_by_id:
                return profile_by_id[profile_id], str(rule.get("id") or "")

    default_id = str(config.get("defaultProfileId") or "default")
    fallback_profile = profile_by_id.get(default_id) or next(iter(profile_by_id.values()), {
        "id": "default",
        "name": "Default",
        "provider": "auto"
    })
    return fallback_profile, ""


def donation_allowed(job: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    if str(job.get("eventType")) != "donation":
        return True, ""
    settings = config.get("donations", {})
    if not bool_any(settings.get("enabled"), True):
        return False, "Озвучка донатов выключена"

    sources = _list_lower(settings.get("sources"))
    source = str(job.get("source") or "").lower()
    if sources and source not in sources:
        return False, f"Источник {source} отключён"

    if bool_any(job.get("bypassMinAmount"), False):
        return True, ""

    amount_field = str(settings.get("amountField") or "amountForGoal")
    amount = to_float(job.get(amount_field), 0)
    minimum = to_float(settings.get("minAmount"), 100)
    if amount < minimum:
        return False, f"Сумма ниже порога: {amount:g} < {minimum:g}"

    currency = str(settings.get("currency") or "").upper()
    if currency and currency not in {"ANY", "*"}:
        # При amountForGoal значение уже находится в валюте цели.
        if amount_field == "amount":
            actual_currency = str(job.get("currency") or "RUB").upper()
            if actual_currency != currency:
                return False, f"Валюта {actual_currency} не совпадает с {currency}"

    return True, ""


def provider_settings(
    provider_name: str,
    profile: dict[str, Any],
    config: dict[str, Any]
) -> dict[str, Any]:
    providers = config.get("providers", {})
    base = dict(providers.get(provider_name, {}) if isinstance(providers, dict) else {})

    if provider_name == "speakerbot":
        if profile.get("voiceAlias"):
            base["voiceAlias"] = profile.get("voiceAlias")
        base["badWordFilter"] = bool_any(
            profile.get("badWordFilter"),
            bool_any(base.get("badWordFilter"), False)
        )
    elif provider_name == "edge":
        if profile.get("edgeVoice"):
            base["voice"] = profile.get("edgeVoice")
        for key in ("rate", "volume", "pitch"):
            if profile.get(key) not in (None, ""):
                base[key] = profile.get(key)
    elif provider_name == "yandex":
        if profile.get("yandexVoice"):
            base["voice"] = profile.get("yandexVoice")
        if profile.get("yandexEmotion") not in (None, ""):
            base["emotion"] = profile.get("yandexEmotion")
        if profile.get("yandexSpeed") not in (None, ""):
            base["speed"] = profile.get("yandexSpeed")
    elif provider_name == "xtts":
        if profile.get("xttsSpeakerWav"):
            base["speakerWav"] = profile.get("xttsSpeakerWav")
        if profile.get("xttsLanguage"):
            base["language"] = profile.get("xttsLanguage")
    elif provider_name == "http":
        if profile.get("httpVoice") not in (None, ""):
            base["voice"] = profile.get("httpVoice")
        if profile.get("httpLanguage") not in (None, ""):
            base["language"] = profile.get("httpLanguage")
    return base


def choose_provider(
    job: dict[str, Any],
    profile: dict[str, Any],
    config: dict[str, Any]
) -> tuple[str, str | None, str]:
    requested = str(job.get("provider") or "").strip().lower()
    configured = str(profile.get("provider") or "auto").strip().lower()
    primary = requested or configured
    if primary in {"", "auto"}:
        primary = str(config.get("activeProvider") or "speakerbot").lower()
    fallback = config.get("fallbackProvider")
    fallback = str(fallback).lower() if fallback else None
    if fallback == primary:
        fallback = None
    return primary, fallback, configured


def providers_registry() -> dict[str, Any]:
    return {
        "speakerbot": SpeakerBotProvider(),
        "edge": EdgeTTSProvider(),
        "yandex": YandexSpeechKitProvider(),
        "xtts": XTTSHTTPProvider(),
        "http": GenericHTTPProvider()
    }


def process_speakerbot(
    provider: SpeakerBotProvider,
    job: dict[str, Any],
    text: str,
    profile: dict[str, Any],
    settings: dict[str, Any]
) -> dict[str, Any]:
    alias = str(profile.get("voiceAlias") or settings.get("defaultVoiceAlias") or "")
    if bool_any(settings.get("autoEnable"), True):
        try:
            provider.control("enable", settings)
        except Exception:
            # Некоторые версии Speaker.bot уже включены и могут не ответить на Enable.
            pass
    result = provider.speak(
        text,
        settings,
        voice_alias=alias,
        bad_word_filter=bool_any(settings.get("badWordFilter"), False),
        request_id=str(job.get("id"))
    )
    return {
        "provider": "speakerbot",
        "voice": alias,
        "result": result
    }


def process_audio_provider(
    provider_name: str,
    provider: Any,
    job: dict[str, Any],
    text: str,
    profile: dict[str, Any],
    settings: dict[str, Any]
) -> dict[str, Any]:
    extension = provider.output_extension(settings)
    filename = f"{str(job.get('id')).replace(':', '_').replace('/', '_')}.{extension}"
    output = AUDIO_DIR / filename
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    provider.synthesize(text, output, settings)
    return {
        "provider": provider_name,
        "voice": str(
            settings.get("voice")
            or settings.get("speakerWav")
            or settings.get("speaker_wav")
            or profile.get("edgeVoice")
            or profile.get("yandexVoice")
            or profile.get("xttsSpeakerWav")
            or profile.get("httpVoice")
            or ""
        ),
        "audioFile": str(output),
        "audioUrl": f"/api/tts/audio/{filename}"
    }


def update_job(job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    return core_post("/api/tts/job/update", {"id": job_id, "patch": patch})


def complete_job(job_id: str, status: str, error: str = "") -> dict[str, Any]:
    return core_post("/api/tts/job/complete", {
        "id": job_id,
        "status": status,
        "error": error
    })


def mark_retry(job: dict[str, Any], error: Exception, config: dict[str, Any]) -> None:
    queue_settings = config.get("queue", {})
    attempts = int(job.get("attempts", 0) or 0) + 1
    max_attempts = max(1, int(to_float(queue_settings.get("retryMaxAttempts"), 3)))

    if attempts >= max_attempts:
        complete_job(str(job.get("id")), "error", str(error))
        return

    base_delay = max(1, to_float(queue_settings.get("retryBaseDelaySeconds"), 5))
    delay = min(base_delay * (2 ** (attempts - 1)), 120)
    update_job(str(job.get("id")), {
        "status": "retry",
        "attempts": attempts,
        "error": str(error)[:1000],
        "nextAttemptAt": time.time() + delay
    })


def process_job(
    job: dict[str, Any],
    config: dict[str, Any],
    profiles: list[dict[str, Any]],
    rules: list[dict[str, Any]]
) -> tuple[bool, str, str]:
    job_id = str(job.get("id"))
    allowed, reason = donation_allowed(job, config)
    if not allowed:
        complete_job(job_id, "skipped", reason)
        return False, "skipped", reason

    cleaned, removed = clean_text(str(job.get("originalText") or ""), config)
    if not cleaned and bool_any(config.get("textProcessing", {}).get("skipEmpty"), True):
        complete_job(job_id, "skipped", "После очистки сообщение пустое")
        return False, "skipped", "Пустое сообщение"

    profile, matched_rule_id = select_profile(job, config, profiles, rules)
    primary, fallback, configured_provider = choose_provider(job, profile, config)
    registry = providers_registry()

    update_job(job_id, {
        "status": "processing",
        "cleanedText": cleaned,
        "removedParts": removed,
        "profileId": profile.get("id"),
        "matchedRuleId": matched_rule_id,
        "configuredProvider": configured_provider,
        "requestedProvider": str(job.get("provider") or ""),
        "provider": primary,
        "voice": (
            profile.get("voiceAlias")
            or profile.get("edgeVoice")
            or profile.get("yandexVoice")
            or profile.get("xttsSpeakerWav")
            or profile.get("httpVoice")
            or ""
        ),
        "fallbackUsed": False,
        "error": ""
    })

    errors: list[str] = []
    attempted_providers: set[str] = set()
    for provider_index, provider_name in enumerate([primary, fallback]):
        if not provider_name or provider_name in attempted_providers:
            continue
        attempted_providers.add(provider_name)
        provider = registry.get(provider_name)
        if provider is None:
            errors.append(f"{provider_name}: неизвестный провайдер")
            continue

        settings = provider_settings(provider_name, profile, config)
        if not bool_any(settings.get("enabled"), True):
            errors.append(f"{provider_name}: выключен")
            continue

        ok, validation_error = provider.validate(settings)
        if not ok:
            errors.append(f"{provider_name}: {validation_error}")
            continue

        try:
            if provider_name == "speakerbot":
                result = process_speakerbot(provider, job, cleaned, profile, settings)
                update_job(job_id, {
                    "provider": "speakerbot",
                    "voice": result["voice"],
                    "cleanedText": cleaned,
                    "removedParts": removed,
                    "fallbackUsed": provider_index > 0,
                    "providerErrors": list(errors)
                })
                complete_job(job_id, "sent")
                return True, "speakerbot", result["voice"]

            result = process_audio_provider(
                provider_name, provider, job, cleaned, profile, settings
            )
            update_job(job_id, {
                "status": "ready",
                "provider": provider_name,
                "voice": result["voice"],
                "audioFile": result["audioFile"],
                "audioUrl": result["audioUrl"],
                "cleanedText": cleaned,
                "removedParts": removed,
                "fallbackUsed": provider_index > 0,
                "providerErrors": list(errors)
            })
            return True, provider_name, result["voice"]
        except Exception as error:
            errors.append(f"{provider_name}: {type(error).__name__}: {error}")

    raise TTSProviderError("; ".join(errors) or "Нет доступного TTS-провайдера")


def scan_donations(config: dict[str, Any], sent: dict[str, Any]) -> None:
    donations = core_get("/api/donations")
    if not isinstance(donations, list):
        return

    seen: set[str] = sent["seen"]
    donation_settings = config.get("donations", {})

    if not sent.get("initialized"):
        if not bool_any(donation_settings.get("readExistingOnFirstStart"), False):
            seen.update(donation_key(x) for x in donations if isinstance(x, dict))
        sent["initialized"] = True
        save_sent(sent)
        return

    changed = False
    for donation in donations:
        if not isinstance(donation, dict):
            continue
        key = donation_key(donation)
        if key in seen:
            continue

        source = str(donation.get("source") or "")
        default_speak = bool_any(donation_settings.get("externalDefaultSpeak"), True)
        speak_flag = bool_any(
            donation.get("speakTTS"),
            False if source == "manual" and bool_any(donation_settings.get("manualRequiresSpeakFlag"), True)
            else default_speak
        )

        if speak_flag:
            payload = {
                "id": f"donation:{key}",
                "eventType": "donation",
                "eventId": key,
                "source": source,
                "username": donation.get("username"),
                "userId": donation.get("userId") or "",
                "roles": donation.get("roles") or [],
                "amount": donation.get("amount"),
                "amountForGoal": donation.get("amountForGoal"),
                "currency": donation.get("currency"),
                "text": donation.get("message") or "",
                "origin": "donation",
                "bypassMinAmount": bool(
                    source == "manual"
                    and speak_flag
                    and bool_any(donation_settings.get("manualBypassMinAmount"), True)
                ),
                "metadata": {
                    "donationUniqueKey": key,
                    "notifyStreamerBot": donation.get("notifyStreamerBot"),
                    "triggerDonationEvents": donation.get("triggerDonationEvents")
                }
            }
            try:
                core_post("/api/tts/enqueue", payload)
            except Exception as error:
                # Не отмечаем событие обработанным, если Core временно недоступен.
                print(f"[TTS] Не удалось поставить донат в очередь {key}: {error}")
                continue

        seen.add(key)
        changed = True

    if changed:
        save_sent(sent)


def process_control(config: dict[str, Any]) -> bool:
    data = core_get("/api/tts/control-state")
    commands = data.get("commands") if isinstance(data, dict) else []
    if not isinstance(commands, list):
        commands = []

    speaker_settings = config.get("providers", {}).get("speakerbot", {})
    speaker = SpeakerBotProvider()
    connected = False

    for command in commands:
        if not isinstance(command, dict):
            continue
        command_id = str(command.get("id") or "")
        action = str(command.get("action") or "").lower()
        try:
            if bool_any(speaker_settings.get("enabled"), True):
                speaker.control(action, speaker_settings)
                connected = True
            core_post("/api/tts/control/consume", {"id": command_id})
        except Exception as error:
            # Команда остаётся для следующей попытки, но не блокирует работу.
            print(f"[TTS] Speaker.bot control {action}: {error}")
            break

    return connected


def cleanup_audio(config: dict[str, Any]) -> None:
    max_files = max(10, int(to_float(config.get("queue", {}).get("audioCacheMaxFiles"), 200)))
    if not AUDIO_DIR.exists():
        return
    files = sorted(
        [x for x in AUDIO_DIR.iterdir() if x.is_file()],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    for path in files[max_files:]:
        try:
            path.unlink()
        except Exception:
            pass


def run_loop() -> None:
    print("=" * 58)
    print(f" VicDonationGoal v{APP_VERSION} — TTS Hub")
    print(" Speaker.bot + Edge + Yandex + XTTS Local + Custom HTTP")
    print("=" * 58)

    require_requests()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    sent = load_sent()
    last_scan = 0.0
    last_cleanup = 0.0
    last_health_check = 0.0
    last_error = None
    last_event = None
    speaker_connected = False

    while True:
        try:
            if not core_ready():
                write_status(
                    status="waiting-core",
                    running=True,
                    connected=False,
                    last_error="Core server недоступен"
                )
                time.sleep(2)
                continue

            bootstrap = core_get("/api/tts/bootstrap")
            config = bootstrap.get("config", {})
            profiles = bootstrap.get("profiles", [])
            rules = bootstrap.get("rules", [])
            control = bootstrap.get("control", {})
            queue = bootstrap.get("queue", [])

            speaker_connected = process_control(config) or speaker_connected

            now = time.time()
            if now - last_health_check >= 5:
                speaker_settings = config.get("providers", {}).get("speakerbot", {})
                if bool_any(speaker_settings.get("enabled"), True):
                    speaker_connected, health_error = SpeakerBotProvider().health_check(speaker_settings)
                    if health_error and str(config.get("activeProvider") or "") == "speakerbot":
                        last_error = f"Speaker.bot: {health_error}"
                    elif speaker_connected and last_error and last_error.startswith("Speaker.bot:"):
                        last_error = None
                else:
                    speaker_connected = False
                last_health_check = now

            if now - last_scan >= 0.8:
                scan_donations(config, sent)
                last_scan = now

            if not bool_any(config.get("enabled"), True):
                write_status(
                    status="disabled",
                    running=True,
                    connected=speaker_connected,
                    provider=str(config.get("activeProvider") or ""),
                    last_error=None,
                    last_event=last_event
                )
                time.sleep(1)
                continue

            if bool_any(control.get("paused"), bool_any(config.get("paused"), False)):
                write_status(
                    status="paused",
                    running=True,
                    connected=speaker_connected,
                    provider=str(config.get("activeProvider") or ""),
                    last_error=last_error,
                    last_event=last_event
                )
                time.sleep(0.8)
                continue

            pending = [
                row for row in queue
                if isinstance(row, dict)
                and row.get("status") in {"pending", "retry"}
                and (
                    row.get("nextAttemptAt") in (None, "")
                    or to_float(row.get("nextAttemptAt"), 0) <= time.time()
                )
            ]

            current = pending[0] if pending else None
            if current:
                job_id = str(current.get("id"))
                write_status(
                    status="processing",
                    running=True,
                    connected=speaker_connected,
                    provider=str(config.get("activeProvider") or ""),
                    last_error=None,
                    last_event=last_event,
                    current_job={
                        "id": job_id,
                        "username": current.get("username"),
                        "eventType": current.get("eventType"),
                        "text": str(current.get("originalText") or "")[:180]
                    }
                )
                try:
                    ok, provider_name, voice = process_job(current, config, profiles, rules)
                    last_error = None
                    last_event = f"{job_id} → {provider_name} / {voice}"
                    if provider_name == "speakerbot":
                        speaker_connected = True
                    print(f"[TTS] {last_event}")
                except Exception as error:
                    last_error = f"{type(error).__name__}: {error}"
                    print(f"[TTS] Ошибка {job_id}: {last_error}")
                    mark_retry(current, error, config)

            if now - last_cleanup >= 60:
                cleanup_audio(config)
                last_cleanup = now

            write_status(
                status="running",
                running=True,
                connected=speaker_connected,
                provider=str(config.get("activeProvider") or ""),
                last_error=last_error,
                last_event=last_event
            )

            interval = max(0.25, to_float(config.get("queue", {}).get("pollIntervalSeconds"), 0.6))
            time.sleep(interval)

        except KeyboardInterrupt:
            write_status(status="stopped", running=False, connected=False)
            print("\n[TTS] Остановлено")
            return
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            write_status(
                status="error",
                running=True,
                connected=speaker_connected,
                last_error=last_error,
                last_event=last_event
            )
            print(f"[TTS] Ошибка цикла: {last_error}")
            time.sleep(2)


if __name__ == "__main__":
    run_loop()
