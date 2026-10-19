from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import sys
PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))
from safe_json import load_json as _robust_load_json, save_json as _robust_save_json
from source_registry import AUTOMATIC_SOURCE_IDS
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
TTS_DIR = PROJECT_ROOT / "integrations" / "tts"
RUNTIME_DIR = PROJECT_ROOT / "runtime"

CONFIG_FILE = TTS_DIR / "tts_config.json"
PROFILES_FILE = TTS_DIR / "tts_profiles.json"
RULES_FILE = TTS_DIR / "tts_rules.json"
QUEUE_FILE = TTS_DIR / "tts_queue.json"
HISTORY_FILE = TTS_DIR / "tts_history.json"
CONTROL_FILE = TTS_DIR / "tts_control.json"
LOG_FILE = TTS_DIR / "tts_log.json"
AUDIO_DIR = TTS_DIR / "audio_cache"
STATUS_FILE = RUNTIME_DIR / "tts_status.json"
PLAYER_STATUS_FILE = RUNTIME_DIR / "tts_player_status.json"

LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_save(path: Path, data: Any) -> None:
    _robust_save_json(path, data, retries=120)


def _load(path: Path, fallback: Any) -> Any:
    return _robust_load_json(path, fallback, retries=16)


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "paused": False,
    "activeProvider": "speakerbot",
    "fallbackProvider": "edge",
    "defaultProfileId": "default",
    "donations": {
        "enabled": True,
        "sources": [],  # Empty means every registered automatic source + manual flags
        "amountField": "amountForGoal",
        "minAmount": 100,
        "currency": "RUB",
        "manualRequiresSpeakFlag": True,
        "manualBypassMinAmount": True,
        "externalDefaultSpeak": True,
        "readExistingOnFirstStart": False
    },
    "textProcessing": {
        "template": "{message}",
        "skipEmpty": True,
        "removeLinks": True,
        "stripHtml": True,
        "collapseWhitespace": True,
        "maxLength": 500,
        "maxRepeatedCharacters": 8
    },
    "queue": {
        "maxItems": 100,
        "maxHistoryItems": 2000,
        "pollIntervalSeconds": 0.6,
        "retryMaxAttempts": 3,
        "retryBaseDelaySeconds": 5,
        "audioCacheMaxFiles": 200,
        "browserPollIntervalMs": 500,
        "browserDelayAfterDoneMs": 250,
        "browserMaxPlayAttempts": 3
    },
    "providers": {
        "speakerbot": {
            "enabled": True,
            "websocketUrl": "ws://127.0.0.1:7580/",
            "defaultVoiceAlias": "Donations",
            "badWordFilter": False,
            "autoEnable": True,
            "connectTimeoutSeconds": 4,
            "responseTimeoutSeconds": 2
        },
        "edge": {
            "enabled": True,
            "voice": "ru-RU-SvetlanaNeural",
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz",
            "proxy": "",
            "connect_timeout_seconds": 10,
            "receive_timeout_seconds": 60,
            "output_format": "mp3"
        },
        "yandex": {
            "enabled": False,
            "endpoint": "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
            "authMode": "api_key",
            "apiKey": "",
            "iamToken": "",
            "folderId": "",
            "lang": "ru-RU",
            "voice": "marina",
            "emotion": "friendly",
            "speed": "1.0",
            "format": "mp3",
            "timeoutSeconds": 60
        },
        "xtts": {
            "enabled": False,
            "endpoint": "http://127.0.0.1:8020/tts_to_audio/",
            "language": "ru",
            "speakerWav": "",
            "timeoutSeconds": 180,
            "output_format": "wav",
            "responseType": "audio",
            "textField": "text",
            "languageField": "language",
            "speakerField": "speaker_wav",
            "headers": {}
        },
        "http": {
            "enabled": False,
            "url": "",
            "method": "POST",
            "headers": {},
            "bodyType": "json",
            "body": {"text": "{text}", "voice": "{voice}", "language": "{language}"},
            "voice": "",
            "language": "ru",
            "timeoutSeconds": 60,
            "output_format": "mp3",
            "responseType": "audio",
            "audioUrlField": "audioUrl",
            "audioBase64Field": "audio"
        }
    }
}

DEFAULT_PROFILES: list[dict[str, Any]] = [
    {
        "id": "default",
        "name": "Default",
        "enabled": True,
        "provider": "speakerbot",
        "voiceAlias": "Donations",
        "edgeVoice": "ru-RU-SvetlanaNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
        "badWordFilter": False
    },
    {
        "id": "donations",
        "name": "Donations",
        "enabled": True,
        "provider": "speakerbot",
        "voiceAlias": "Donations",
        "edgeVoice": "ru-RU-SvetlanaNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
        "badWordFilter": False
    },
    {
        "id": "rewards",
        "name": "Rewards",
        "enabled": True,
        "provider": "speakerbot",
        "voiceAlias": "Rewards",
        "edgeVoice": "ru-RU-SvetlanaNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
        "badWordFilter": False
    },
    {
        "id": "washington",
        "name": "Washington",
        "enabled": True,
        "provider": "speakerbot",
        "voiceAlias": "Washington",
        "edgeVoice": "ru-RU-DmitryNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "-10Hz",
        "badWordFilter": False
    },
    {
        "id": "moderator",
        "name": "Moderator",
        "enabled": True,
        "provider": "speakerbot",
        "voiceAlias": "Moderator",
        "edgeVoice": "ru-RU-DmitryNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
        "badWordFilter": False
    },
    {
        "id": "vip",
        "name": "VIP",
        "enabled": True,
        "provider": "speakerbot",
        "voiceAlias": "VIP",
        "edgeVoice": "ru-RU-SvetlanaNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
        "badWordFilter": False
    }
]

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "id": "personal-example",
        "name": "Персональный голос — пример",
        "enabled": False,
        "priority": 10,
        "profileId": "default",
        "conditions": {
            "eventTypes": [],
            "sources": [],
            "userIds": [],
            "usernames": ["ViewerName"],
            "roles": [],
            "rewardIds": [],
            "minAmount": None,
            "maxAmount": None
        }
    },
    {
        "id": "moderator-rule",
        "name": "Модераторы",
        "enabled": True,
        "priority": 20,
        "profileId": "moderator",
        "conditions": {
            "eventTypes": [],
            "sources": [],
            "userIds": [],
            "usernames": [],
            "roles": ["moderator"],
            "rewardIds": [],
            "minAmount": None,
            "maxAmount": None
        }
    },
    {
        "id": "vip-rule",
        "name": "VIP",
        "enabled": True,
        "priority": 30,
        "profileId": "vip",
        "conditions": {
            "eventTypes": [],
            "sources": [],
            "userIds": [],
            "usernames": [],
            "roles": ["vip"],
            "rewardIds": [],
            "minAmount": None,
            "maxAmount": None
        }
    },
    {
        "id": "washington-rule",
        "name": "Вашингтон",
        "enabled": True,
        "priority": 100,
        "profileId": "washington",
        "conditions": {
            "eventTypes": ["washington"],
            "sources": [],
            "userIds": [],
            "usernames": [],
            "roles": [],
            "rewardIds": [],
            "minAmount": None,
            "maxAmount": None
        }
    },
    {
        "id": "rewards-rule",
        "name": "Баллы канала",
        "enabled": True,
        "priority": 110,
        "profileId": "rewards",
        "conditions": {
            "eventTypes": ["channel_reward"],
            "sources": [],
            "userIds": [],
            "usernames": [],
            "roles": [],
            "rewardIds": [],
            "minAmount": None,
            "maxAmount": None
        }
    },
    {
        "id": "donations-rule",
        "name": "Донаты",
        "enabled": True,
        "priority": 120,
        "profileId": "donations",
        "conditions": {
            "eventTypes": ["donation"],
            "sources": [],
            "userIds": [],
            "usernames": [],
            "roles": [],
            "rewardIds": [],
            "minAmount": None,
            "maxAmount": None
        }
    }
]

DEFAULT_CONTROL = {
    "paused": False,
    "stopToken": 0,
    "commands": []
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_tts_files() -> None:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK:
        if not CONFIG_FILE.exists():
            _atomic_save(CONFIG_FILE, DEFAULT_CONFIG)
        if not PROFILES_FILE.exists():
            _atomic_save(PROFILES_FILE, DEFAULT_PROFILES)
        if not RULES_FILE.exists():
            _atomic_save(RULES_FILE, DEFAULT_RULES)
        if not QUEUE_FILE.exists():
            _atomic_save(QUEUE_FILE, [])
        if not HISTORY_FILE.exists():
            _atomic_save(HISTORY_FILE, [])
        if not CONTROL_FILE.exists():
            _atomic_save(CONTROL_FILE, DEFAULT_CONTROL)
        if not LOG_FILE.exists():
            _atomic_save(LOG_FILE, [])


def get_config() -> dict[str, Any]:
    ensure_tts_files()
    data = _load(CONFIG_FILE, {})
    if not isinstance(data, dict):
        data = {}
    return _deep_merge(DEFAULT_CONFIG, data)


def save_config(data: dict[str, Any]) -> dict[str, Any]:
    current = get_config()
    if not isinstance(data, dict):
        data = {}
    merged = _deep_merge(current, data)
    with LOCK:
        _atomic_save(CONFIG_FILE, merged)
    return merged


def get_profiles() -> list[dict[str, Any]]:
    ensure_tts_files()
    data = _load(PROFILES_FILE, DEFAULT_PROFILES)
    if not isinstance(data, list):
        return [dict(x) for x in DEFAULT_PROFILES]
    return [x for x in data if isinstance(x, dict)]


def save_profiles(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("profiles", [])
    if not isinstance(data, list):
        raise ValueError("profiles должен быть списком")

    allowed_providers = {"auto", "speakerbot", "edge", "yandex", "xtts", "http"}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id") or "").strip()
        if not profile_id:
            raise ValueError("У каждого профиля должен быть ID")
        if profile_id in seen:
            raise ValueError(f"Повторяющийся ID профиля: {profile_id}")
        seen.add(profile_id)

        provider = str(item.get("provider") or "auto").strip().lower()
        if provider not in allowed_providers:
            raise ValueError(f"Неизвестный провайдер профиля {profile_id}: {provider}")

        row = dict(item)
        row["id"] = profile_id
        row["name"] = str(item.get("name") or profile_id)
        row["enabled"] = bool(item.get("enabled", True))
        row["provider"] = provider
        normalized.append(row)

    if not normalized:
        raise ValueError("Нельзя сохранить пустой список голосовых профилей")
    with LOCK:
        _atomic_save(PROFILES_FILE, normalized)
    return normalized


def get_rules() -> list[dict[str, Any]]:
    ensure_tts_files()
    data = _load(RULES_FILE, DEFAULT_RULES)
    if not isinstance(data, list):
        return [dict(x) for x in DEFAULT_RULES]
    return [x for x in data if isinstance(x, dict)]


def _string_list(value: Any, lower: bool = False) -> list[str]:
    if isinstance(value, str):
        values = [x.strip() for x in value.split(",") if x.strip()]
    elif isinstance(value, list):
        values = [str(x).strip() for x in value if str(x).strip()]
    else:
        values = []
    return [x.lower() for x in values] if lower else values


def save_rules(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("rules", [])
    if not isinstance(data, list):
        raise ValueError("rules должен быть списком")

    profile_ids = {str(x.get("id")) for x in get_profiles() if isinstance(x, dict)}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("id") or "").strip()
        if not rule_id:
            raise ValueError("У каждого правила должен быть ID")
        if rule_id in seen:
            raise ValueError(f"Повторяющийся ID правила: {rule_id}")
        seen.add(rule_id)

        profile_id = str(item.get("profileId") or "default").strip()
        if profile_id not in profile_ids:
            raise ValueError(f"Правило {rule_id} ссылается на неизвестный профиль: {profile_id}")

        try:
            priority = int(item.get("priority", 100))
        except Exception:
            priority = 100

        conditions = item.get("conditions") if isinstance(item.get("conditions"), dict) else {}
        row = dict(item)
        row.update({
            "id": rule_id,
            "name": str(item.get("name") or rule_id),
            "enabled": bool(item.get("enabled", True)),
            "priority": priority,
            "profileId": profile_id,
            "conditions": {
                "eventTypes": _string_list(conditions.get("eventTypes"), lower=True),
                "sources": _string_list(conditions.get("sources"), lower=True),
                "userIds": _string_list(conditions.get("userIds")),
                "usernames": _string_list(conditions.get("usernames"), lower=True),
                "roles": _string_list(conditions.get("roles"), lower=True),
                "rewardIds": _string_list(conditions.get("rewardIds")),
                "minAmount": conditions.get("minAmount") if conditions.get("minAmount") not in (None, "") else None,
                "maxAmount": conditions.get("maxAmount") if conditions.get("maxAmount") not in (None, "") else None,
            },
        })
        normalized.append(row)

    normalized.sort(key=lambda x: int(x.get("priority", 100)))
    with LOCK:
        _atomic_save(RULES_FILE, normalized)
    return normalized



def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _rule_matches_job(job: dict[str, Any], rule: dict[str, Any]) -> bool:
    if not bool(rule.get("enabled", True)):
        return False
    conditions = rule.get("conditions") if isinstance(rule.get("conditions"), dict) else {}
    comparisons = [
        ("eventTypes", str(job.get("eventType") or "").lower()),
        ("sources", str(job.get("source") or "").lower()),
        ("userIds", str(job.get("userId") or "")),
        ("usernames", str(job.get("username") or "").lower()),
        ("rewardIds", str(job.get("rewardId") or "")),
    ]
    for key, actual in comparisons:
        allowed = _string_list(conditions.get(key), lower=key in {"eventTypes", "sources", "usernames"})
        if allowed and actual not in allowed:
            return False

    required_roles = set(_string_list(conditions.get("roles"), lower=True))
    job_roles = set(_string_list(job.get("roles"), lower=True))
    if required_roles and not required_roles.intersection(job_roles):
        return False

    amount = _to_float(job.get("amountForGoal"), _to_float(job.get("amount"), 0))
    minimum = conditions.get("minAmount")
    maximum = conditions.get("maxAmount")
    if minimum not in (None, "") and amount < _to_float(minimum):
        return False
    if maximum not in (None, "") and amount > _to_float(maximum):
        return False
    return True


def test_routing(payload: dict[str, Any]) -> dict[str, Any]:
    job = _normalized_job(payload if isinstance(payload, dict) else {})
    config = get_config()
    profiles = get_profiles()
    rules = get_rules()
    enabled_profiles = {
        str(profile.get("id")): profile
        for profile in profiles
        if isinstance(profile, dict) and bool(profile.get("enabled", True))
    }

    requested = str(job.get("profileId") or "")
    matched_rule = None
    if requested and requested in enabled_profiles:
        profile = enabled_profiles[requested]
        reason = "Профиль передан напрямую в событии"
    else:
        profile = None
        reason = ""
        for rule in sorted(rules, key=lambda row: int(row.get("priority", 100))):
            if _rule_matches_job(job, rule):
                candidate = enabled_profiles.get(str(rule.get("profileId") or ""))
                if candidate:
                    matched_rule = rule
                    profile = candidate
                    reason = "Первое совпавшее правило"
                    break
        if profile is None:
            default_id = str(config.get("defaultProfileId") or "default")
            profile = enabled_profiles.get(default_id) or next(iter(enabled_profiles.values()), None)
            reason = "Профиль по умолчанию"

    if profile is None:
        return {"ok": False, "message": "Нет включённых голосовых профилей", "job": job}

    configured_provider = str(profile.get("provider") or "auto").lower()
    provider = configured_provider
    if provider in {"", "auto"}:
        provider = str(config.get("activeProvider") or "speakerbot").lower()

    voice = ""
    if provider == "speakerbot":
        voice = str(profile.get("voiceAlias") or config.get("providers", {}).get("speakerbot", {}).get("defaultVoiceAlias") or "")
    elif provider == "edge":
        voice = str(profile.get("edgeVoice") or config.get("providers", {}).get("edge", {}).get("voice") or "")
    elif provider == "yandex":
        voice = str(profile.get("yandexVoice") or config.get("providers", {}).get("yandex", {}).get("voice") or "")
    elif provider == "xtts":
        voice = str(profile.get("xttsSpeakerWav") or config.get("providers", {}).get("xtts", {}).get("speakerWav") or "")
    elif provider == "http":
        voice = str(profile.get("httpVoice") or config.get("providers", {}).get("http", {}).get("voice") or "")

    return {
        "ok": True,
        "reason": reason,
        "job": job,
        "matchedRule": matched_rule,
        "profile": profile,
        "configuredProvider": configured_provider,
        "provider": provider,
        "voice": voice,
        "fallbackProvider": config.get("fallbackProvider"),
    }

def get_queue() -> list[dict[str, Any]]:
    ensure_tts_files()
    data = _load(QUEUE_FILE, [])
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _save_queue(data: list[dict[str, Any]]) -> None:
    _atomic_save(QUEUE_FILE, data)


def get_history(limit: int = 200) -> list[dict[str, Any]]:
    ensure_tts_files()
    data = _load(HISTORY_FILE, [])
    if not isinstance(data, list):
        return []
    rows = [x for x in data if isinstance(x, dict)]
    if limit <= 0:
        return rows
    return rows[-limit:]


def _save_history(data: list[dict[str, Any]]) -> None:
    max_items = int(get_config().get("queue", {}).get("maxHistoryItems", 1000) or 1000)
    _atomic_save(HISTORY_FILE, data[-max(10, max_items):])


def append_log(level: str, message: str, details: Any = None) -> dict[str, Any]:
    ensure_tts_files()
    row = {
        "id": str(uuid.uuid4()),
        "time": now_iso(),
        "level": str(level or "info"),
        "message": str(message or ""),
        "details": details
    }
    with LOCK:
        data = _load(LOG_FILE, [])
        if not isinstance(data, list):
            data = []
        data.append(row)
        _atomic_save(LOG_FILE, data[-500:])
    return row


def get_logs(limit: int = 200) -> list[dict[str, Any]]:
    ensure_tts_files()
    data = _load(LOG_FILE, [])
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)][-max(1, limit):]


def _normalized_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(payload.get("id") or uuid.uuid4())
    event_type = str(payload.get("eventType") or payload.get("event_type") or "manual")
    text = str(payload.get("text") or payload.get("message") or "")
    roles = payload.get("roles")
    if isinstance(roles, str):
        roles = [x.strip() for x in roles.split(",") if x.strip()]
    if not isinstance(roles, list):
        roles = []

    return {
        "id": job_id,
        "eventType": event_type,
        "source": str(payload.get("source") or event_type),
        "eventId": str(payload.get("eventId") or payload.get("event_id") or job_id),
        "username": str(payload.get("username") or payload.get("user") or "Аноним"),
        "userId": str(payload.get("userId") or payload.get("user_id") or ""),
        "roles": [str(x).lower() for x in roles],
        "rewardId": str(payload.get("rewardId") or payload.get("reward_id") or ""),
        "amount": payload.get("amount"),
        "amountForGoal": payload.get("amountForGoal"),
        "currency": str(payload.get("currency") or "RUB").upper(),
        "originalText": text,
        "cleanedText": str(payload.get("cleanedText") or ""),
        "removedParts": payload.get("removedParts") if isinstance(payload.get("removedParts"), list) else [],
        "profileId": str(payload.get("profileId") or payload.get("voiceProfile") or ""),
        "provider": str(payload.get("provider") or ""),
        "voice": str(payload.get("voice") or ""),
        "status": str(payload.get("status") or "pending"),
        "priority": int(payload.get("priority", 100) or 100),
        "origin": str(payload.get("origin") or "api"),
        "bypassMinAmount": bool(payload.get("bypassMinAmount", False)),
        "createdAt": str(payload.get("createdAt") or now_iso()),
        "updatedAt": now_iso(),
        "attempts": int(payload.get("attempts", 0) or 0),
        "nextAttemptAt": payload.get("nextAttemptAt"),
        "error": str(payload.get("error") or ""),
        "audioUrl": str(payload.get("audioUrl") or ""),
        "audioFile": str(payload.get("audioFile") or ""),
        "playAttempts": int(payload.get("playAttempts", 0) or 0),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    }


def enqueue_job(payload: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    ensure_tts_files()
    if not isinstance(payload, dict):
        raise ValueError("TTS payload должен быть объектом")
    job = _normalized_job(payload)
    config = get_config()
    max_items = int(config.get("queue", {}).get("maxItems", 100) or 100)

    with LOCK:
        queue = get_queue()
        duplicate = next((x for x in queue if str(x.get("id")) == job["id"]), None)
        if duplicate:
            return duplicate, False, "TTS задача уже существует"
        if len(queue) >= max_items:
            raise RuntimeError(f"Очередь TTS заполнена ({len(queue)}/{max_items})")
        queue.append(job)
        queue.sort(key=lambda x: (int(x.get("priority", 100)), str(x.get("createdAt", ""))))
        _save_queue(queue)
    append_log("info", "TTS задача добавлена", {"id": job["id"], "eventType": job["eventType"]})
    return job, True, "TTS задача добавлена"


def update_job(job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    job_id = str(job_id or "")
    if not job_id:
        return None
    with LOCK:
        queue = get_queue()
        for index, row in enumerate(queue):
            if str(row.get("id")) != job_id:
                continue
            updated = dict(row)
            updated.update(patch if isinstance(patch, dict) else {})
            updated["id"] = job_id
            updated["updatedAt"] = now_iso()
            queue[index] = updated
            _save_queue(queue)
            return updated
    return None


def remove_job(job_id: str) -> dict[str, Any] | None:
    job_id = str(job_id or "")
    with LOCK:
        queue = get_queue()
        for index, row in enumerate(queue):
            if str(row.get("id")) == job_id:
                removed = queue.pop(index)
                _save_queue(queue)
                return removed
    return None


def complete_job(job_id: str, status: str = "played", error: str = "") -> dict[str, Any] | None:
    with LOCK:
        row = remove_job(job_id)
        if row is None:
            return None
        row = dict(row)
        row["status"] = status
        row["error"] = str(error or row.get("error") or "")
        row["completedAt"] = now_iso()
        row["updatedAt"] = row["completedAt"]
        history = get_history(limit=0)
        history.append(row)
        _save_history(history)
    append_log("error" if status == "error" else "info", f"TTS задача завершена: {status}", {"id": job_id, "error": error})
    return row


def retry_history_job(job_id: str) -> dict[str, Any] | None:
    job_id = str(job_id or "")
    with LOCK:
        history = get_history(limit=0)
        index = next((i for i, row in enumerate(history) if str(row.get("id")) == job_id), None)
        if index is None:
            return None
        source = dict(history[index])
        clone = dict(source)
        clone["id"] = str(uuid.uuid4())
        clone["status"] = "pending"
        clone["attempts"] = 0
        clone["playAttempts"] = 0
        clone["error"] = ""
        clone["audioUrl"] = ""
        clone["audioFile"] = ""
        clone["createdAt"] = now_iso()
        clone["updatedAt"] = clone["createdAt"]
        clone["origin"] = "retry"
    job, _, _ = enqueue_job(clone)
    return job


def delete_history_job(job_id: str) -> dict[str, Any] | None:
    job_id = str(job_id or "")
    with LOCK:
        history = get_history(limit=0)
        for index, row in enumerate(history):
            if str(row.get("id")) == job_id:
                removed = history.pop(index)
                _save_history(history)
                return removed
    return None


def clear_history() -> int:
    with LOCK:
        history = get_history(limit=0)
        count = len(history)
        _save_history([])
    append_log("warn", "История TTS очищена", {"count": count})
    return count


def clear_queue() -> int:
    with LOCK:
        queue = get_queue()
        count = len(queue)
        _save_queue([])
    append_log("warn", "Очередь TTS очищена", {"count": count})
    return count


def get_control() -> dict[str, Any]:
    ensure_tts_files()
    data = _load(CONTROL_FILE, DEFAULT_CONTROL)
    if not isinstance(data, dict):
        data = dict(DEFAULT_CONTROL)
    data.setdefault("paused", False)
    data.setdefault("stopToken", 0)
    data.setdefault("commands", [])
    return data


def set_paused(value: bool) -> dict[str, Any]:
    with LOCK:
        data = get_control()
        data["paused"] = bool(value)
        _atomic_save(CONTROL_FILE, data)
    config = get_config()
    config["paused"] = bool(value)
    save_config(config)
    return data


def enqueue_command(action: str) -> dict[str, Any]:
    action = str(action or "").strip().lower()
    if action not in {"pause", "resume", "stop", "clear", "enable", "disable"}:
        raise ValueError("Неизвестная TTS команда")
    with LOCK:
        data = get_control()
        if action == "pause":
            data["paused"] = True
        elif action == "resume":
            data["paused"] = False
        elif action in {"stop", "clear"}:
            data["stopToken"] = int(data.get("stopToken", 0) or 0) + 1
        command = {
            "id": str(uuid.uuid4()),
            "action": action,
            "createdAt": now_iso()
        }
        commands = data.get("commands")
        if not isinstance(commands, list):
            commands = []
        commands.append(command)
        data["commands"] = commands[-50:]
        _atomic_save(CONTROL_FILE, data)
    if action == "clear":
        clear_queue()
    append_log("info", f"TTS command: {action}", {"id": command["id"]})
    return command


def consume_command(command_id: str) -> bool:
    command_id = str(command_id or "")
    with LOCK:
        data = get_control()
        commands = data.get("commands") if isinstance(data.get("commands"), list) else []
        new_commands = [x for x in commands if str(x.get("id")) != command_id]
        changed = len(new_commands) != len(commands)
        if changed:
            data["commands"] = new_commands
            _atomic_save(CONTROL_FILE, data)
        return changed


def update_player_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    data.update({"updatedAt": time.time(), "time": now_iso()})
    with LOCK:
        _atomic_save(PLAYER_STATUS_FILE, data)
    return data


def get_player_status() -> dict[str, Any]:
    data = _load(PLAYER_STATUS_FILE, {})
    if not isinstance(data, dict):
        data = {}
    updated = float(data.get("updatedAt") or 0)
    data["connected"] = bool(updated and time.time() - updated <= 12)
    data["stale"] = bool(updated and time.time() - updated > 12)
    data["ageSeconds"] = round(time.time() - updated, 1) if updated else None
    return data


def public_status() -> dict[str, Any]:
    ensure_tts_files()
    config = get_config()
    queue = get_queue()
    history = get_history(50)
    control = get_control()
    runtime = _load(STATUS_FILE, {})
    if not isinstance(runtime, dict):
        runtime = {}
    updated = float(runtime.get("updatedAt") or 0)
    runtime["stale"] = not updated or (time.time() - updated > 15)
    runtime["ageSeconds"] = round(time.time() - updated, 1) if updated else None
    return {
        "config": config,
        "runtime": runtime,
        "control": control,
        "queueLength": len(queue),
        "pending": len([x for x in queue if x.get("status") in {"pending", "retry"}]),
        "ready": len([x for x in queue if x.get("status") == "ready"]),
        "playing": len([x for x in queue if x.get("status") == "playing"]),
        "historyCount": len(get_history(limit=0)),
        "lastHistory": history[-1] if history else None,
        "player": get_player_status()
    }


ensure_tts_files()
