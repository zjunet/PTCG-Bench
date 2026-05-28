"""Base agent interface for PTCG battles."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

from ptcg.core.action import Action
from ptcg.core.state import State


class BaseAgent(ABC):
    """Abstract base class for all battle agents.

    All agents (LLM, RL, rule-based, etc.) should inherit from this class
    and implement the predict method.
    """

    @abstractmethod
    def predict(self, obs: State, info: Dict[str, Any]) -> Action:
        """Predict the next action given the current observation.

        Args:
            obs: Current game state
            info: Additional information dictionary containing:
                - raw_available_actions: List of valid Action objects
                - turn: Current player (PlayerId)
                - full_state: Complete game state object
                - is_choosing_card: Whether a card selection prompt is active

        Returns:
            Action: The chosen action to take
        """
        pass

    def reset(self) -> None:
        """Reset the agent's internal state. Override if needed."""
        pass

    def notify_game_start(
        self,
        my_deck: str,
        opponent_deck: str,
        opponent_name: str = "",
    ) -> None:
        """Called once before each game starts. Override if needed."""
        pass

    def post_game(self, result: str = "", my_prizes: int = 0, opponent_prizes: int = 0) -> None:
        """Called once after each game ends.

        Args:
            result:       "win", "loss", "draw", or "unknown".
            my_prizes:    Prize cards remaining for this agent.
            opponent_prizes: Prize cards remaining for the opponent.

        Override to write summaries, trigger reflection, etc.
        """
        pass

    def post_batch(
        self,
        battle_summary: dict[str, Any],
        history_path: Path,
    ) -> dict[str, Any] | None:
        """Called after each evaluation batch. Override if batch-level processing is needed."""
        return None
