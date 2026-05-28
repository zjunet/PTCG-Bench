"""Unit tests for ContextManager truncation logic."""

from __future__ import annotations

from ptcgbench.agents.memory.context_manager import ContextManager

_SYSTEM = "You are a PTCG agent."


def _make_manager(max_messages: int = 10, max_tokens: int = 100_000) -> ContextManager:
    mgr = ContextManager(
        model="deepseek-chat",
        system_prompt=_SYSTEM,
        max_tokens=max_tokens,
        max_messages=max_messages,
    )
    mgr.clear()
    mgr.add_system(_SYSTEM)
    return mgr


def _tool_call(tc_id: str, name: str) -> dict:
    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


def _messages_are_valid(messages: list[dict]) -> None:
    """Assert OpenAI tool-message invariant: every tool message has a preceding
    assistant message that contains a tool_call with the matching id."""
    # Build a set of (tool_call_id) available from the preceding assistant
    available_tc_ids: set[str] = set()
    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            available_tc_ids = {tc["id"] for tc in (msg.get("tool_calls") or [])}
        elif role == "tool":
            tc_id = msg.get("tool_call_id", "")
            assert tc_id in available_tc_ids, (
                f"Orphaned tool message (tool_call_id={tc_id!r}): "
                f"no preceding assistant with that tool_call."
            )
            available_tc_ids.discard(tc_id)


# ---------------------------------------------------------------------------
# Core invariant tests
# ---------------------------------------------------------------------------


def test_no_orphaned_tool_after_message_count_truncation():
    """Removing oldest messages leaves no orphaned tool messages."""
    mgr = _make_manager(max_messages=5)

    # Turn 1: user → assistant(query_card) → tool
    mgr.add_message({"role": "user", "content": "turn 1 state"})
    mgr.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("tc1", "query_card")],
        }
    )
    mgr.add_message(
        {
            "role": "tool",
            "tool_call_id": "tc1",
            "content": "card info",
        }
    )
    # Second LLM call in same turn → game action
    mgr.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("tc2", "attack")],
        }
    )
    mgr.add_message({"role": "tool", "tool_call_id": "tc2", "content": ""})

    # Turn 2: this user push pushes count over max_messages=5
    # (system + 5 turn-1 messages + 1 user = 7 > 5)
    mgr.add_message({"role": "user", "content": "turn 2 state"})

    built = mgr.build_messages()
    _messages_are_valid(built)


def test_no_orphaned_tool_after_deep_truncation():
    """Multiple truncation iterations must not leave an orphaned tool message."""
    # max_messages=4: system + 3 non-system
    mgr = _make_manager(max_messages=4)

    # Turn 1
    mgr.add_message({"role": "user", "content": "t1"})
    mgr.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("a1", "query_card")],
        }
    )
    mgr.add_message({"role": "tool", "tool_call_id": "a1", "content": "card info"})

    # Turn 2: forces 3 iterations of truncation
    mgr.add_message({"role": "user", "content": "t2"})
    mgr.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_tool_call("b1", "attack")],
        }
    )
    mgr.add_message({"role": "tool", "tool_call_id": "b1", "content": ""})

    # Turn 3: new state
    mgr.add_message({"role": "user", "content": "t3"})

    built = mgr.build_messages()
    _messages_are_valid(built)


def test_message_count_truncation_preserves_latest_user():
    """After truncation the most-recently added user message is still present."""
    mgr = _make_manager(max_messages=4)

    for i in range(6):
        mgr.add_message({"role": "user", "content": f"turn {i}"})
        mgr.add_message({"role": "assistant", "content": f"action {i}"})

    built = mgr.build_messages()
    assert built[-1]["role"] == "assistant"
    assert built[-2]["role"] == "user"
    assert built[-2]["content"] == "turn 5"


def test_token_truncation_removes_complete_turns():
    """Token-based truncation removes from oldest user turn to next user turn."""
    mgr = _make_manager(max_tokens=50)  # Very tight budget

    mgr.add_message({"role": "user", "content": "old turn"})
    mgr.add_message({"role": "assistant", "content": "old reply"})
    mgr.add_message({"role": "user", "content": "new turn"})

    built = mgr.build_messages()
    _messages_are_valid(built)
    # 'new turn' must survive
    assert any(m["content"] == "new turn" for m in built)


# ---------------------------------------------------------------------------
# Skill message tests
# ---------------------------------------------------------------------------


def test_add_skill_stored_separately():
    """Skill content is not in the main message list."""
    mgr = _make_manager()
    mgr.add_skill("<skill_content>strategy</skill_content>")

    assert len(mgr.messages) == 1  # only system prompt
    assert len(mgr._skill_messages) == 1


def test_build_messages_merges_skills_after_system():
    """Skill messages appear right after the system prompt, before user messages."""
    mgr = _make_manager()
    mgr.add_skill("skill_A")
    mgr.add_skill("skill_B")
    mgr.add_message({"role": "user", "content": "turn 1"})

    built = mgr.build_messages()
    assert built[0]["role"] == "system"  # system prompt
    assert built[1]["content"] == "skill_A"
    assert built[1]["role"] == "system"
    assert built[2]["content"] == "skill_B"
    assert built[2]["role"] == "system"
    assert built[3]["role"] == "user"


def test_skills_survive_truncation():
    """Skill messages are not removed when main messages are truncated."""
    mgr = _make_manager(max_messages=3)
    mgr.add_skill("persistent_strategy")
    mgr.add_message({"role": "user", "content": "old turn"})
    mgr.add_message({"role": "assistant", "content": "old action"})
    mgr.add_message({"role": "user", "content": "new turn"})

    built = mgr.build_messages()
    assert any(m["content"] == "persistent_strategy" for m in built)
    assert any(m["content"] == "new turn" for m in built)
    # 'old turn' should be truncated
    assert not any(m.get("content") == "old turn" for m in built)


def test_clear_resets_skill_messages():
    """clear() also removes all stored skill messages."""
    mgr = _make_manager()
    mgr.add_skill("skill_A")
    mgr.add_skill("skill_B")

    mgr.clear()
    assert len(mgr._skill_messages) == 0


def test_no_skills_returns_messages_unchanged():
    """Without skills, build_messages returns the main list directly."""
    mgr = _make_manager()
    mgr.add_message({"role": "user", "content": "hello"})

    built = mgr.build_messages()
    assert len(built) == 2  # system + user
    assert built[0]["role"] == "system"
    assert built[1]["content"] == "hello"
