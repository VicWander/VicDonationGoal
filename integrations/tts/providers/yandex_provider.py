from __future__ import annotations

from pathlib import Path
from typing import Any

from .base_provider import BaseTTSProvider, TTSProviderError


class YandexSpeechKitProvider(BaseTTSProvider):
    """Yandex SpeechKit REST API v1 provider.

    Supports API key and IAM token authentication. The provider sends form data
    to the synchronous SpeechKit synthesis endpoint and expects audio bytes.
    """

    name = "yandex"
    default_extension = "mp3"

    @staticmethod
    def _requests():
        try:
            import requests
        except ImportError as error:
            raise TTSProviderError("Не установлен requests. Запусти 00_INSTALL_ALL.bat") from error
        return requests

    def validate(self, settings: dict[str, Any]) -> tuple[bool, str]:
        try:
            self._requests()
        except TTSProviderError as error:
            return False, str(error)

        auth_mode = str(settings.get("authMode") or "api_key").strip().lower()
        if auth_mode == "iam_token":
            if not str(settings.get("iamToken") or "").strip():
                return False, "Не указан IAM token Yandex SpeechKit"
        elif not str(settings.get("apiKey") or "").strip():
            return False, "Не указан API key Yandex SpeechKit"

        if not str(settings.get("folderId") or "").strip():
            return False, "Не указан Folder ID Yandex Cloud"
        if not str(settings.get("voice") or "").strip():
            return False, "Не указан голос Yandex SpeechKit"
        return True, ""

    def output_extension(self, settings: dict[str, Any]) -> str:
        fmt = str(settings.get("format") or settings.get("output_format") or "mp3").lower()
        mapping = {"oggopus": "ogg", "lpcm": "wav", "wav": "wav", "mp3": "mp3"}
        return mapping.get(fmt, fmt.lstrip(".") or "mp3")

    def synthesize(self, text: str, output_path: Path, settings: dict[str, Any]) -> None:
        requests = self._requests()
        endpoint = str(
            settings.get("endpoint")
            or "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
        ).strip()
        auth_mode = str(settings.get("authMode") or "api_key").strip().lower()
        if auth_mode == "iam_token":
            token = str(settings.get("iamToken") or "").strip()
            authorization = f"Bearer {token}"
        else:
            token = str(settings.get("apiKey") or "").strip()
            authorization = f"Api-Key {token}"

        data: dict[str, Any] = {
            "text": text,
            "lang": str(settings.get("lang") or "ru-RU"),
            "voice": str(settings.get("voice") or "marina"),
            "speed": str(settings.get("speed") or "1.0"),
            "format": str(settings.get("format") or "mp3"),
            "folderId": str(settings.get("folderId") or ""),
        }
        emotion = str(settings.get("emotion") or "").strip()
        if emotion:
            data["emotion"] = emotion

        timeout = max(10, int(float(settings.get("timeoutSeconds") or 60)))
        try:
            response = requests.post(
                endpoint,
                headers={"Authorization": authorization},
                data=data,
                timeout=timeout,
            )
        except Exception as error:
            raise TTSProviderError(
                f"Yandex SpeechKit connection error: {type(error).__name__}: {error}"
            ) from error

        if not response.ok:
            details = response.text[:1000] if response.text else "<empty response>"
            raise TTSProviderError(f"Yandex SpeechKit HTTP {response.status_code}: {details}")
        if not response.content:
            raise TTSProviderError("Yandex SpeechKit вернул пустой аудиофайл")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
