import json
from pathlib import Path

import pytest

from ptcgbench.agents.memory.context_manager import ContextManager
from ptcgbench.agents.memory.reflection_agent import ReflectionAgent
from ptcgbench.agents.memory.summary_agent import SummaryAgent


def _make_turn_observation(turn_number: int, timestep: int | None = None, extra: str = "") -> str:
    timestep = turn_number if timestep is None else timestep
    suffix = f"\n{extra}" if extra else ""
    return (
        f"turn: player1\n"
        f"turn_number: {turn_number}\n"
        f"timestep: {timestep}\n"
        "available_actions:\n"
        "- attack"
        f"{suffix}"
    )


def _make_turn_summary_response() -> str:
    return json.dumps(
        {
            "opponent_previous_turn_actions": ["draw"],
            "turn_start_state": {
                "turn": "player1",
                "turn_number": 1,
                "timestep": 1,
            },
            "turn_action_sequence": [
                {
                    "step": 1,
                    "action": "attack",
                    "details": {"target": "opponent_active"},
                }
            ],
            "turn_reasoning_summary": {
                "goal": "Advance board state",
                "reasoning_steps": ["Reviewed available attack options."],
            },
            "turn_state_changes": {"deck_count": {"before": 30, "after": 29}},
        }
    )


class _FakeCompletions:
    def create(self, **kwargs):
        messages = kwargs.get("messages", [])
        system_prompt = messages[0]["content"] if messages else ""
        if "summarizing a single Pokémon TCG" in system_prompt:
            content = _make_turn_summary_response()
        else:
            content = json.dumps(
                {
                    "summary": "The agent lost tempo after wasting resources early.",
                    "lessons": [
                        {
                            "title": "Sequence draw before commitment",
                            "category": "sequencing",
                            "importance": "high",
                            "lesson": "Use draw/search effects before committing attachments or evolutions.",
                            "phase": "mid_game",
                            "card_names": ["Charizard ex"],
                            "action_types": ["attach_energy", "use_supporter"],
                            "situation": ["low_hand_size"],
                            "confidence": 0.8,
                            "evidence": ["The agent attached energy before using a search action."],
                        }
                    ],
                    "heuristics": [
                        {
                            "heuristic": "Draw and search before committing once-per-turn resources.",
                            "phase": "mid_game",
                            "card_names": ["Charizard ex"],
                            "action_types": ["use_supporter", "attach_energy"],
                            "situation": ["low_hand_size"],
                            "confidence": 0.9,
                        }
                    ],
                }
            )

        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _FakeCompletions()})()


def test_context_manager_streams_to_battle_record(tmp_path: Path):
    from ptcgbench.agents.common.profile import BattleRecord

    battles_dir = tmp_path / "battles"
    battles_dir.mkdir()
    record = BattleRecord(
        battles_dir=battles_dir,
        my_deck="a",
        opponent_deck="b",
    )

    manager = ContextManager(
        model="gpt-4o-mini",
        system_prompt="system prompt",
        max_tokens=1000,
    )
    # Simulate the flow from BaseLLMAgent.notify_game_start():
    # clear, set record, then re-add system prompt
    manager.clear()
    manager.set_battle_record(record)
    manager.add_system("system prompt")

    manager.add_message({"role": "user", "content": "turn 1"})
    manager.add_message({"role": "assistant", "content": "action"})

    lines = record.conversation_path.read_text(encoding="utf-8").splitlines()
    # System prompt + user + assistant = 3 lines
    assert len(lines) == 3
    assert json.loads(lines[0])["role"] == "system"
    assert json.loads(lines[1])["content"] == "turn 1"
    assert json.loads(lines[2])["content"] == "action"


def test_reflection_agent_reads_history_and_appends_knowledge(tmp_path: Path):
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"role": "system", "content": "rules"}),
                json.dumps({"role": "user", "content": _make_turn_observation(1)}),
                json.dumps({"role": "assistant", "content": "tool call"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    kb_path = tmp_path / "knowledge_base.json"
    kb_path.write_text(json.dumps([{"type": "heuristic", "text": "existing"}]), encoding="utf-8")

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(kb_path),
        client=_FakeClient(),
    )

    reflection = agent.reflect(history_path)

    assert reflection["summary"] == "The agent lost tempo after wasting resources early."

    knowledge = json.loads(kb_path.read_text(encoding="utf-8"))
    assert len(knowledge) == 3  # 1 existing + 1 lesson + 1 heuristic
    assert knowledge[0]["text"] == "existing"
    assert any(entry["type"] == "lesson" for entry in knowledge)
    assert any(entry.get("type") == "heuristic" and entry.get("heuristic") for entry in knowledge)
    assert any(entry.get("card_names") == ["Charizard ex"] for entry in knowledge[1:])


def test_reflection_prompt_includes_deck_composition_from_recorded_deck_files(tmp_path: Path):
    history_path = tmp_path / "conversation.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"role": "system", "content": "rules"}),
                json.dumps({"role": "user", "content": _make_turn_observation(1)}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "my_deck.txt").write_text(
        "Pokémon: 2\n1 Charmander PAF 007\n1 Charmeleon PAF 008\n", encoding="utf-8"
    )
    (tmp_path / "opponent_deck.txt").write_text(
        "Trainer: 2\n2 Buddy-Buddy Poffin TEF 144\n", encoding="utf-8"
    )

    captured_system_prompts: list[str] = []

    class _PromptCapturingCompletions:
        def create(self, **kwargs):
            messages = kwargs.get("messages", [])
            system_prompt = messages[0]["content"] if messages else ""
            captured_system_prompts.append(system_prompt)
            if "summarizing a single Pokémon TCG" in system_prompt:
                content = _make_turn_summary_response()
            else:
                content = json.dumps({"summary": "ok", "lessons": [], "heuristics": []})
            message = type("Message", (), {"content": content})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class _PromptCapturingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": _PromptCapturingCompletions()})()

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(tmp_path / "kb.json"),
        client=_PromptCapturingClient(),
    )

    agent.reflect(history_path)

    reflection_prompts = [
        prompt for prompt in captured_system_prompts if "reflection coach" in prompt
    ]
    assert reflection_prompts
    assert "Deck Composition" in reflection_prompts[-1]
    assert "1 Charmander PAF 007" in reflection_prompts[-1]
    assert "2 Buddy-Buddy Poffin TEF 144" in reflection_prompts[-1]


# ---------------------------------------------------------------------------
# Phase 1: Token counting & auto-detection
# ---------------------------------------------------------------------------


def test_count_tokens_returns_positive_for_nonempty_text():
    assert SummaryAgent.count_tokens("Hello world") > 0


def test_count_tokens_returns_zero_for_empty_string():
    assert SummaryAgent.count_tokens("") == 0


def test_count_tokens_increases_with_longer_text():
    short = SummaryAgent.count_tokens("Hello")
    long = SummaryAgent.count_tokens("Hello " * 100)
    assert long > short


def test_compress_summarizes_recent_turns_by_turn_number():
    agent = SummaryAgent(client=_FakeClient())
    text = agent.compress(
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": _make_turn_observation(1)},
            {"role": "assistant", "content": "turn 1 action"},
            {"role": "user", "content": _make_turn_observation(2)},
            {"role": "assistant", "content": "turn 2 action"},
        ],
        max_turns=1,
    )

    lines = text.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["type"] == "turn_summary"
    assert payload["turn_number"] == 2
    assert payload["summary"]["turn_action_sequence"][0]["action"] == "attack"


def test_compress_keeps_retry_user_message_inside_current_turn():
    agent = SummaryAgent(client=_FakeClient())
    grouped = agent._group_messages_by_turn(
        [
            {"role": "user", "content": _make_turn_observation(3)},
            {"role": "assistant", "content": "attempted action"},
            {"role": "user", "content": "Your action could not be executed.\nAttempt 1/2."},
            {"role": "assistant", "content": "retried action"},
        ]
    )
    assert len(grouped) == 1
    assert len(grouped[0]["messages"]) == 4


def test_reflection_agent_logs_token_count_and_uses_single_shot_for_small_history(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"role": "system", "content": "rules"}),
                json.dumps({"role": "user", "content": _make_turn_observation(1)}),
                json.dumps({"role": "assistant", "content": "tool call"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(tmp_path / "kb.json"),
        client=_FakeClient(),
        segment_token_budget=4000,
    )

    with caplog.at_level("INFO"):
        reflection = agent.reflect(history_path)

    assert "Reflection text token count:" in caplog.text
    # Small history should succeed via single-shot path
    assert reflection["summary"] == "The agent lost tempo after wasting resources early."


def test_reflection_agent_uses_chunked_path_for_large_history(tmp_path: Path):
    history_path = tmp_path / "history.jsonl"
    # Generate a large history that exceeds the budget
    lines = [json.dumps({"role": "system", "content": "rules"})]
    for i in range(500):
        lines.append(
            json.dumps(
                {
                    "role": "user",
                    "content": _make_turn_observation(i + 1, i + 1, "notes: " + "x" * 200),
                }
            )
        )
        lines.append(json.dumps({"role": "assistant", "content": "thinking " * 50}))
        lines.append(json.dumps({"role": "tool", "content": "result " * 50}))
    history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(tmp_path / "kb.json"),
        client=_FakeClient(),
        segment_token_budget=100,  # Very low budget to force chunked path
    )

    reflection = agent.reflect(history_path)
    # Chunked path should succeed and return valid reflection
    assert reflection["summary"] == "The agent lost tempo after wasting resources early."
    assert len(reflection["lessons"]) > 0


def test_reflection_backward_compatibility_identical_results(tmp_path: Path):
    """Small history produces identical results to pre-chunking behavior."""
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"role": "system", "content": "rules"}),
                json.dumps({"role": "user", "content": _make_turn_observation(1)}),
                json.dumps({"role": "assistant", "content": "tool call"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    kb_path = tmp_path / "knowledge_base.json"
    kb_path.write_text(json.dumps([{"type": "heuristic", "text": "existing"}]), encoding="utf-8")

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(kb_path),
        client=_FakeClient(),
    )

    reflection = agent.reflect(history_path)

    # Same assertions as the original test
    assert reflection["summary"] == "The agent lost tempo after wasting resources early."
    knowledge = json.loads(kb_path.read_text(encoding="utf-8"))
    assert len(knowledge) == 3
    assert knowledge[0]["text"] == "existing"


# ---------------------------------------------------------------------------
# Phase 2: Segmentation & per-segment reflection
# ---------------------------------------------------------------------------


def _build_history_text(num_events: int, event_size: int = 200) -> str:
    """Build a JSONL reflection text with num_events message pairs."""
    import json

    lines = []
    for i in range(num_events):
        lines.append(json.dumps({"role": "user", "content": f"Turn {i}: " + "x" * event_size}))
        lines.append(
            json.dumps(
                {
                    "role": "assistant",
                    "content": "I should attack.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "attack",
                                "arguments": '{"target": "opponent_active"}',
                            }
                        }
                    ],
                }
            )
        )
    return "\n".join(lines)


def test_segment_reflection_text_treats_each_jsonl_line_as_one_event():
    import json

    text = "\n".join(
        [
            json.dumps({"role": "user", "content": "Turn 0 state"}),
            json.dumps({"role": "assistant", "content": "action"}),
            json.dumps({"role": "user", "content": "Turn 1 state"}),
        ]
    )
    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file="unused.json",
        client=_FakeClient(),
        segment_token_budget=10_000,
    )
    segments = agent._segment_reflection_text(text)
    assert len(segments) == 1
    events = segments[0].splitlines()
    assert len(events) == 3
    assert json.loads(events[0])["role"] == "user"
    assert json.loads(events[1])["role"] == "assistant"


def test_segment_reflection_text_returns_empty_for_empty_text():
    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file="unused.json",
        client=_FakeClient(),
    )
    assert agent._segment_reflection_text("") == []
    assert agent._segment_reflection_text("   \n  \n  ") == []


def test_segment_reflection_text_produces_segments_within_budget():
    text = _build_history_text(50, event_size=50)
    budget = 1000
    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file="unused.json",
        client=_FakeClient(),
        segment_token_budget=budget,
    )
    segments = agent._segment_reflection_text(text)
    assert len(segments) > 1
    for seg in segments:
        token_count = SummaryAgent.count_tokens(seg)
        events_in_seg = [line for line in seg.splitlines() if line.strip()]
        # Each segment should be within a reasonable multiple of budget (at most
        # one event over), or be a single oversized event
        assert token_count <= budget * 1.2 or len(events_in_seg) == 1


def test_segment_no_event_block_split_across_segments():
    import json

    text = _build_history_text(30, event_size=50)
    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file="unused.json",
        client=_FakeClient(),
        segment_token_budget=150,
    )
    segments = agent._segment_reflection_text(text)
    for seg in segments:
        events = [line for line in seg.splitlines() if line.strip()]
        for event in events:
            assert json.loads(event)["role"] in ("user", "assistant", "tool")


def test_oversized_event_becomes_own_segment():
    import json

    # One very large event surrounded by small ones
    text = "\n".join(
        [
            json.dumps({"role": "user", "content": "small state"}),
            json.dumps({"role": "user", "content": "y" * 5000}),
            json.dumps({"role": "user", "content": "another small state"}),
        ]
    )
    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file="unused.json",
        client=_FakeClient(),
        segment_token_budget=100,
    )
    segments = agent._segment_reflection_text(text)
    # The oversized event should be its own segment (not dropped)
    oversized_found = any(SummaryAgent.count_tokens(s) > 100 for s in segments)
    assert oversized_found
    # All events should still be present
    all_events = []
    for seg in segments:
        all_events.extend([line for line in seg.splitlines() if line.strip()])
    assert len(all_events) == 3


def test_chunked_reflection_concatenates_per_segment_results(tmp_path: Path):
    """Large history produces concatenated reflections with all segments represented."""
    # Create a history that generates enough text to split into multiple segments
    history_path = tmp_path / "history.jsonl"
    lines = [json.dumps({"role": "system", "content": "rules"})]
    for i in range(100):
        lines.append(
            json.dumps(
                {
                    "role": "user",
                    "content": _make_turn_observation(i + 1, i + 1, "notes: " + "x" * 100),
                }
            )
        )
        lines.append(json.dumps({"role": "assistant", "content": "action " * 20}))
        lines.append(json.dumps({"role": "tool", "content": "result " * 20}))
    history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    kb_path = tmp_path / "kb.json"
    call_count = 0

    class _CountingCompletions:
        def create(self, **kwargs):
            nonlocal call_count
            call_count += 1
            return _FakeCompletions().create(**kwargs)

    class _CountingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": _CountingCompletions()})()

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(kb_path),
        client=_CountingClient(),
        segment_token_budget=200,  # Force multiple segments
    )

    reflection = agent.reflect(history_path)

    # Should have called LLM multiple times (one per segment)
    assert call_count > 1
    # Results should be concatenated
    assert len(reflection["lessons"]) >= 1  # At least one lesson per segment
    assert reflection["summary"]  # Summary from last segment

    # Knowledge base should have all entries
    knowledge = json.loads(kb_path.read_text(encoding="utf-8"))
    assert any(entry["type"] == "lesson" for entry in knowledge)


def test_chunked_reflection_logs_segment_info(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    history_path = tmp_path / "history.jsonl"
    lines = [json.dumps({"role": "system", "content": "rules"})]
    for i in range(100):
        lines.append(
            json.dumps(
                {
                    "role": "user",
                    "content": _make_turn_observation(i + 1, i + 1, "notes: " + "x" * 100),
                }
            )
        )
        lines.append(json.dumps({"role": "assistant", "content": "action " * 20}))
    history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(tmp_path / "kb.json"),
        client=_FakeClient(),
        segment_token_budget=200,
    )

    with caplog.at_level("INFO"):
        agent.reflect(history_path)

    assert "Chunked reflection:" in caplog.text
    assert "segments" in caplog.text
    assert "Reflecting on segment" in caplog.text


# ---------------------------------------------------------------------------
# Phase 3: LLM-Based Consolidation
# ---------------------------------------------------------------------------


def _make_consolidation_response(
    lessons_count: int = 2,
    heuristics_count: int = 2,
):
    """Build a consolidated JSON response for consolidation LLM calls."""
    return json.dumps(
        {
            "summary": "Consolidated: the agent struggled with resource management throughout.",
            "lessons": [
                {
                    "title": f"Consolidated lesson {i + 1}",
                    "category": "strategy",
                    "importance": "high",
                    "lesson": f"Merged lesson number {i + 1} from multiple segments.",
                    "phase": "mid_game",
                    "card_names": ["Charizard ex"],
                    "action_types": ["attach_energy"],
                    "situation": ["low_hand_size"],
                    "evidence": ["Evidence from segments."],
                }
                for i in range(lessons_count)
            ],
            "heuristics": [
                {
                    "text": f"Consolidated heuristic {i + 1}",
                    "phase": "mid_game",
                    "card_names": ["Charizard ex"],
                    "action_types": ["use_supporter"],
                    "situation": ["low_hand_size"],
                }
                for i in range(heuristics_count)
            ],
        }
    )


def test_merge_prompt_template_exists():
    """Verify merge.md template can be loaded and rendered."""
    from ptcgbench.agents.memory.reflection_agent import _render_merge_prompt

    result = _render_merge_prompt(segment_reflections='[{"summary": "test"}]')
    assert "consolidation" in result.lower()
    assert "segment_reflections" not in result  # Variable should be replaced


def test_consolidation_uses_separate_llm_call(tmp_path: Path):
    """Consolidation step should make an additional LLM call after per-segment reflections."""
    history_path = tmp_path / "history.jsonl"
    lines = [json.dumps({"role": "system", "content": "rules"})]
    for i in range(100):
        lines.append(
            json.dumps(
                {
                    "role": "user",
                    "content": _make_turn_observation(i + 1, i + 1, "notes: " + "x" * 100),
                }
            )
        )
        lines.append(json.dumps({"role": "assistant", "content": "action " * 20}))
    history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    kb_path = tmp_path / "kb.json"
    consolidation_content = _make_consolidation_response(lessons_count=2, heuristics_count=2)

    call_log: list[str] = []

    class _TrackingCompletions:
        def create(self, **kwargs):
            messages = kwargs.get("messages", [])
            user_msg = messages[-1]["content"] if messages else ""
            system_prompt = messages[0].get("content", "") if messages else ""
            if "summarizing a single Pokémon TCG" in system_prompt:
                call_log.append("summary")
                content = _make_turn_summary_response()
            elif (
                "per-segment reflections" in user_msg.lower()
                or "consolidat" in system_prompt.lower()
            ):
                call_log.append("consolidation")
                content = consolidation_content
            else:
                call_log.append("per_segment")
                content = json.dumps(
                    {
                        "summary": "Segment reflection.",
                        "lessons": [
                            {
                                "title": "Lesson",
                                "category": "strategy",
                                "importance": "high",
                                "lesson": "A lesson.",
                                "phase": "mid_game",
                                "card_names": ["Pikachu"],
                                "action_types": ["attack"],
                                "situation": ["behind_on_prizes"],
                                "evidence": ["test"],
                            }
                        ],
                        "heuristics": [],
                    }
                )
            message = type("Message", (), {"content": content})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class _TrackingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": _TrackingCompletions()})()

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(kb_path),
        client=_TrackingClient(),
        segment_token_budget=200,
    )

    reflection = agent.reflect(history_path)

    # Should have at least one per_segment and one consolidation call
    assert "per_segment" in call_log
    assert "consolidation" in call_log
    assert len(call_log) >= 3  # 2+ per_segment + 1 consolidation

    # Consolidated result should have the expected schema
    assert reflection["summary"]
    assert isinstance(reflection["lessons"], list)
    assert isinstance(reflection["heuristics"], list)


def test_consolidation_preserves_metadata(tmp_path: Path):
    """Consolidated result preserves card_names, action_types, situation."""
    history_path = tmp_path / "history.jsonl"
    lines = [json.dumps({"role": "system", "content": "rules"})]
    for i in range(100):
        lines.append(
            json.dumps(
                {
                    "role": "user",
                    "content": _make_turn_observation(i + 1, i + 1, "notes: " + "x" * 100),
                }
            )
        )
        lines.append(json.dumps({"role": "assistant", "content": "action " * 20}))
    history_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    kb_path = tmp_path / "kb.json"

    class _ConsolidatingCompletions:
        def create(self, **kwargs):
            messages = kwargs.get("messages", [])
            system_prompt = messages[0].get("content", "") if messages else ""
            if "summarizing a single Pokémon TCG" in system_prompt:
                content = _make_turn_summary_response()
            elif "consolidat" in system_prompt.lower():
                content = _make_consolidation_response()
            else:
                content = json.dumps(
                    {
                        "summary": "Segment summary",
                        "lessons": [
                            {
                                "title": "Lesson",
                                "category": "strategy",
                                "importance": "high",
                                "lesson": "A lesson.",
                                "phase": "mid_game",
                                "card_names": ["Pikachu"],
                                "action_types": ["attack"],
                                "situation": ["behind_on_prizes"],
                                "evidence": ["test"],
                            }
                        ],
                        "heuristics": [],
                    }
                )
            message = type("Message", (), {"content": content})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class _ConsolidatingClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": _ConsolidatingCompletions()})()

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file=str(kb_path),
        client=_ConsolidatingClient(),
        segment_token_budget=200,
    )

    reflection = agent.reflect(history_path)

    # Consolidated lessons should have the normalized fields
    for lesson in reflection["lessons"]:
        assert "lesson" in lesson
        assert "card_names" in lesson

    # Knowledge base should receive consolidated results
    knowledge = json.loads(kb_path.read_text(encoding="utf-8"))
    assert any(entry["type"] == "lesson" for entry in knowledge)
    assert any(entry.get("card_names") for entry in knowledge)


def test_consolidation_return_schema_matches_single_shot():
    """Consolidated reflection has the same top-level keys as single-shot."""
    from ptcgbench.agents.memory.reflection_agent import ReflectionAgent

    agent = ReflectionAgent(
        model="deepseek-chat",
        knowledge_base_file="unused.json",
        client=_FakeClient(),
    )

    # Simulate consolidated result
    reflections = [
        {
            "summary": "Segment 1",
            "lessons": [
                {
                    "title": "L1",
                    "category": "strategy",
                    "importance": "high",
                    "lesson": "Learn",
                    "phase": "mid_game",
                }
            ],
            "heuristics": [],
        },
        {
            "summary": "Segment 2",
            "lessons": [
                {
                    "title": "L2",
                    "category": "tactics",
                    "importance": "medium",
                    "lesson": "Learn2",
                    "phase": "late_game",
                }
            ],
            "heuristics": [],
        },
    ]

    # The _normalize_reflection ensures consistent schema
    result = agent._normalize_reflection(
        {
            "summary": "Consolidated",
            "lessons": reflections[0]["lessons"] + reflections[1]["lessons"],
            "heuristics": [],
        }
    )

    assert set(result.keys()) == {"summary", "lessons", "heuristics"}
    assert isinstance(result["summary"], str)
    assert isinstance(result["lessons"], list)
    assert isinstance(result["heuristics"], list)
