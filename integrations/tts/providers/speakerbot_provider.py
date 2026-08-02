from __future__ import annotations

import json
import uuid
from typing import Any

from .base_provider import TTSProviderError


class SpeakerBotProvider:
    name = "speakerbot"

    @staticmethod
    def _websocket():
        try:
            import websocket
        except ImportError as error:
            raise TTSProviderError(
                "Не установлен websocket-client. Запусти 00_INSTALL_ALL.bat"
            ) from error
        return websocket

    def validate(self, settings: dict[str, Any]) -> tuple[bool, str]:
        try:
            self._websocket()
        except TTSProviderError as error:
            return False, str(error)
        url = str(settings.get("websocketUrl") or "").strip()
        if not url.startswith(("ws://", "wss://")):
            return False, "У Speaker.bot не указан корректный websocketUrl"
        return True, ""

    def health_check(self, settings: dict[str, Any]) -> tuple[bool, str]:
        websocket = self._websocket()
        url = str(settings.get("websocketUrl") or "ws://127.0.0.1:7580/")
        timeout = max(1, float(settings.get("connectTimeoutSeconds") or 4))
        ws = None
        try:
            ws = websocket.create_connection(url, timeout=timeout)
            return True, ""
        except Exception as error:
            return False, f"{type(error).__name__}: {error}"
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def request(self, request_name: str, settings: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        websocket = self._websocket()
        url = str(settings.get("websocketUrl") or "ws://127.0.0.1:7580/")
        connect_timeout = max(1, float(settings.get("connectTimeoutSeconds") or 4))
        response_timeout = max(0.2, float(settings.get("responseTimeoutSeconds") or 2))

        request_id = str(kwargs.pop("id", None) or uuid.uuid4())
        payload = {
            "id": request_id,
            "request": request_name
        }
        payload.update(kwargs)

        ws = None
        try:
            ws = websocket.create_connection(url, timeout=connect_timeout)
            ws.settimeout(response_timeout)
            ws.send(json.dumps(payload, ensure_ascii=False))

            response = None
            try:
                raw = ws.recv()
                if raw:
                    try:
                        response = json.loads(raw)
                    except Exception:
                        response = {"raw": str(raw)}
            except websocket.WebSocketTimeoutException:
                response = None

            if isinstance(response, dict):
                success = response.get("success")
                status = str(response.get("status") or "").lower()
                if success is False or status in {"error", "failed", "failure"}:
                    raise TTSProviderError(
                        str(response.get("message") or response.get("error") or response)
                    )

            return {
                "ok": True,
                "requestId": request_id,
                "response": response,
                "payload": payload
            }
        except Exception as error:
            if isinstance(error, TTSProviderError):
                raise
            raise TTSProviderError(
                f"Speaker.bot WebSocket: {type(error).__name__}: {error}"
            ) from error
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def speak(
        self,
        text: str,
        settings: dict[str, Any],
        voice_alias: str,
        bad_word_filter: bool = False,
        request_id: str | None = None
    ) -> dict[str, Any]:
        alias = str(voice_alias or settings.get("defaultVoiceAlias") or "").strip()
        if not alias:
            raise TTSProviderError(
                "Не указан Voice Alias Speaker.bot. Создай alias и укажи его в профиле."
            )
        return self.request(
            "Speak",
            settings,
            id=request_id or str(uuid.uuid4()),
            voice=alias,
            message=str(text),
            badWordFilter=bool(bad_word_filter)
        )

    def control(self, action: str, settings: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "pause": "Pause",
            "resume": "Resume",
            "stop": "Stop",
            "clear": "Clear",
            "enable": "Enable",
            "disable": "Disable"
        }
        request_name = mapping.get(str(action or "").lower())
        if not request_name:
            raise TTSProviderError(f"Неизвестная команда Speaker.bot: {action}")
        return self.request(request_name, settings)
