from __future__ import annotations

from typing import Any

from .base_provider import BaseTTSProvider, TTSProviderError
from .edge_provider import EdgeTTSProvider
from .http_provider import GenericHTTPProvider
from .xtts_provider import XTTSHTTPProvider
from .yandex_provider import YandexSpeechKitProvider

_PROVIDER_TYPES = {
    "edge": EdgeTTSProvider,
    "http": GenericHTTPProvider,
    "xtts": XTTSHTTPProvider,
    "yandex": YandexSpeechKitProvider,
}


def create_provider(name: str) -> BaseTTSProvider:
    normalized = str(name or "").strip().lower()
    provider_type = _PROVIDER_TYPES.get(normalized)
    if provider_type is None:
        raise TTSProviderError(
            f"Неизвестный TTS provider: {normalized or '<empty>'}. "
            f"Доступно: {', '.join(sorted(_PROVIDER_TYPES))}"
        )
    return provider_type()


def provider_settings(config: dict[str, Any], name: str) -> dict[str, Any]:
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return {}
    settings = providers.get(str(name or "").strip().lower())
    return settings if isinstance(settings, dict) else {}


__all__ = [
    "BaseTTSProvider",
    "TTSProviderError",
    "create_provider",
    "provider_settings",
]
