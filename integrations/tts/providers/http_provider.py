from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .base_provider import BaseTTSProvider, TTSProviderError


def _replace_templates(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for key, replacement in replacements.items():
            result = result.replace(key, replacement)
        return result
    if isinstance(value, list):
        return [_replace_templates(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_templates(item, replacements) for key, item in value.items()}
    return value


def _get_path(data: Any, path: str) -> Any:
    current = data
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


class GenericHTTPProvider(BaseTTSProvider):
    """Universal local/cloud HTTP TTS adapter.

    Supported response types:
      - audio: raw audio bytes in response body;
      - json_url: JSON contains a URL to an audio file;
      - json_base64: JSON contains base64-encoded audio.
    """

    name = "http"
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
        if not str(settings.get("url") or "").strip():
            return False, "Не указан URL Custom HTTP TTS"
        method = str(settings.get("method") or "POST").upper()
        if method not in {"GET", "POST", "PUT", "PATCH"}:
            return False, f"Неподдерживаемый HTTP-метод: {method}"
        response_type = str(settings.get("responseType") or settings.get("response_type") or "audio")
        if response_type not in {"audio", "json_url", "json_base64"}:
            return False, f"Неподдерживаемый responseType: {response_type}"
        return True, ""

    def synthesize(self, text: str, output_path: Path, settings: dict[str, Any]) -> None:
        requests = self._requests()
        url = str(settings.get("url") or "").strip()
        method = str(settings.get("method") or "POST").upper()
        body_type = str(settings.get("bodyType") or settings.get("body_type") or "json").lower()
        response_type = str(settings.get("responseType") or settings.get("response_type") or "audio")
        headers = settings.get("headers") if isinstance(settings.get("headers"), dict) else {}
        body = settings.get("body") if isinstance(settings.get("body"), dict) else {"text": "{text}"}
        timeout = max(5, int(float(settings.get("timeoutSeconds") or settings.get("timeout_seconds") or 60)))

        replacements = {
            "{text}": text,
            "{voice}": str(settings.get("voice") or ""),
            "{language}": str(settings.get("language") or "ru"),
        }
        body = _replace_templates(body, replacements)
        safe_headers = {
            str(key): _replace_templates(str(value), replacements)
            for key, value in headers.items()
        }

        kwargs: dict[str, Any] = {"headers": safe_headers, "timeout": timeout}
        if method == "GET":
            kwargs["params"] = body
        elif body_type == "form":
            kwargs["data"] = body
        else:
            kwargs["json"] = body

        try:
            response = requests.request(method, url, **kwargs)
        except Exception as error:
            raise TTSProviderError(
                f"Custom HTTP connection error: {type(error).__name__}: {error}"
            ) from error

        if not response.ok:
            details = response.text[:1000] if response.text else "<empty response>"
            raise TTSProviderError(f"Custom HTTP {response.status_code}: {details}")

        audio: bytes
        if response_type == "audio":
            audio = response.content
        else:
            try:
                payload = response.json()
            except Exception as error:
                raise TTSProviderError("Custom HTTP ожидал JSON, но получил другой ответ") from error

            if response_type == "json_url":
                field = str(settings.get("audioUrlField") or settings.get("audio_url_field") or "audioUrl")
                audio_url = str(_get_path(payload, field) or "").strip()
                if not audio_url:
                    raise TTSProviderError(f"В JSON не найден URL аудио по пути: {field}")
                audio_url = urljoin(url, audio_url)
                try:
                    audio_response = requests.get(audio_url, headers=safe_headers, timeout=timeout)
                    audio_response.raise_for_status()
                    audio = audio_response.content
                except Exception as error:
                    raise TTSProviderError(f"Не удалось скачать аудио: {error}") from error
            else:
                field = str(settings.get("audioBase64Field") or settings.get("audio_base64_field") or "audio")
                encoded = _get_path(payload, field)
                if not encoded:
                    raise TTSProviderError(f"В JSON не найден base64 по пути: {field}")
                try:
                    value = str(encoded)
                    if "," in value and value.lower().startswith("data:"):
                        value = value.split(",", 1)[1]
                    audio = base64.b64decode(value)
                except Exception as error:
                    raise TTSProviderError("Не удалось декодировать base64-аудио") from error

        if not audio:
            raise TTSProviderError("Custom HTTP вернул пустой аудиофайл")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)
