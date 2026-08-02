from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .base_provider import BaseTTSProvider, TTSProviderError


class EdgeTTSProvider(BaseTTSProvider):
    name = "edge"
    default_extension = "mp3"

    @staticmethod
    def _import_edge_tts():
        try:
            import edge_tts
        except ImportError as error:
            raise TTSProviderError(
                "Не установлен edge-tts. Запусти 00_INSTALL_ALL.bat "
                "или: py -3 -m pip install edge-tts"
            ) from error
        return edge_tts

    def validate(self, settings: dict[str, Any]) -> tuple[bool, str]:
        try:
            self._import_edge_tts()
        except TTSProviderError as error:
            return False, str(error)

        if not str(settings.get("voice") or "").strip():
            return False, "В providers.edge.voice не указан голос"

        return True, ""

    def output_extension(self, settings: dict[str, Any]) -> str:
        # Edge endpoint отдаёт MP3; расширение фиксируем, чтобы Browser Source
        # всегда получал корректный тип файла.
        return "mp3"

    def synthesize(self, text: str, output_path: Path, settings: dict[str, Any]) -> None:
        edge_tts = self._import_edge_tts()

        voice = str(settings.get("voice") or "ru-RU-SvetlanaNeural")
        rate = str(settings.get("rate") or "+0%")
        volume = str(settings.get("volume") or "+0%")
        pitch = str(settings.get("pitch") or "+0Hz")
        proxy = str(settings.get("proxy") or "").strip() or None

        connect_timeout = max(3, int(float(settings.get("connect_timeout_seconds") or 10)))
        receive_timeout = max(10, int(float(settings.get("receive_timeout_seconds") or 60)))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_name(output_path.name + ".part")

        try:
            if temp_path.exists():
                temp_path.unlink()

            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
                proxy=proxy,
                connect_timeout=connect_timeout,
                receive_timeout=receive_timeout,
            )
            communicate.save_sync(str(temp_path))

            if not temp_path.exists() or temp_path.stat().st_size <= 0:
                raise TTSProviderError("Edge TTS не создал аудиофайл")

            temp_path.replace(output_path)
        except Exception as error:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if isinstance(error, TTSProviderError):
                raise
            raise TTSProviderError(f"Edge TTS: {type(error).__name__}: {error}") from error

    def list_voices(self, settings: dict[str, Any], locale_prefix: str = "") -> list[dict[str, Any]]:
        edge_tts = self._import_edge_tts()
        proxy = str(settings.get("proxy") or "").strip() or None

        try:
            voices = asyncio.run(edge_tts.list_voices(proxy=proxy))
        except Exception as error:
            raise TTSProviderError(
                f"Не удалось получить список голосов Edge TTS: {type(error).__name__}: {error}"
            ) from error

        prefix = str(locale_prefix or "").strip().lower()
        result = []
        for voice in voices:
            short_name = str(voice.get("ShortName") or voice.get("Name") or "")
            locale = str(voice.get("Locale") or "")
            if prefix and not (short_name.lower().startswith(prefix) or locale.lower().startswith(prefix)):
                continue
            result.append(voice)

        return sorted(result, key=lambda item: str(item.get("ShortName") or item.get("Name") or ""))
