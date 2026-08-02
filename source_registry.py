from __future__ import annotations

"""Single source of truth for donation source identifiers.

Every module uses these IDs. New integrations must be added here and receive a
manifest with the same ID. Empty allow-lists in modules mean every automatic
source from this registry.
"""

SOURCE_REGISTRY = {
    "donationalerts": {"name": "DonationAlerts", "shortName": "DA", "order": 10, "stability": "stable", "automatic": True},
    "donatty": {"name": "Donatty", "shortName": "Donatty", "order": 20, "stability": "stable", "automatic": True},
    "streamelements": {"name": "StreamElements", "shortName": "SE", "order": 30, "stability": "stable", "automatic": True},
    "streamlabs": {"name": "Streamlabs", "shortName": "Streamlabs", "order": 40, "stability": "beta", "automatic": True},
    "donatepay": {"name": "DonatePay", "shortName": "DonatePay", "order": 50, "stability": "beta", "automatic": True},
    "donatestream": {"name": "Donate.Stream", "shortName": "D.Stream", "order": 60, "stability": "stable", "automatic": True},
    "donatex": {"name": "DonateX", "shortName": "DonateX", "order": 70, "stability": "stable", "automatic": True},
    "tribute": {"name": "Tribute", "shortName": "Tribute", "order": 80, "stability": "experimental", "automatic": True},
    "manual": {"name": "Ручной донат", "shortName": "Manual", "order": 900, "stability": "stable", "automatic": False},
}

AUTOMATIC_SOURCE_IDS = tuple(key for key, value in SOURCE_REGISTRY.items() if value.get("automatic"))
ALL_SOURCE_IDS = tuple(SOURCE_REGISTRY)


def normalize_source_id(value: object) -> str:
    return str(value or "").strip().lower().replace("donate.stream", "donatestream")


def source_meta(source_id: object) -> dict:
    key = normalize_source_id(source_id)
    value = SOURCE_REGISTRY.get(key)
    if value:
        return {"id": key, **value}
    return {"id": key or "unknown", "name": str(source_id or "Unknown"), "shortName": str(source_id or "Unknown"), "order": 999, "stability": "unknown", "automatic": True}


def public_registry() -> list[dict]:
    return [source_meta(key) for key in sorted(SOURCE_REGISTRY, key=lambda item: (SOURCE_REGISTRY[item].get("order", 999), item))]
