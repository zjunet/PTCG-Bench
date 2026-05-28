#!/usr/bin/env python3
"""Build card_data_cache.json by scanning card implementations and fetching metadata from tcgdex."""

from __future__ import annotations

import json
from pathlib import Path

from ptcg.core.card_registry import CardRegistry
from ptcgbench.services.tcgdex_service import fetch_card

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_PATH = PROJECT_ROOT / "card_data_cache.json"


def main() -> None:
    registry = CardRegistry()
    registry._ensure_loaded()
    card_ids = registry.list_all()
    print(f"Found {len(card_ids)} card implementations")

    cache: dict[str, dict] = {}

    for card_id in card_ids:
        card_class = registry.get(card_id)
        if card_class is None:
            continue

        instance = card_class()
        set_code = instance.set_name
        number = instance.number
        print(f"  Fetching {card_id} ({instance.name})...", end=" ", flush=True)

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            card_data = fetch_card(set_code, number)
            if card_data:
                break

        if card_data is None:
            print("not found, using minimal data")
            card_data = {
                "name": instance.name,
                "set_name": set_code,
                "number": number,
            }
        else:
            print("ok")

        cache[card_id] = card_data

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\nCache saved to {CACHE_PATH} ({len(cache)} cards)")


def _class_to_file(cls: type) -> str:
    """Infer the filename from the class's module path."""
    module = cls.__module__
    # e.g. "ptcg.cards.PAF.charizard_ex" -> "PAF/charizard_ex.py"
    parts = module.split(".")
    if len(parts) >= 3:
        return "/".join(parts[2:]) + ".py"
    return cls.__module__.replace(".", "/") + ".py"


if __name__ == "__main__":
    main()
