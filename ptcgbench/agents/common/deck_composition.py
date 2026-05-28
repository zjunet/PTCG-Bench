from __future__ import annotations

from pathlib import Path


def read_deck_text(deck_path: Path) -> str:
    if not deck_path.exists():
        return "Unknown."

    with deck_path.open(encoding="utf-8") as f:
        lines = [line.rstrip() for line in f if line.strip() and not line.lstrip().startswith("#")]
    return "\n".join(lines) if lines else "Unknown."


def read_deck_compositions(history_path: str | Path) -> tuple[str, str]:
    path = Path(history_path)
    record_dir = path if path.is_dir() else path.parent
    return (
        read_deck_text(record_dir / "my_deck.txt"),
        read_deck_text(record_dir / "opponent_deck.txt"),
    )
