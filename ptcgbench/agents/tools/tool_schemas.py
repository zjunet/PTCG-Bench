from __future__ import annotations

import json
from typing import Any

TOOL_TO_ACTION_TYPE: dict[str, str] = {
    "attack": "ATTACK_ACTION",
    "use_ability": "USE_ABILITY_ACTION",
    "use_stadium": "USE_STADIUM_ACTION",
    "retreat": "RETREAT_ACTION",
    "play_pokemon": "PLAY_POKEMON_ACTION",
    "evolve_pokemon": "EVOLVE_POKEMON_ACTION",
    "attach_energy": "ATTACH_ENERGY_ACTION",
    "use_supporter": "USE_SUPPORTER_ACTION",
    "use_item": "USE_ITEM_ACTION",
    "use_tool": "USE_TOOL_ACTION",
    "put_stadium": "PUT_STADIUM_ACTION",
    "discard_stadium": "DISCARD_STADIUM_ACTION",
    "pass_turn": "PASS_TURN",
    "choose_card": "CHOOSE_CARD_ACTION",
    "query_card": "QUERY_CARD",
}

GAME_ACTION_TOOLS: set[str] = {
    "attack",
    "use_ability",
    "use_stadium",
    "retreat",
    "play_pokemon",
    "evolve_pokemon",
    "attach_energy",
    "use_supporter",
    "use_item",
    "use_tool",
    "put_stadium",
    "discard_stadium",
    "pass_turn",
    "choose_card",
}

GENERAL_TOOLS: set[str] = {"query_card", "activate_skill", "query_discard"}


def get_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "attack",
                "description": "Use your active Pokémon's attack against the opponent's active Pokémon.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of your active Pokémon performing the attack",
                        },
                        "attack_name": {
                            "type": "string",
                            "description": "Exact name of the attack to use",
                        },
                    },
                    "required": ["source_card", "attack_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "use_ability",
                "description": "Activate a Pokémon's ability (if it has one that requires manual activation).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Pokémon whose ability you are using",
                        },
                        "ability_name": {
                            "type": "string",
                            "description": "Name of the ability (optional if Pokémon has only one ability)",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "use_stadium",
                "description": "Activate the in-play stadium's effect (if it requires manual activation).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Stadium card currently in play",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "retreat",
                "description": "Switch your active Pokémon with one from your bench. Requires paying the active Pokémon's retreat cost in energy.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of your active Pokémon to retreat",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "play_pokemon",
                "description": "Play a Basic Pokémon from your hand onto the field.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Basic Pokémon card to play",
                        },
                        "position": {
                            "type": "string",
                            "enum": ["ACTIVE", "BENCH"],
                            "description": "ACTIVE if your active slot is empty, BENCH for bench slot (up to 5 Pokémon)",
                        },
                    },
                    "required": ["source_card", "position"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "evolve_pokemon",
                "description": "Evolve a Pokémon already on the field using an Evolution card from your hand.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Evolution card (the new, higher-stage Pokémon)",
                        },
                        "target_card": {
                            "type": "string",
                            "description": "Name of the Pokémon currently on field that will be evolved",
                        },
                        "target_index": {
                            "type": "integer",
                            "description": (
                                "Optional field index shown in available_actions "
                                "to disambiguate same-name Active or Benched Pokemon"
                            ),
                        },
                    },
                    "required": ["source_card", "target_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attach_energy",
                "description": "Attach one energy card from your hand to any of your Pokémon (active or bench).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the energy card",
                        },
                        "target_card": {
                            "type": "string",
                            "description": "Name of the Pokémon to attach the energy to",
                        },
                        "target_index": {
                            "type": "integer",
                            "description": (
                                "Optional field index shown in available_actions "
                                "to disambiguate same-name Active or Benched Pokemon"
                            ),
                        },
                    },
                    "required": ["source_card", "target_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "use_supporter",
                "description": "Play a Supporter card from your hand. Limit 1 per turn.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Supporter card",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "use_item",
                "description": "Play an Item card from your hand.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Item card",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "use_tool",
                "description": "Attach a Pokémon Tool card from your hand to one of your Pokémon.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Tool card",
                        },
                        "target_card": {
                            "type": "string",
                            "description": "Name of the Pokémon to attach the Tool to",
                        },
                        "target_index": {
                            "type": "integer",
                            "description": (
                                "Optional field index shown in available_actions "
                                "to disambiguate same-name Active or Benched Pokemon"
                            ),
                        },
                    },
                    "required": ["source_card", "target_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "put_stadium",
                "description": "Play a Stadium card from your hand, replacing any existing stadium.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Stadium card",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "discard_stadium",
                "description": "Discard the stadium currently in play.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_card": {
                            "type": "string",
                            "description": "Name of the Stadium card to discard",
                        },
                    },
                    "required": ["source_card"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "pass_turn",
                "description": "End your turn without taking further action. Use when you have no beneficial actions left.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "choose_card",
                "description": "Respond to a card-selection prompt triggered by an effect (e.g., searching deck, discarding cards).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chosen_cards": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of card names you are selecting",
                        },
                        "chosen_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": (
                                "Optional field indices shown in available_actions "
                                "to disambiguate same-name Active or Benched Pokemon"
                            ),
                        },
                    },
                    "required": ["chosen_cards"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_card",
                "description": "Query detailed information about a specific card from the database. Use when you need exact attack costs, ability details, weakness/resistance, retreat cost, or special rules.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {
                            "type": "string",
                            "description": "Card identifier in format '{SET}-{NUMBER}', e.g., 'PAF-001'",
                        },
                    },
                    "required": ["card_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_discard",
                "description": "View the contents of a player's discard pile. Use when you need to check which cards have been knocked out or discarded.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "player": {
                            "type": "string",
                            "enum": ["me", "opponent"],
                            "description": "Which player's discard pile to inspect",
                        },
                    },
                    "required": ["player"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "activate_skill",
                "description": "Load a skill's full instructions or a specific resource file. When a skill matches your current game situation, call this tool to load its detailed strategy.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the skill to activate (from the Skills section in your instructions)",
                        },
                        "resource": {
                            "type": "string",
                            "description": "Optional: specific resource file to load (e.g., 'REFERENCE.md'). Omit to load the skill's main instructions.",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
    ]


def parse_tool_call_arguments(tool_call: Any) -> tuple[str, dict[str, Any]]:
    if hasattr(tool_call, "function"):
        tool_name = tool_call.function.name
        arguments_json = tool_call.function.arguments
        arguments = json.loads(arguments_json) if arguments_json else {}
    else:
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
    return tool_name, arguments


def is_game_action_tool(tool_name: str) -> bool:
    return tool_name in GAME_ACTION_TOOLS


def is_general_tool(tool_name: str) -> bool:
    return tool_name in GENERAL_TOOLS
