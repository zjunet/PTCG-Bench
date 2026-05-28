from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]


class CardQueryTool:
    def __init__(self, cache_path: str | Path | None = None):
        if cache_path is None:
            cache_path = PROJECT_ROOT / "card_data_cache.json"
        self._cache_path = Path(cache_path)
        self._cards: dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        with open(self._cache_path, "r", encoding="utf-8") as f:
            self._cards = json.load(f)

    def query(self, card_id: str) -> dict | None:
        return self._cards.get(card_id)

    def format_result(self, card_data: dict) -> str:
        lines = []

        name = card_data.get("name", "Unknown")
        card_type = card_data.get("card_type", "Unknown")
        lines.append(f"Name: {name}")
        lines.append(f"Type: {card_type}")

        if card_type == "Pokémon":
            if stage := card_data.get("stage"):
                lines.append(f"Stage: {stage}")
            if hp := card_data.get("hp"):
                lines.append(f"HP: {hp}")
            if types := card_data.get("types"):
                lines.append(f"Pokemon Type: {', '.join(types)}")
            if evolve_from := card_data.get("evolve_from"):
                lines.append(f"Evolves From: {evolve_from}")

            if abilities := card_data.get("abilities"):
                lines.append("\nAbilities:")
                for ability in abilities:
                    lines.append(
                        f"  - {ability.get('name', 'Unknown')}: {ability.get('effect', 'No effect text')}"
                    )

            if attacks := card_data.get("attacks"):
                lines.append("\nAttacks:")
                for attack in attacks:
                    cost = ", ".join(attack.get("cost", []))
                    attack_name = attack.get("name", "Unknown")
                    damage_info = attack.get("damage", {})
                    if isinstance(damage_info, dict):
                        damage = damage_info.get("amount", "?")
                        suffix = damage_info.get("suffix", "")
                        damage_str = f"{damage}{suffix}"
                    else:
                        damage_str = str(damage_info) if damage_info else "0"
                    effect = attack.get("effect", "")
                    lines.append(f"  - [{cost}] {attack_name}: {damage_str} damage")
                    if effect:
                        lines.append(f"    Effect: {effect}")

            if weakness := card_data.get("weakness"):
                weak_types = weakness.get("type", [])
                weak_value = weakness.get("value", "")
                if weak_types:
                    lines.append(f"\nWeakness: {', '.join(weak_types)} {weak_value}")

            if resistance := card_data.get("resistance"):
                res_types = resistance.get("type", [])
                res_value = resistance.get("value", "")
                if res_types:
                    lines.append(f"Resistance: {', '.join(res_types)} {res_value}")

            if retreat := card_data.get("retreat"):
                lines.append(f"Retreat Cost: {retreat}")

        elif card_type in ("Item", "Supporter", "Stadium", "Pokémon Tool"):
            if effect := card_data.get("effect"):
                lines.append(f"\nEffect: {effect}")

        elif card_type in ("Special Energy", "Basic Energy"):
            if effect := card_data.get("effect"):
                lines.append(f"\nEffect: {effect}")

        if rule_box := card_data.get("rule_box"):
            lines.append(f"\nRule Box: {rule_box}")

        if tags := card_data.get("tags"):
            lines.append(f"\nTags: {', '.join(tags)}")

        return "\n".join(lines)
