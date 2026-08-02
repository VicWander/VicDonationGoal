from __future__ import annotations

import importlib.util
import json
import py_compile
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from source_registry import AUTOMATIC_SOURCE_IDS
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "dev"

ERRORS = []
WARNINGS = []
OK = []


def ok(message):
    OK.append(message)
    print(f"[ OK ] {message}")


def warn(message):
    WARNINGS.append(message)
    print(f"[WARN] {message}")


def error(message):
    ERRORS.append(message)
    print(f"[ERR ] {message}")


def read_json(relative, expected_type=None, private=False):
    path = ROOT / relative
    if not path.exists():
        warn(f"Нет файла {relative}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        error(f"Некорректный JSON {relative}: {type(exc).__name__}: {exc}")
        return None
    if expected_type and not isinstance(data, expected_type):
        error(f"Неверный тип данных в {relative}: ожидался {expected_type.__name__}")
        return None
    ok(f"JSON читается: {relative}")
    return data


def check_file(relative):
    path = ROOT / relative
    if path.exists() and path.is_file():
        ok(f"Файл найден: {relative}")
    else:
        error(f"Нет обязательного файла: {relative}")


def check_python(relative):
    path = ROOT / relative
    try:
        py_compile.compile(str(path), doraise=True)
        ok(f"Python синтаксис: {relative}")
    except Exception as exc:
        error(f"Python ошибка в {relative}: {exc}")


def placeholder(value):
    text = str(value or "")
    return not text or "ВСТАВЬ" in text or "PASTE_" in text


print("=" * 60)
print(f" VicDonationGoal v{VERSION} — Stability Check")
print("=" * 60)
print()

for relative in [
    "core/server.py",
    "core/donor_store.py",
    "core/integration_manager.py",
    "core/public/admin.html",
    "core/public/integrations-admin.js",
    "core/public/widget.html",
    "integrations/donatty/donatty_listener.py",
    "integrations/streamelements/streamelements_listener.py",
    "integrations/streamlabs/streamlabs_integration.py",
    "integrations/donatty/manifest.json",
    "integrations/donatty/GUIDE.md",
    "integrations/streamelements/streamelements_listener.py",
    "integrations/streamelements/manifest.json",
    "integrations/streamelements/GUIDE.md",
    "integrations/streamlabs/streamlabs_integration.py",
    "integrations/streamlabs/manifest.json",
    "integrations/streamlabs/GUIDE.md",
    "integrations/donationalerts/donationalerts_integration.py",
    "integrations/donationalerts/manifest.json",
    "integrations/donationalerts/GUIDE.md",
    "integrations/streamerbot/streamerbot_bridge.py",
    "integrations/tts/tts_hub.py",
    "core/tts_hub_store.py",
    "core/public/tts-admin.js",
    "core/public/tts.html",
    "docs/MANUAL.md",
    "docs/index.html",
    "integrations/tts/providers/speakerbot_provider.py",
    "integrations/tts/providers/edge_provider.py",
    "integrations/tts/providers/yandex_provider.py",
    "integrations/tts/providers/xtts_provider.py",
    "integrations/tts/providers/http_provider.py",
    "safe_json.py",
    "tools/stop_all.py",
    "tools/install_cloudflared.py",
    "13_STOP_ALL.bat",
    "integrations/donatepay/donatepay_listener.py",
    "integrations/donatex/donatex_listener.py",
    "integrations/tribute/tribute_tunnel.py",
    "source_registry.py",
    "tools/create_diagnostic_report.py",
    "tools/beta_readiness_check.py",
    "14_CREATE_DIAGNOSTIC_REPORT.bat",
    "15_BETA_READINESS_CHECK.bat",
]:
    check_file(relative)

for relative in [
    "core/server.py",
    "core/donor_store.py",
    "core/integration_manager.py",
    "integrations/donationalerts/donationalerts_integration.py",
    "integrations/donatty/donatty_listener.py",
    "integrations/streamelements/streamelements_listener.py",
    "integrations/streamlabs/streamlabs_integration.py",
    "integrations/streamerbot/streamerbot_bridge.py",
    "integrations/tts/tts_hub.py",
    "core/tts_hub_store.py",
    "integrations/tts/providers/speakerbot_provider.py",
    "integrations/tts/providers/edge_provider.py",
    "integrations/tts/providers/yandex_provider.py",
    "integrations/tts/providers/xtts_provider.py",
    "integrations/tts/providers/http_provider.py",
    "safe_json.py",
    "tools/stop_all.py",
    "tools/install_cloudflared.py",
    "integrations/donatepay/donatepay_listener.py",
    "integrations/donatex/donatex_listener.py",
    "integrations/tribute/tribute_tunnel.py",
    "source_registry.py",
    "tools/create_diagnostic_report.py",
    "tools/beta_readiness_check.py",
]:
    check_python(relative)

# Import/runtime smoke test catches missing helper imports that py_compile cannot detect.
try:
    code = (
        "import sys; from pathlib import Path; "
        f"root=Path({str(ROOT)!r}); "
        "sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'integrations'/'tts')); "
        "import tts_hub; tts_hub.load_sent(); print('ok')"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=25)
    if result.returncode == 0:
        ok("TTS Hub runtime import/load_sent: успешно")
    else:
        error("TTS Hub runtime import: " + (result.stderr or result.stdout).strip()[-500:])
except Exception as exc:
    error(f"TTS Hub runtime smoke test: {type(exc).__name__}: {exc}")

state = read_json("core/data/state.json", dict)
donations = read_json("core/data/donations.json", list)
rates = read_json("core/data/rates.json", dict)
donor_profiles = read_json("core/data/donor_profiles.json", list)
donor_adjustments = read_json("core/data/donor_adjustments.json", list)
da = read_json("integrations/donationalerts/donationalerts_config.json", dict, private=True)
donatty = read_json("integrations/donatty/donatty_config.json", dict, private=True)
streamelements = read_json("integrations/streamelements/streamelements_config.json", dict, private=True)
streamlabs = read_json("integrations/streamlabs/streamlabs_config.json", dict, private=True)
donatepay = read_json("integrations/donatepay/donatepay_config.json", dict, private=True)
donatex = read_json("integrations/donatex/donatex_config.json", dict, private=True)
tribute = read_json("integrations/tribute/tribute_config.json", dict, private=True)
da_manifest = read_json("integrations/donationalerts/manifest.json", dict)
donatty_manifest = read_json("integrations/donatty/manifest.json", dict)
streamelements_manifest = read_json("integrations/streamelements/manifest.json", dict)
streamlabs_manifest = read_json("integrations/streamlabs/manifest.json", dict)
onboarding = read_json("integrations/integrations_onboarding.json", dict)
sb = read_json("integrations/streamerbot/streamerbot_config.json", dict, private=True)
rules = read_json("integrations/streamerbot/donation_event_rules.json", dict, private=True)
tts = read_json("integrations/tts/tts_config.json", dict, private=True)
tts_profiles = read_json("integrations/tts/tts_profiles.json", list, private=True)
tts_rules = read_json("integrations/tts/tts_rules.json", list, private=True)
tts_history = read_json("integrations/tts/tts_history.json", list, private=True)

if state:
    for field in ("title", "goal", "currency"):
        if field not in state:
            error(f"state.json: нет поля {field}")
    if "current" in state:
        ok("state.json содержит текущий прогресс")

if donations is not None:
    ok(f"История донатов: {len(donations)} записей")
    top_ready = sum(1 for item in donations if isinstance(item, dict) and "includeInTop" in item and "donorId" in item)
    ok(f"TopDonation fields: {top_ready}/{len(donations)} записей")

if donor_profiles is not None:
    ok(f"Профили донатеров: {len(donor_profiles)}")
    ids = [str(item.get("id") or "") for item in donor_profiles if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        error("Есть повторяющиеся ID профилей донатеров")
    else:
        ok("ID профилей донатеров уникальны")
if donor_adjustments is not None:
    ok(f"Корректировки TopDonation: {len(donor_adjustments)}")

if da:
    if placeholder(da.get("client_id")) or placeholder(da.get("client_secret")):
        warn("DonationAlerts конфиг не заполнен полностью")
    else:
        ok("DonationAlerts конфиг заполнен (секреты не выводятся)")

if donatty:
    if placeholder(donatty.get("widget_url")):
        warn("Donatty widget_url не заполнен")
    else:
        ok("Donatty widget_url заполнен (ссылка не выводится)")


if da_manifest:
    if da_manifest.get("id") != "donationalerts":
        error("DonationAlerts manifest: неверный id")
    else:
        ok("DonationAlerts manifest зарегистрирован")
if donatty_manifest:
    if donatty_manifest.get("id") != "donatty":
        error("Donatty manifest: неверный id")
    else:
        ok("Donatty manifest зарегистрирован")
if onboarding is not None:
    ok(f"Integration onboarding: completed={bool(onboarding.get('completed'))}")

if streamelements:
    if bool(streamelements.get("enabled")) and (placeholder(streamelements.get("channel_id")) or placeholder(streamelements.get("token"))):
        warn("StreamElements включён, но Channel ID/token заполнены не полностью")
    else:
        ok("StreamElements config читается (секрет не выводится)")

if streamlabs:
    if bool(streamlabs.get("enabled")) and (placeholder(streamlabs.get("client_id")) or placeholder(streamlabs.get("client_secret"))):
        warn("Streamlabs включён, но Client ID/Secret заполнены не полностью")
    else:
        ok("Streamlabs config читается (секрет не выводится)")

if streamelements_manifest and streamelements_manifest.get("id") == "streamelements":
    ok("StreamElements manifest зарегистрирован")
else:
    error("StreamElements manifest: неверный id")
if streamlabs_manifest and streamlabs_manifest.get("id") == "streamlabs":
    ok("Streamlabs manifest зарегистрирован")
else:
    error("Streamlabs manifest: неверный id")

if donatepay:
    if bool(donatepay.get("enabled")) and placeholder(donatepay.get("api_key")):
        warn("DonatePay включён, но API key не заполнен")
    else:
        ok("DonatePay config читается; catch-up необязателен")
    if donatepay.get("catch_up_enabled") and int(donatepay.get("catch_up_min_interval_seconds", 0) or 0) < 600:
        warn("DonatePay catch-up interval слишком мал и может вызвать HTTP 429")

if donatex:
    if int(donatex.get("poll_interval_seconds", 0) or 0) < 10:
        warn("DonateX poll interval будет автоматически поднят до 10 секунд")
    else:
        ok("DonateX poll interval безопасный")

if tribute:
    if tribute.get("auto_start_tunnel") and not tribute.get("auto_install_cloudflared", True):
        warn("Tribute auto tunnel включён, но auto-install cloudflared выключен")
    else:
        ok("Tribute cloudflared auto-install настроен")

if (ROOT / "tools/cloudflared.exe").exists():
    warn("cloudflared.exe встроен в сборку; для Beta Readiness рекомендуется установка по запросу")
else:
    ok("cloudflared не встроен и будет установлен только для Tribute")

if sb:
    sources = sb.get("send_sources", [])
    if sources == []:
        ok("Streamer.bot Bridge принимает все автоматические сервисы")
    elif set(map(str.lower, sources)) == {"donationalerts", "donatty"}:
        error("Streamer.bot Bridge использует старый whitelist без новых сервисов")
    if not str(sb.get("action_id") or sb.get("action_name") or "").strip():
        warn("Streamer.bot action не указан")
    else:
        ok("Streamer.bot action настроен")

if rules:
    rule_list = rules.get("rules", []) if isinstance(rules, dict) else []
    ok(f"Donation Event Rules: {len(rule_list)} правил")

if tts:
    tts_sources = {str(x).lower() for x in ((tts.get("donations") or {}).get("sources") or [])}
    expected_sources = set(AUTOMATIC_SOURCE_IDS) | {"manual"}
    missing_sources = sorted(expected_sources - tts_sources) if tts_sources else []
    if missing_sources:
        warn("TTS Hub не включает источники: " + ", ".join(missing_sources))
    else:
        ok("TTS Hub принимает все интеграции" + (" (пустой список = все источники)" if not tts_sources else ""))
    provider = str(tts.get("activeProvider") or "не указан")
    fallback = str(tts.get("fallbackProvider") or "нет")
    enabled = bool(tts.get("enabled", False))
    ok(f"TTS Hub: provider={provider}; fallback={fallback}; enabled={enabled}")

if tts_profiles is not None:
    ok(f"TTS voice profiles: {len(tts_profiles)}")
if tts_rules is not None:
    ok(f"TTS routing rules: {len(tts_rules)}")
if tts_history is not None:
    ok(f"TTS history: {len(tts_history)} записей")

if tts_profiles is not None:
    ids = [str(item.get("id") or "") for item in tts_profiles if isinstance(item, dict)]
    duplicate_ids = sorted({item for item in ids if item and ids.count(item) > 1})
    if duplicate_ids:
        error("Повторяющиеся ID TTS-профилей: " + ", ".join(duplicate_ids))
    else:
        ok("ID TTS-профилей уникальны")

if tts_rules is not None:
    ids = [str(item.get("id") or "") for item in tts_rules if isinstance(item, dict)]
    duplicate_ids = sorted({item for item in ids if item and ids.count(item) > 1})
    if duplicate_ids:
        error("Повторяющиеся ID TTS-правил: " + ", ".join(duplicate_ids))
    else:
        ok("ID TTS-правил уникальны")

    known_profiles = {str(item.get("id") or "") for item in (tts_profiles or []) if isinstance(item, dict)}
    broken = [str(item.get("id") or "?") for item in tts_rules if isinstance(item, dict) and str(item.get("profileId") or "") not in known_profiles]
    if broken:
        error("TTS-правила ссылаются на неизвестные профили: " + ", ".join(broken))
    else:
        ok("Все TTS-правила ссылаются на существующие профили")

if tts:
    providers = tts.get("providers") if isinstance(tts.get("providers"), dict) else {}
    for provider_name in ("speakerbot", "edge", "yandex", "xtts", "http"):
        if provider_name in providers:
            ok(f"TTS provider config найден: {provider_name}")
        else:
            warn(f"Нет секции TTS provider: {provider_name}")

for module in ("requests", "websocket", "playwright", "edge_tts"):
    if importlib.util.find_spec(module) is None:
        warn(f"Python dependency не найдена: {module}")
    else:
        ok(f"Python dependency доступна: {module}")

try:
    with urllib.request.urlopen("http://127.0.0.1:3333/api/health", timeout=2) as response:
        health = json.loads(response.read().decode("utf-8"))
    if health.get("ok"):
        ok(f"Core server отвечает, версия {health.get('version', '?')}")
    else:
        warn("Core server ответил, но health.ok != true")
except Exception:
    warn("Core server сейчас не запущен — это нормально для офлайн-проверки")

print()
print("-" * 60)
print(f"OK: {len(OK)} | WARN: {len(WARNINGS)} | ERR: {len(ERRORS)}")
if ERRORS:
    print("Проверка завершена с ошибками.")
    sys.exit(1)
print("Критических ошибок не найдено.")
sys.exit(0)
