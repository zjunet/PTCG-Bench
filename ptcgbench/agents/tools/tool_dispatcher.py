from __future__ import annotations

from typing import TYPE_CHECKING

from ptcgbench.agents.tools import CardQueryTool

if TYPE_CHECKING:
    from ptcgbench.agents.interfaces.observer import StateObserver
    from ptcgbench.agents.skills.skill_registry import SkillRegistry
    from ptcg.core.state import State


class ToolDispatcher:
    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        observer: StateObserver | None = None,
    ):
        self.card_query = CardQueryTool()
        self.skill_registry = skill_registry
        self.observer = observer
        self._active_skills: set[str] = set()

    def dispatch(self, tool_name: str, arguments: dict, state: State | None = None) -> str:
        """Dispatch a general (non-game-action) tool call."""
        if tool_name == "query_card":
            return self._query_card(arguments.get("card_id", ""))
        if tool_name == "activate_skill":
            return self.activate_skill(arguments.get("name", ""), arguments.get("resource"))
        if tool_name == "query_discard":
            return self._query_discard(arguments, state)
        return f"Unknown tool: {tool_name}"

    # -- private handlers --------------------------------------------------

    def _query_card(self, card_id: str) -> str:
        query_result = self.card_query.query(card_id)
        if query_result:
            return f"Card Query Result:\n{self.card_query.format_result(query_result)}"
        return f"Card not found: {card_id}"

    def _query_discard(self, arguments: dict, state: State | None) -> str:
        if state is None or self.observer is None:
            return "Cannot query discard pile: no state available."
        target = arguments.get("player", "me")
        my_player, opp_player = self.observer._get_players(state)
        player_obj = my_player if target == "me" else opp_player
        cards = [f"{c.name} ({c.id})" for c in player_obj.discard]
        if cards:
            return f"{target.title()} discard pile ({len(cards)} cards):\n" + "\n".join(
                f"  - {c}" for c in cards
            )
        return f"{target.title()} discard pile is empty."

    # -- public helpers ----------------------------------------------------

    def activate_skill(self, name: str, resource: str | None = None) -> str:
        if self.skill_registry is None:
            return "No skills available."

        skill = self.skill_registry.get(name)
        if skill is None:
            available = self.skill_registry.skill_names()
            return f"Unknown skill '{name}'. Available skills: {available}"

        if resource is not None:
            content = skill.load_resource(resource)
            if content is None:
                resources = skill.list_resources()
                return f"Resource '{resource}' not found in skill '{name}'. Available: {resources}"
            return (
                f'<skill_content name="{name}" resource="{resource}">\n{content}\n</skill_content>'
            )

        # Load main skill instructions
        if name in self._active_skills:
            return f"Skill '{name}' is already active. Its instructions are in your context."

        self._active_skills.add(name)
        resources = skill.list_resources()
        resource_list = ""
        if resources:
            resource_list = "\nAvailable resources: " + ", ".join(resources)

        return f'<skill_content name="{name}">\n{skill.body}\n</skill_content>{resource_list}'

    def reset(self) -> None:
        self._active_skills.clear()
