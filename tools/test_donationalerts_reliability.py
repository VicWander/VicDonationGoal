from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.donationalerts.donationalerts_integration import DonationAlertsIntegration
from core.integration_manager import IntegrationManager


def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_row(external_id: int, created_at: str):
    return {
        "id": external_id,
        "username": f"user-{external_id}",
        "amount": external_id,
        "currency": "RUB",
        "message": "test",
        "created_at": created_at,
    }


def create_integration(root: Path, added: list[str]):
    save_json(root / "integrations/donationalerts/donationalerts_config.json", {
        "enabled": True,
        "client_id": "client",
        "client_secret": "secret",
    })
    save_json(root / "integrations/donationalerts/donationalerts_tokens.json", {"access_token": "token"})

    def add_donation(donation):
        added.append(str(donation["externalId"]))
        return {}, True, "Донат добавлен"

    return DonationAlertsIntegration(root, add_donation, load_json, save_json)


def test_remote_baseline_does_not_import_history():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        added: list[str] = []
        integration = create_integration(root, added)
        integration.api_request = lambda *_args, **_kwargs: {
            "data": [api_row(3, "2026-08-25 12:03:00"), api_row(2, "2026-08-25 12:02:00")],
            "links": {"next": None},
        }
        assert integration._catch_up_after_connect() is True
        assert added == []
        state = load_json(integration.catch_up_file, {})
        assert state["lastSeenId"] == "3"
        assert integration.status["catchUp"]["status"] == "baseline_created"


def test_local_checkpoint_imports_only_new_rows_oldest_first():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        save_json(root / "core/data/donations.json", [{
            "source": "donationalerts",
            "externalId": "2",
            "createdAt": "2026-08-25 12:02:00",
        }])
        added: list[str] = []
        integration = create_integration(root, added)
        integration.api_request = lambda *_args, **_kwargs: {
            "data": [
                api_row(4, "2026-08-25 12:04:00"),
                api_row(3, "2026-08-25 12:03:00"),
                api_row(2, "2026-08-25 12:02:00"),
            ],
            "links": {"next": None},
        }
        integration._catch_up_after_connect()
        assert added == ["3", "4"]
        state = load_json(integration.catch_up_file, {})
        assert state["lastSeenId"] == "4"
        assert integration.status["catchUp"]["added"] == 2
        assert integration.status["catchUp"]["checkpointFound"] is True


def test_existing_checkpoint_is_reused():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        added: list[str] = []
        integration = create_integration(root, added)
        save_json(integration.catch_up_file, {
            "schemaVersion": 1,
            "lastSeenId": "4",
            "lastSeenCreatedAt": "2026-08-25 12:04:00",
        })
        integration.api_request = lambda *_args, **_kwargs: {
            "data": [api_row(5, "2026-08-25 12:05:00"), api_row(4, "2026-08-25 12:04:00")],
            "links": {"next": None},
        }
        integration._catch_up_after_connect()
        assert added == ["5"]
        assert load_json(integration.catch_up_file, {})["lastSeenId"] == "5"


def test_old_local_checkpoint_creates_new_baseline_without_bulk_import():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        save_json(root / "core/data/donations.json", [{
            "source": "donationalerts",
            "externalId": "99",
            "createdAt": "2025-01-01 00:00:00",
        }])
        added: list[str] = []
        integration = create_integration(root, added)
        integration.api_request = lambda *_args, **_kwargs: {
            "data": [api_row(5, "2026-08-25 12:05:00"), api_row(4, "2026-08-25 12:04:00")],
            "links": {"next": None},
        }
        integration._catch_up_after_connect()
        assert added == []
        assert load_json(integration.catch_up_file, {})["lastSeenId"] == "5"
        assert integration.status["catchUp"]["status"] == "baseline_reset"


def test_network_failures_are_transient():
    assert DonationAlertsIntegration._is_transient_error(TimeoutError("timed out")) is True
    assert DonationAlertsIntegration._is_transient_error(ConnectionResetError("reset")) is True
    assert DonationAlertsIntegration._is_transient_error(RuntimeError("HTTP 504")) is True
    assert DonationAlertsIntegration._is_transient_error(RuntimeError("DonationAlerts не авторизован")) is False


def test_common_status_keeps_short_outage_yellow_and_long_outage_red():
    manager = IntegrationManager.__new__(IntegrationManager)
    short_outage = manager._common_state(
        enabled=True,
        configured=True,
        running=True,
        connected=False,
        status={"status": "reconnecting", "lastError": None},
    )
    long_outage = manager._common_state(
        enabled=True,
        configured=True,
        running=True,
        connected=False,
        status={"status": "outage", "lastError": "timeout"},
    )
    assert short_outage == "degraded"
    assert long_outage == "error"


def main():
    tests = [
        test_remote_baseline_does_not_import_history,
        test_local_checkpoint_imports_only_new_rows_oldest_first,
        test_existing_checkpoint_is_reused,
        test_old_local_checkpoint_creates_new_baseline_without_bulk_import,
        test_network_failures_are_transient,
        test_common_status_keeps_short_outage_yellow_and_long_outage_red,
    ]
    for test in tests:
        test()
    print(f"DonationAlerts reliability tests passed: {len(tests)}/{len(tests)}")


if __name__ == "__main__":
    main()
