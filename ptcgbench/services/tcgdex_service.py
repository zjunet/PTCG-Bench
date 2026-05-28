"""Service for fetching card data from the tcgdex API."""

from __future__ import annotations

import re
from typing import Any

from tcgdexsdk import TCGdex

# Map project set codes to tcgdex set IDs
SET_TO_TCGDEX: dict[str, str] = {
    # Scarlet & Violet
    "SVI": "sv01",
    "PAL": "sv02",
    "OBF": "sv03",
    "MEW": "sv03.5",
    "PAR": "sv04",
    "PAF": "sv04.5",
    "TEF": "sv05",
    "TWM": "sv06",
    "SFA": "sv06.5",
    "SSP": "sv07",
    "SVE": "sve",
    "PRE": "sv08.5",
    "DRI": "sv10",
    "ASC": "me02.5",
    "JTG": "sv09",
    "WHT": "sv10.5w",
    # Sword & Shield
    "BRS": "swsh9",
    "ASR": "swsh10",
    "LOR": "swsh11",
    "PGO": "swsh10.5",
    "SIT": "swsh12",
    "CRZ": "swsh12.5",
    "VIV": "swsh4",
}

# Reverse mapping for embedding in cached data
TCGDEX_TO_SET: dict[str, str] = {v: k for k, v in SET_TO_TCGDEX.items()}


def _parse_damage(raw: str | int | None) -> dict[str, Any]:
    """Parse tcgdex damage string like '180+' or '30' into project format."""
    if raw is None:
        return {"amount": 0, "suffix": ""}
    if isinstance(raw, int):
        return {"amount": raw, "suffix": ""}
    match = re.match(r"(\d+)(.*)", str(raw))
    if match:
        return {"amount": int(match.group(1)), "suffix": match.group(2)}
    return {"amount": 0, "suffix": str(raw)}


def _convert_attacks(attacks: list[Any] | None) -> list[dict[str, Any]]:
    """Convert tcgdex attack objects to project format."""
    if not attacks:
        return []
    result = []
    for atk in attacks:
        entry: dict[str, Any] = {
            "name": atk.name,
            "cost": list(atk.cost) if atk.cost else [],
            "damage": _parse_damage(atk.damage),
        }
        if atk.effect:
            entry["effect"] = atk.effect
        result.append(entry)
    return result


def _convert_abilities(abilities: list[Any] | None) -> list[dict[str, Any]]:
    """Convert tcgdex ability objects to project format."""
    if not abilities:
        return []
    return [{"name": a.name, "effect": a.effect} for a in abilities]


def _category_to_card_type(category: str | None, trainer_type: str | None) -> str:
    """Map tcgdex category/trainerType to project card_type."""
    if category == "Pokemon":
        return "Pokémon"
    if category == "Energy":
        return "Special Energy"  # tcgdex doesn't distinguish basic vs special via category
    if category == "Trainer":
        type_map = {
            "Item": "Item",
            "Supporter": "Supporter",
            "Stadium": "Stadium",
            "Tool": "Pokémon Tool",
        }
        return type_map.get(trainer_type or "", "Item")
    return "Unknown"


# Fallback images for basic energy cards that tcgdex lacks images for.
# These are sourced from other sets within tcgdex that do have images.
FALLBACK_ENERGY_IMAGES: dict[str, str] = {
    "Fire Energy": "https://assets.tcgdex.net/en/sv/sv03/230/high.jpg",
    "Lightning Energy": "https://assets.tcgdex.net/en/sv/sv01/257/high.jpg",
    "Psychic Energy": "https://assets.tcgdex.net/en/swsh/swsh6/232/high.jpg",
    "Darkness Energy": "https://assets.tcgdex.net/en/swsh/swsh7/236/high.jpg",
    "Metal Energy": "https://assets.tcgdex.net/en/swsh/swsh7/237/high.jpg",
}


def _fallback_energy_img(name: str | None) -> str | None:
    """Return a fallback image URL for basic energy cards without tcgdex images."""
    if name and name in FALLBACK_ENERGY_IMAGES:
        return FALLBACK_ENERGY_IMAGES[name]
    return None


def fetch_card(set_code: str, local_id: str) -> dict[str, Any] | None:
    """Fetch card data from tcgdex and convert to project format.

    Args:
        set_code: Project set code like "PAF", "SVI", etc.
        local_id: Card number like "054", "198"

    Returns:
        Card data dict matching the project's database.json format, or None on failure.
    """
    tcgdex_set = SET_TO_TCGDEX.get(set_code)
    if not tcgdex_set:
        print(f"Warning: No tcgdex mapping for set {set_code}")
        return None

    sdk = TCGdex()

    # Try the local_id as-is first, then without leading zeros
    for lid in (local_id, str(int(local_id))):
        tcgdex_id = f"{tcgdex_set}-{lid}"
        try:
            card = sdk.card.getSync(tcgdex_id)
            if card is not None:
                break
        except Exception:
            continue
    else:
        return None

    img = f"{card.image}/high.jpg" if card.image else _fallback_energy_img(card.name)
    result: dict[str, Any] = {
        "name": card.name,
        "set_name": set_code,
        "number": card.localId,
        "card_type": _category_to_card_type(card.category, card.trainerType),
        "img": img,
    }

    if card.suffix:
        result["tags"] = [card.suffix]

    if card.category == "Pokemon":
        if card.hp:
            result["hp"] = card.hp
        if card.stage:
            result["stage"] = card.stage
        if card.types:
            result["types"] = card.types
        if card.evolveFrom:
            result["evolve_from"] = card.evolveFrom
        if card.retreat is not None:
            result["retreat"] = card.retreat

        attacks = _convert_attacks(card.attacks)
        if attacks:
            result["attacks"] = attacks
        abilities = _convert_abilities(card.abilities)
        if abilities:
            result["abilities"] = abilities

    elif card.category == "Trainer":
        if card.effect:
            result["effect"] = card.effect

    elif card.category == "Energy":
        if card.effect:
            result["effect"] = card.effect

    return result
