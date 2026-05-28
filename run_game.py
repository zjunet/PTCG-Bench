"""Run a complete game of Pokemon TCG with detailed debug output."""

import argparse
import sys
from typing import Optional

import weave

from ptcgbench.agents.base_agent import BaseAgent
from ptcgbench.agents.charizard_heuristic_agent import CharizardHeuristicAgent
from ptcgbench.agents.common.profile import AgentProfile
from ptcgbench.agents.random_agent import RandomAgent
from ptcg.core.card import EnergyCard, PokemonCard, TrainerCard
from ptcg.core.envs import PokemonTCG
from ptcg.utils.deck_validation import validate_deck
from ptcg.utils.load_deck import _resolve_deck_path

AGENT_TYPES = ["random", "charizard_heuristic", "skillevolving", "react", "reflexion"]


def create_agent(
    agent_type: str, seed: int = 0, model: str = "openrouter/openai/gpt-4.1"
) -> BaseAgent:
    if agent_type == "random":
        return RandomAgent(seed=seed)
    elif agent_type == "charizard_heuristic":
        return CharizardHeuristicAgent(seed=seed)
    elif agent_type == "skillevolving":
        from ptcgbench.agents.skill_evolving_agent import SkillEvolvingAgent

        return SkillEvolvingAgent(model=model, seed=seed)
    elif agent_type == "react":
        from ptcgbench.agents.react_agent import ReActAgent

        return ReActAgent(model=model)
    elif agent_type == "reflexion":
        from ptcgbench.agents.reflexion_agent import ReflexionAgent

        return ReflexionAgent(model=model)
    else:
        raise ValueError(f"Unknown agent type: {agent_type}. Choose from {AGENT_TYPES}")


COLORS = {
    "HEADER": "\033[95m",
    "PLAYER1": "\033[92m",
    "PLAYER2": "\033[93m",
    "POKEMON": "\033[33m",
    "ENERGY": "\033[33m",
    "TRAINER": "\033[35m",
    "ACTION": "\033[36m",
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "DIM": "\033[2m",
}


def clear_colors():
    print("\033[0m", end="")


def print_header(text):
    line = "=" * 60
    print(f"\n{COLORS['HEADER']}{line}")
    print(f"{COLORS['HEADER']}{text:^60}{COLORS['RESET']}")
    print(f"{COLORS['HEADER']}{line}{COLORS['RESET']}")


def print_section(title):
    print(f"\n{COLORS['BOLD']}>>> {title}{COLORS['RESET']}")


def format_energy(energy_list):
    if not energy_list:
        return "None"
    energy_names = []
    for e in energy_list:
        if hasattr(e, "name"):
            energy_names.append(e.name)
        else:
            energy_names.append(str(e))
    return ", ".join(energy_names)


def format_pokemon(card, is_active=False):
    if not card:
        return "  Empty slot"

    lines = []
    prefix = "* " if is_active else "  "

    hp_current = getattr(card, "hp", 0)

    status = f"{COLORS['POKEMON']}{prefix}{card.name}{COLORS['RESET']}"
    status += f" [HP: {hp_current}]"

    energy = getattr(card, "energy", [])
    if energy:
        status += f" | Energy: {format_energy(energy)}"

    attachment = getattr(card, "attachment", [])
    if attachment:
        tools = [a.name for a in attachment if hasattr(a, "name")]
        if tools:
            status += f" | Tools: {', '.join(tools)}"

    lines.append(status)

    attacks = getattr(card, "attacks", [])
    if attacks:
        lines.append(f"{COLORS['DIM']}      Attacks:{COLORS['RESET']}")
        for atk in attacks:
            cost = getattr(atk, "cost", [])
            cost_str = format_energy(cost) if cost else "Free"
            damage = getattr(atk, "damage", 0)
            name = getattr(atk, "name", "Unknown")
            lines.append(
                f"{COLORS['DIM']}        - {name}: {damage} damage ({cost_str}){COLORS['RESET']}"
            )

    abilities = getattr(card, "ability", [])
    if abilities:
        lines.append(f"{COLORS['DIM']}      Abilities:{COLORS['RESET']}")
        for ab in abilities:
            name = getattr(ab, "name", "Unknown")
            lines.append(f"{COLORS['DIM']}        - {name}{COLORS['RESET']}")

    return "\n".join(lines)


def format_card(card):
    if isinstance(card, PokemonCard):
        return format_pokemon(card)
    elif isinstance(card, EnergyCard):
        provides = getattr(card, "provides", [])
        provides_str = format_energy(provides) if provides else "Basic Energy"
        return f"{COLORS['ENERGY']}[Energy] {card.name} ({provides_str}){COLORS['RESET']}"
    elif isinstance(card, TrainerCard):
        trainer_type = getattr(card, "trainerType", None)
        type_str = (
            trainer_type.name if trainer_type and hasattr(trainer_type, "name") else "Trainer"
        )
        return f"{COLORS['TRAINER']}[{type_str}] {card.name}{COLORS['RESET']}"
    else:
        return f"[Card] {card.name}"


def format_hand(hand):
    if not hand:
        return "  No cards"

    lines = []
    for i, card in enumerate(hand):
        lines.append(f"    {i + 1}. {format_card(card)}")

    return "\n".join(lines)


def print_player_state(player, name, show_hand=False):
    color = COLORS["PLAYER1"] if name == "Player 1" else COLORS["PLAYER2"]
    print(f"\n{color}{name}:{COLORS['RESET']}")
    print(f"  Deck: {len(player.left)} cards remaining")
    print(f"  Hand: {len(player.hand)} cards")
    print(f"  Prize cards: {len(player.prize)} remaining")
    print(f"  Discard pile: {len(player.discard)} cards")

    if show_hand:
        print(f"\n  Hand cards:")
        print(format_hand(player.hand))

    print(f"\n  Active Pokemon:")
    if player.active:
        for p in player.active:
            print(format_pokemon(p, is_active=True))
    else:
        print("    No active Pokemon")

    print(f"\n  Bench ({len(player.bench)} Pokemon):")
    if player.bench:
        for i, p in enumerate(player.bench):
            print(format_pokemon(p))
    else:
        print("    Empty bench")


def print_game_state(state, turn_info):
    turn = turn_info.get("turn", None)
    turn_name = turn.name if turn and hasattr(turn, "name") else str(turn)
    turn_number = getattr(state, "turn_number", 0)
    timestep = getattr(state, "timestep", 0)

    print_header(f"Turn {turn_number} | Timestep {timestep} | Current: {turn_name}")

    print_player_state(state.player1, "Player 1", show_hand=True)
    print_player_state(state.player2, "Player 2", show_hand=False)

    stadium = getattr(state, "stadium", [])
    if stadium:
        print(
            f"\n{COLORS['HEADER']}Stadium: {stadium[0].name if stadium else 'None'}{COLORS['RESET']}"
        )


def print_action(action, step):
    print(f"\n{COLORS['ACTION']}[Step {step}] {action.to_nl()}{COLORS['RESET']}")


def _post_single_game_batch(
    agent: BaseAgent,
    *,
    my_deck: str,
    opponent_deck: str,
    result: str,
    turn_count: int,
    verbose: bool,
) -> None:
    battle_record = getattr(agent, "_battle_record", None)
    history_path = getattr(battle_record, "record_dir", None)
    if history_path is None or not history_path.is_dir():
        return

    reflection = agent.post_batch(
        battle_summary={
            "my_deck": my_deck,
            "opponent_deck": opponent_deck,
            "result": result,
            "turn_count": turn_count,
        },
        history_path=history_path,
    )
    if verbose and reflection:
        agent_name = getattr(agent, "name", agent.__class__.__name__)
        print(
            f"  {agent_name} evolved: {len(reflection.get('lessons', []))} lessons, "
            f"{len(reflection.get('heuristics', []))} heuristics"
        )


@weave.op
def run_game(
    seed: int = 0,
    verbose: bool = True,
    max_steps: int = 1000,
    show_every_step: bool = False,
    deck1: Optional[str] = None,
    deck2: Optional[str] = None,
    agent1_type: str = "random",
    agent2_type: str = "random",
    model1: str = "deepseek-chat",
    model2: str = "deepseek-chat",
):
    agent1 = create_agent(agent1_type, seed=seed, model=model1)
    agent2 = create_agent(agent2_type, seed=seed + 1, model=model2)

    env = PokemonTCG(seed=seed, verbose=verbose, deck1=deck1, deck2=deck2)
    obs, reward, done, info = env.reset()

    # Derive deck names and notify agents of game start
    deck1_name = AgentProfile.deck_name_from_path(deck1) if deck1 else "charizard_ex"
    deck2_name = AgentProfile.deck_name_from_path(deck2) if deck2 else "charizard_ex"
    agent2_name = agent2_type if agent2_type == "random" else getattr(agent2, "name", agent2_type)
    agent1_name = agent1_type if agent1_type == "random" else getattr(agent1, "name", agent1_type)

    if hasattr(agent1, "notify_game_start"):
        agent1.notify_game_start(deck1_name, deck2_name, opponent_name=agent2_name)
    if hasattr(agent2, "notify_game_start"):
        agent2.notify_game_start(deck2_name, deck1_name, opponent_name=agent1_name)

    if verbose:
        print_header("GAME START")
        print(f"  Player 1 agent: {agent1_type}")
        print(f"  Player 2 agent: {agent2_type}")
        print_game_state(env.gamestate, info)

    step = 0
    try:
        while not done and step < max_steps:
            actions = info["raw_available_actions"]
            if not actions:
                break

            current_turn = info.get("turn")
            if current_turn and hasattr(current_turn, "name") and current_turn.name == "PLAYER2":
                action = agent2.predict(obs, info)
            else:
                action = agent1.predict(obs, info)

            if verbose:
                print_action(action, step + 1)

            obs, reward, done, info = env.step(action)
            step += 1

            if show_every_step and verbose:
                print_game_state(env.gamestate, info)
    finally:
        # Determine game outcome for battle records
        winner = info.get("winner")
        from ptcg.core.enums import PlayerId

        p1_result = "unknown"
        p2_result = "unknown"
        if winner == PlayerId.PLAYER1:
            p1_result, p2_result = "win", "loss"
        elif winner == PlayerId.PLAYER2:
            p1_result, p2_result = "loss", "win"
        elif done:
            p1_result = p2_result = "draw"

        state = obs if hasattr(obs, "player1") else env.gamestate
        p1_prizes = len(state.player1.prize) if hasattr(state, "player1") else 0
        p2_prizes = len(state.player2.prize) if hasattr(state, "player2") else 0

        agent1.post_game(result=p1_result, my_prizes=p1_prizes, opponent_prizes=p2_prizes)
        agent2.post_game(result=p2_result, my_prizes=p2_prizes, opponent_prizes=p1_prizes)

        # Copy replay log into each agent's battle record directory
        if env.recorder is not None:
            replay_file = env.recorder.file_path
            for agent in (agent1, agent2):
                br = getattr(agent, "_battle_record", None)
                if br is not None:
                    br.save_replay(replay_file)

        _post_single_game_batch(
            agent1,
            my_deck=deck1_name,
            opponent_deck=deck2_name,
            result=p1_result,
            turn_count=step,
            verbose=verbose,
        )
        _post_single_game_batch(
            agent2,
            my_deck=deck2_name,
            opponent_deck=deck1_name,
            result=p2_result,
            turn_count=step,
            verbose=verbose,
        )

    winner = info.get("winner")
    if verbose:
        print_header("GAME OVER")
        print(f"\n{COLORS['HEADER']}Total steps: {step}{COLORS['RESET']}")
        if winner:
            print(f"{COLORS['HEADER']}Winner: {winner.name}{COLORS['RESET']}")
        else:
            print(f"{COLORS['HEADER']}Game ended without a winner{COLORS['RESET']}")

    return winner, step


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Pokemon TCG game with random agents")
    parser.add_argument(
        "--deck1", type=str, default=None, help="Deck name for Player 1 (from ptcg-engine)"
    )
    parser.add_argument(
        "--deck2", type=str, default=None, help="Deck name for Player 2 (from ptcg-engine)"
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed for reproducibility")
    parser.add_argument("--max-steps", type=int, default=1000, help="Maximum number of game steps")
    parser.add_argument(
        "--show-every-step", action="store_true", help="Show game state after every step"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    parser.add_argument(
        "--agent1",
        type=str,
        default="random",
        choices=AGENT_TYPES,
        help="Agent type for Player 1 (default: random)",
    )
    parser.add_argument(
        "--agent2",
        type=str,
        default="random",
        choices=AGENT_TYPES,
        help="Agent type for Player 2 (default: random)",
    )
    parser.add_argument(
        "--model1",
        type=str,
        default="deepseek-chat",
        help="LLM model for Player 1 (only used if --agent1 is an LLM agent)",
    )
    parser.add_argument(
        "--model2",
        type=str,
        default="deepseek-chat",
        help="LLM model for Player 2 (only used if --agent2 is an LLM agent)",
    )

    args = parser.parse_args()
    llm_agents = {"skillevolving", "react", "reflexion"}
    if args.agent1 in llm_agents or args.agent2 in llm_agents:
        weave.init("test_ptcg_agent")

    # Validate deck names if provided and construct full paths
    deck1_path = None
    deck2_path = None
    try:
        if args.deck1:
            deck_name = validate_deck(args.deck1)
            deck1_path = str(_resolve_deck_path(deck_name))
        if args.deck2:
            deck_name = validate_deck(args.deck2)
            deck2_path = str(_resolve_deck_path(deck_name))
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("Starting Pokemon TCG game...")
    run_game(
        seed=args.seed,
        verbose=not args.quiet,
        max_steps=args.max_steps,
        show_every_step=args.show_every_step,
        deck1=deck1_path,
        deck2=deck2_path,
        agent1_type=args.agent1,
        agent2_type=args.agent2,
        model1=args.model1,
        model2=args.model2,
    )
