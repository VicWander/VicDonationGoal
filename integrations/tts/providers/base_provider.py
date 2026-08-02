from __future__ import annotations

from pathlib import Path
from typing import Any


class TTSProviderError(RuntimeError):
    """Понятная ошибка конкретного TTS-провайдера."""


class BaseTTSProvider:
    name = "base"
    default_extension = "mp3"

    def validate(self, settings: dict[str, Any]) -> tuple[bool, str]:
        return True, ""

    def output_extension(self, settings: dict[str, Any]) -> str:
        extension = str(settings.get("output_format") or self.default_extension).strip().lower()
        return extension.lstrip(".") or self.default_extension

    def synthesize(self, text: str, output_path: Path, settings: dict[str, Any]) -> None:
        raise NotImplementedError

    def list_voices(self, settings: dict[str, Any], locale_prefix: str = "") -> list[dict[str, Any]]:
        return []
