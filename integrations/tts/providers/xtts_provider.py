from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .base_provider import BaseTTSProvider, TTSProviderError


class XTTSHTTPProvider(BaseTTSProvider):
    """Adapter for a separately running XTTS-compatible HTTP server.

    By default sends multipart/form-data fields `text`, `language`, and optional
    `speaker_wav`. The model and its weights are not bundled with VicDonationGoal.
    """

    name = "xtts"
    default_extension = "wav"

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
        if not str(settings.get("endpoint") or "").strip():
            return False, "Не указан адрес локального XTTS-сервера"
        speaker_wav = str(settings.get("speakerWav") or settings.get("speaker_wav") or "").strip()
        if speaker_wav and not Path(speaker_wav).expanduser().exists():
            return False, f"Не найден XTTS reference WAV: {speaker_wav}"
        return True, ""

    def synthesize(self, text: str, output_path: Path, settings: dict[str, Any]) -> None:
        requests = self._requests()
        endpoint = str(settings.get("endpoint") or "").strip()
        language = str(settings.get("language") or "ru")
        speaker_wav = str(settings.get("speakerWav") or settings.get("speaker_wav") or "").strip()
        timeout = max(15, int(float(settings.get("timeoutSeconds") or settings.get("timeout_seconds") or 180)))
        headers = settings.get("headers") if isinstance(settings.get("headers"), dict) else {}
        response_type = str(settings.get("responseType") or "audio")

        data = {
            str(settings.get("textField") or settings.get("text_field") or "text"): text,
            str(settings.get("languageField") or settings.get("language_field") or "language"): language,
        }
        files = None
        file_handle = None
        try:
            if speaker_wav:
                file_path = Path(speaker_wav).expanduser()
                file_handle = file_path.open("rb")
                files = {
                    str(settings.get("speakerField") or settings.get("speaker_field") or "speaker_wav"): (
                        file_path.name,
                        file_handle,
                        "audio/wav",
                    )
                }
            response = requests.post(
                endpoint,
                data=data,
                files=files,
                headers={str(key): str(value) for key, value in headers.items()},
                timeout=timeout,
            )
        except Exception as error:
            raise TTSProviderError(f"XTTS connection error: {type(error).__name__}: {error}") from error
        finally:
            if file_handle is not None:
                file_handle.close()

        if not response.ok:
            details = response.text[:1000] if response.text else "<empty response>"
            raise TTSProviderError(f"XTTS HTTP {response.status_code}: {details}")

        if response_type == "json_url":
            try:
                payload = response.json()
                audio_url = str(payload.get(str(settings.get("audioUrlField") or "audioUrl")) or "")
                audio_response = requests.get(urljoin(endpoint, audio_url), timeout=timeout)
                audio_response.raise_for_status()
                audio = audio_response.content
            except Exception as error:
                raise TTSProviderError(f"XTTS не вернул корректный URL аудио: {error}") from error
        elif response_type == "json_base64":
            try:
                payload = response.json()
                encoded = str(payload.get(str(settings.get("audioBase64Field") or "audio")) or "")
                audio = base64.b64decode(encoded.split(",", 1)[-1])
            except Exception as error:
                raise TTSProviderError(f"XTTS не вернул корректное base64-аудио: {error}") from error
        else:
            audio = response.content

        if not audio:
            raise TTSProviderError("XTTS вернул пустой аудиофайл")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)
