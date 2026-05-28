import json
import time

from ptcgbench.agents.memory.summary_agent import SummaryAgent


def _make_turn_observation(turn: str, turn_number: int, timestep: int) -> str:
    return (
        f"turn: {turn}\n"
        f"turn_number: {turn_number}\n"
        f"timestep: {timestep}\n"
        "available_actions:\n"
        "- attack"
    )


class _DummyClient:
    pass


class _OrderedFakeCompletions:
    def create(self, **kwargs):
        messages = kwargs.get("messages", [])
        prompt = messages[0]["content"] if messages else ""
        if "turn: player1" in prompt:
            time.sleep(0.03)
            turn_number = 1
        else:
            time.sleep(0.01)
            turn_number = 2

        content = json.dumps(
            {
                "turn_action_sequence": [{"action": f"turn-{turn_number}"}],
            }
        )
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _OrderedFakeClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _OrderedFakeCompletions()})()


def test_group_messages_by_turn_keeps_tool_roundtrips_inside_same_turn():
    agent = SummaryAgent(client=_DummyClient())
    grouped = agent._group_messages_by_turn(
        [
            {"role": "user", "content": _make_turn_observation("player2", 2, 7)},
            {
                "role": "assistant",
                "content": "I should check what Charmander's attack does.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "query_card",
                            "arguments": '{"card_id": "PAF-007"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "Charmander info",
            },
            {"role": "assistant", "content": "I will use Arven."},
            {"role": "user", "content": _make_turn_observation("player2", 2, 8)},
            {"role": "assistant", "content": "I choose Rare Candy."},
            {"role": "user", "content": _make_turn_observation("player1", 3, 9)},
        ]
    )

    assert len(grouped) == 2
    assert grouped[0]["turn"] == "player2"
    assert grouped[0]["turn_number"] == 2
    assert grouped[0]["timestep"] == 8
    assert len(grouped[0]["messages"]) == 6
    assert grouped[1]["turn"] == "player1"
    assert grouped[1]["turn_number"] == 3


def test_group_messages_by_turn_splits_same_turn_number_when_turn_changes():
    agent = SummaryAgent(client=_DummyClient())
    grouped = agent._group_messages_by_turn(
        [
            {"role": "user", "content": _make_turn_observation("player1", 2, 4)},
            {"role": "assistant", "content": "player1 action"},
            {"role": "user", "content": _make_turn_observation("player2", 2, 5)},
        ]
    )

    assert len(grouped) == 2
    assert grouped[0]["turn"] == "player1"
    assert grouped[1]["turn"] == "player2"


def test_compress_preserves_turn_order_when_summaries_run_in_parallel():
    agent = SummaryAgent(client=_OrderedFakeClient(), summary_max_workers=2)
    text = agent.compress(
        [
            {"role": "user", "content": _make_turn_observation("player1", 1, 1)},
            {"role": "assistant", "content": "player1 action"},
            {"role": "user", "content": _make_turn_observation("player2", 2, 2)},
            {"role": "assistant", "content": "player2 action"},
        ],
        max_turns=2,
    )

    payloads = [json.loads(line) for line in text.splitlines()]
    assert [payload["turn_number"] for payload in payloads] == [1, 2]
    assert [payload["summary"]["turn_action_sequence"][0]["action"] for payload in payloads] == [
        "turn-1",
        "turn-2",
    ]
