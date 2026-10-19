from __future__ import annotations

import base64
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import portability


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sample_project(root: Path) -> None:
    (root / "VERSION").write_text("1.4.4.1\n", encoding="utf-8")
    write_json(root / "core/data/state.json", {"title": "Test", "goal": 1000, "current": 100, "currency": "RUB"})
    write_json(root / "core/data/rates.json", {"baseCurrency": "RUB", "ratesToRUB": {"RUB": 1}})
    write_json(root / "core/data/donations.json", [{"uniqueKey": "manual:1", "amount": 100, "source": "manual"}])
    write_json(root / "core/data/donor_profiles.json", [{"id": "donor-1", "displayName": "Test", "aliases": []}])
    write_json(root / "core/data/donor_adjustments.json", [])
    write_json(root / "integrations/donationalerts/donationalerts_config.json", {"enabled": True, "client_id": "private"})
    write_json(root / "integrations/donationalerts/donationalerts_tokens.json", {"access_token": "secret"})
    write_json(root / "integrations/streamerbot/streamerbot_config.json", {"enabled": True, "action_id": "abc"})
    write_json(root / "integrations/streamerbot/donation_event_rules.json", {"rules": []})
    write_json(root / "integrations/tts/tts_config.json", {"enabled": True, "activeProvider": "speakerbot"})
    write_json(root / "integrations/tts/tts_profiles.json", [])
    write_json(root / "integrations/tts/tts_rules.json", [])
    write_json(root / "integrations/tts/tts_history.json", [])
    (root / "integrations/tts/audio_cache").mkdir(parents=True, exist_ok=True)
    (root / "integrations/tts/audio_cache/temporary.mp3").write_bytes(b"not-user-data")


def identity_normalize(item: dict) -> dict:
    result = dict(item)
    result.setdefault("uniqueKey", f"{result.get('source', 'manual')}:{result.get('externalId', 'unknown')}")
    result.setdefault("amountForTop", result.get("amount", 0))
    return result


def test_backup_roundtrip(temp_root: Path) -> None:
    sample_project(temp_root)
    payload, manifest = portability.create_backup_bytes(temp_root, reason="test")
    assert manifest["schemaVersion"] == portability.BACKUP_SCHEMA_VERSION
    assert manifest["containsSecrets"] is True
    assert "integrations/tts/audio_cache/temporary.mp3" not in {item["path"] for item in manifest["files"]}
    preview = portability.backup_preview(payload, "1.4.5")
    assert preview["compatible"] is True
    assert preview["categories"]["streamerbot"] >= 2
    assert preview["categories"]["tts"] >= 4

    write_json(temp_root / "core/data/donations.json", [])
    _manifest, files = portability.inspect_backup_bytes(payload)
    restored = portability.apply_payload(temp_root, files)
    assert "core/data/donations.json" in restored
    donations = json.loads((temp_root / "core/data/donations.json").read_text(encoding="utf-8"))
    assert donations[0]["uniqueKey"] == "manual:1"


def test_folder_and_schema(temp_root: Path) -> None:
    donation_bytes = json.dumps([{"uniqueKey": "manual:2", "amount": 50, "source": "manual"}]).encode("utf-8")
    config_bytes = json.dumps({"enabled": False, "token": "secret"}).encode("utf-8")
    request_files = [
        {"path": "VicDonationGoal-old/core/data/donations.json", "content": base64.b64encode(donation_bytes).decode("ascii")},
        {"path": "VicDonationGoal-old/integrations/donatty/donatty_config.json", "content": base64.b64encode(config_bytes).decode("ascii")},
    ]
    payload = portability.folder_payload_from_request(request_files)
    assert set(payload) == {"core/data/donations.json", "integrations/donatty/donatty_config.json"}
    preview = portability.folder_preview(payload, "1.4.5", "1.4.4.1")
    assert preview["compatible"] is True
    try:
        portability.folder_preview(payload, "1.4.5", "2.0.0")
    except portability.PortabilityError:
        pass
    else:
        raise AssertionError("Новая major-версия должна отклоняться")

    invalid = [{"path": "old/core/data/donations.json", "content": base64.b64encode(b"{}").decode("ascii")}]
    try:
        portability.folder_payload_from_request(invalid)
    except portability.PortabilityError:
        pass
    else:
        raise AssertionError("donations.json с неверным корневым типом должен отклоняться")


def test_donations_merge() -> None:
    existing = [{"uniqueKey": "manual:1", "amount": 100, "source": "manual", "includeInGoal": True}]
    incoming = [
        {"uniqueKey": "manual:1", "amount": 100, "source": "manual"},
        {"uniqueKey": "donationalerts:2", "amount": 250, "source": "donationalerts"},
    ]
    preview = portability.donation_preview(incoming, existing, identity_normalize)
    assert preview["newCount"] == 1 and preview["duplicateCount"] == 1
    merged, stats = portability.merge_donations(incoming, existing, identity_normalize)
    assert stats == {"added": 1, "duplicates": 1, "invalid": 0}
    imported = next(item for item in merged if item["uniqueKey"] == "donationalerts:2")
    assert imported["includeInGoal"] is False
    assert imported["notifyStreamerBot"] is False
    assert imported["speakTTS"] is False


def test_donationalerts_table() -> None:
    html = """<!doctype html><html><body><table>
    <tr><th>Имя пользователя</th><th>Сумма</th><th>Валюта</th></tr>
    <tr><td>Viewer</td><td>1234,50</td><td>RUB</td></tr>
    <tr><td>Аноним</td><td>500</td><td>RUB</td></tr>
    </table></body></html>""".encode("utf-8")
    rows = portability.parse_donationalerts_table(html)
    assert rows == [{"username": "Viewer", "amount": 1234.5}, {"username": "Аноним", "amount": 500.0}]


def test_tampered_backup(temp_root: Path) -> None:
    payload, _manifest = portability.create_backup_bytes(temp_root, reason="tamper-test")
    source = zipfile.ZipFile(io.BytesIO(payload))
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "data/core/data/state.json":
                content = b'{"title":"tampered"}'
            target.writestr(item, content)
    try:
        portability.inspect_backup_bytes(output.getvalue())
    except portability.PortabilityError:
        pass
    else:
        raise AssertionError("Изменённый архив должен отклоняться по контрольной сумме")


def test_server_apply_pipeline(temp_root: Path) -> None:
    app_root = temp_root / "app"
    shutil.copytree(
        ROOT,
        app_root,
        ignore=shutil.ignore_patterns("__pycache__", "runtime", "diagnostics", "backups", "integration_inspector_reports", "audio_cache"),
    )
    sys.path[:0] = [str(app_root), str(app_root / "core"), str(app_root / "integrations" / "tts")]
    spec = importlib.util.spec_from_file_location("vic_portability_server_test", app_root / "core/server.py")
    server = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(server)

    original = json.loads((app_root / "core/data/donations.json").read_text(encoding="utf-8"))
    new_row = {
        "source": "manual",
        "externalId": "portability-pipeline-test",
        "uniqueKey": "manual:portability-pipeline-test",
        "username": "Portability Test",
        "amount": 321,
        "currency": "RUB",
        "message": "offline test",
    }
    raw = json.dumps([new_row], ensure_ascii=False).encode("utf-8")
    token = server.portability.create_stage(app_root, "donations", "donations.json", raw, {"kind": "donations"})
    result = server.apply_staged_import(token, {"includeInGoal": False})
    assert result["ok"] is True and result["added"] == 1
    imported = json.loads((app_root / "core/data/donations.json").read_text(encoding="utf-8"))
    assert len(imported) == len(original) + 1
    assert next(item for item in imported if item.get("uniqueKey") == new_row["uniqueKey"])["includeInGoal"] is False
    assert list((app_root / "backups/automatic").glob("*.zip"))

    da_html = """<table><tr><th>Имя пользователя</th><th>Сумма</th></tr>
    <tr><td>PortabilityDAUser</td><td>1234,50</td></tr></table>""".encode("utf-8")
    da_rows = server.portability.parse_donationalerts_table(da_html)
    preview = server.donationalerts_import_preview(da_rows, imported)
    import_key = preview["items"][0]["importKey"]
    token = server.portability.create_stage(app_root, "donationalerts", "donations.xls", da_html, preview)
    result = server.apply_staged_import(token, {"selectedKeys": [import_key]})
    assert result["ok"] is True and result["profilesProcessed"] == 1
    snapshots = [item for item in server.donor_store.load_adjustments() if item.get("snapshotKey") == import_key]
    assert len(snapshots) == 1 and snapshots[0]["amountForTop"] == 1234.5

    preview = server.donationalerts_import_preview(da_rows, imported)
    token = server.portability.create_stage(app_root, "donationalerts", "donations.xls", da_html, preview)
    server.apply_staged_import(token, {"selectedKeys": [import_key]})
    snapshots = [item for item in server.donor_store.load_adjustments() if item.get("snapshotKey") == import_key]
    assert len(snapshots) == 1 and snapshots[0]["amountForTop"] == 1234.5

    backup_bytes, backup_manifest = server.portability.create_backup_bytes(app_root, reason="pipeline-restore")
    write_json(app_root / "core/data/donations.json", [])
    restore_preview = server.portability.backup_preview(backup_bytes, server.APP_VERSION)
    token = server.portability.create_stage(app_root, "backup", "backup.zip", backup_bytes, restore_preview)
    result = server.apply_staged_import(token)
    assert result["ok"] is True and result["restartRequired"] is True
    restored = json.loads((app_root / "core/data/donations.json").read_text(encoding="utf-8"))
    assert any(item.get("uniqueKey") == new_row["uniqueKey"] for item in restored)
    assert backup_manifest["schemaVersion"] == server.portability.BACKUP_SCHEMA_VERSION

    before_failure = (app_root / "core/data/donations.json").read_bytes()
    token = server.portability.create_stage(app_root, "unknown", "invalid.bin", b"invalid", {"kind": "unknown"})
    try:
        server.apply_staged_import(token)
    except server.portability.PortabilityError as error:
        assert "автоматически восстановлены" in str(error)
    else:
        raise AssertionError("Неизвестный импорт должен завершаться ошибкой и откатом")
    assert (app_root / "core/data/donations.json").read_bytes() == before_failure


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vic_portability_test_") as temp:
        root = Path(temp)
        test_backup_roundtrip(root)
        test_folder_and_schema(root)
        test_tampered_backup(root)
        test_server_apply_pipeline(root)
    test_donations_merge()
    test_donationalerts_table()
    print("Portability tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
