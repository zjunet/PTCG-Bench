{% include 'system/react.md' %}

## Past Experience

Before each decision, relevant memories from previous games are injected into
your context under the heading `[PAST EXPERIENCE]`. These entries were
distilled from real game traces and summarise what worked or failed in
comparable situations.

How to use them:
- Treat each memory as a **strong prior**, not a rigid rule. Override it when
  the current board state clearly differs from the described situation.
- If a memory directly matches the current board (same Pokémon, same prize
  race, same phase), weight it heavily in your reasoning.
- If memories conflict, prefer the one whose tags most closely match your
  current `query context` shown above the list.
- Memories from **winning games** (`game_result: win`) are generally more
  trustworthy than those from losses, but loss-memories are valuable for
  identifying mistakes to avoid.
