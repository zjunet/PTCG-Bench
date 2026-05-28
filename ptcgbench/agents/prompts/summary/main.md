You are an AI agent tasked with summarizing a single Pokémon TCG (PTCG) turn from a provided chat history into a structured JSON format.

## Input
You will be given a chat history describing one turn of a PTCG game in JSONL format:

```
{{ chat_history }}
```

## Objective
Your goal is to compress the full turn into a structured JSON output that captures:
- Key game states
- Action sequence
- Agent reasoning
- State transitions

The output must be objective, concise, and in third-person perspective.

## Output Requirements

- Output must be valid JSON
- Use third-person perspective only (e.g., "the agent", not "I")
- Do not include subjective judgments or evaluations
- Do not include unnecessary verbosity
- Focus on information compression and clarity

## Required JSON Structure

```json
{
  "opponent_previous_turn_actions": [...],
  "turn_start_state": {...},
  "turn_action_sequence": [...],
  "turn_reasoning_summary": {...},
  "turn_state_changes": {...}
}
```

## Field Specifications

### 1. `opponent_previous_turn_actions`

- Optional but should be included if present
- List the opponent's actions from the previous turn

### 2. `turn_start_state`

Include:

- Turn metadata (player, turn number, timestep)
- Player state:
  - active Pokémon (id, name, hp, energy)
  - bench Pokémon
  - hand (cards with id and name)
  - counts (hand, deck, prize, discard)
- Opponent state (same structure but simpler if needed)

### 3. `turn_action_sequence`

- Chronological list of actions taken during the turn
- Each step includes:
  - `"step"` (integer)
  - `"action"` (short description)
  - `"details"` (structured object when applicable)

### 4. `turn_reasoning_summary`

Summarize how the agent reasoned based only on the chat content objectively.

- Must not include:
  - Opinions
  - Evaluations (e.g., "good", "bad", "optimal")

Example structure:

```json
{
  "goal": "...",
  "reasoning_steps": [...]
}
```

### 5. `turn_state_changes`

Track before vs after changes.

Include if changed:

- Active Pokémon (energy changes)
- Bench changes (e.g., evolution)
- Hand changes
- Deck count
- Discard count
- Prize counts
- Opponent board changes
