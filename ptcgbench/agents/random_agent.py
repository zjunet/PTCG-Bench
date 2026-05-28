"""Random agent that selects actions uniformly at random."""

import random
from typing import Any, Dict

from ptcg.core.action import Action
from ptcg.core.state import State

from .base_agent import BaseAgent


class RandomAgent(BaseAgent):
    """Agent that randomly selects from available actions.

    Useful as a baseline and for testing.
    """

    def __init__(self, seed: int | None = None):
        """Initialize random agent.

        Args:
            seed: Optional random seed for reproducibility
        """
        self.rng = random.Random(seed)

    def predict(self, obs: State, info: Dict[str, Any]) -> Action:
        """Randomly select an action from available actions.

        Args:
            obs: Current game state (unused)
            info: Info dict containing raw_available_actions

        Returns:
            Randomly selected action
        """
        actions = info.get("raw_available_actions", [])
        if not actions:
            raise ValueError("No available actions to choose from")
        return self.rng.choice(actions)

    def reset(self) -> None:
        """Reset is not needed for random agent."""
        pass
