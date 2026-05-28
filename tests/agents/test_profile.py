"""Tests for AgentConfig, AgentProfile, and BattleRecord."""

from __future__ import annotations

import json
from pathlib import Path

from ptcgbench.agents.common.profile import AgentConfig, AgentProfile, BattleRecord


class TestAgentConfig:
    def test_default_values(self):
        config = AgentConfig(name="llm_deepseek-chat", model="deepseek-chat", architecture="llm")
        assert config.architecture == "llm"
        assert config.temperature == 0.8
        assert config.max_completion_tokens == 2048
        assert config.max_retries == 2
        assert config.max_tokens == 80000
        assert config.created_at is not None

    def test_custom_values(self):
        config = AgentConfig(
            name="llm_qwen3.5-flash",
            model="qwen3.5-flash",
            architecture="llm",
            temperature=0.5,
            max_completion_tokens=4096,
            max_retries=3,
            max_tokens=100000,
        )
        assert config.temperature == 0.5
        assert config.max_completion_tokens == 4096

    def test_serialization_round_trip(self):
        config = AgentConfig(name="llm_deepseek-chat", model="deepseek-chat", architecture="llm")
        data = config.model_dump()
        restored = AgentConfig.model_validate(data)
        assert restored == config


class TestAgentProfile:
    def test_creates_directory_structure(self, tmp_path: Path):
        profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        profile.ensure_dirs()

        agent_dir = tmp_path / "llm_deepseek-chat"
        assert agent_dir.is_dir()
        assert (agent_dir / "decks").is_dir()
        assert (agent_dir / "battles").is_dir()
        assert (agent_dir / "memory").is_dir()
        assert (agent_dir / "skills").is_dir()

    def test_ensure_dirs_idempotent(self, tmp_path: Path):
        profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        profile.ensure_dirs()
        profile.ensure_dirs()  # Should not raise

        agent_dir = tmp_path / "llm_deepseek-chat"
        assert agent_dir.is_dir()

    def test_config_round_trip(self, tmp_path: Path):
        profile = AgentProfile(name="llm_deepseek-chat", root=tmp_path)
        config = AgentConfig(name="llm_deepseek-chat", model="deepseek-chat", architecture="llm")
        profile.save_config(config)

        loaded = profile.load_config()
        assert loaded.name == "llm_deepseek-chat"
        assert loaded.model == "deepseek-chat"
        assert loaded.architecture == "llm"
        assert loaded.temperature == 0.8


class TestBattleRecord:
    def test_creates_timestamped_directory(self, tmp_path: Path):
        battles_dir = tmp_path / "battles"
        battles_dir.mkdir()
        record = BattleRecord(
            battles_dir=battles_dir,
            my_deck="charizard-ex",
            opponent_deck="gardevoir-ex",
        )
        assert record.record_dir.parent == battles_dir
        assert "charizard-ex_vs_gardevoir-ex" in record.record_dir.name
        assert record.record_dir.is_dir()

    def test_unique_dirs_via_uuid(self, tmp_path: Path):
        battles_dir = tmp_path / "battles"
        battles_dir.mkdir()
        r1 = BattleRecord(
            battles_dir=battles_dir,
            my_deck="charizard-ex",
            opponent_deck="gardevoir-ex",
        )
        r2 = BattleRecord(
            battles_dir=battles_dir,
            my_deck="charizard-ex",
            opponent_deck="gardevoir-ex",
        )
        assert r1.record_dir != r2.record_dir
        # Each record gets a unique UUID suffix, so both dirs are distinct
        assert r1.record_dir.is_dir()
        assert r2.record_dir.is_dir()

    def test_append_conversation(self, tmp_path: Path):
        battles_dir = tmp_path / "battles"
        battles_dir.mkdir()
        record = BattleRecord(
            battles_dir=battles_dir,
            my_deck="a",
            opponent_deck="b",
        )
        record.append_conversation({"role": "user", "content": "hello"})
        record.append_conversation({"role": "assistant", "content": "world"})

        lines = record.conversation_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["content"] == "hello"
        assert json.loads(lines[1])["content"] == "world"

    def test_append_event(self, tmp_path: Path):
        battles_dir = tmp_path / "battles"
        battles_dir.mkdir()
        record = BattleRecord(
            battles_dir=battles_dir,
            my_deck="a",
            opponent_deck="b",
        )
        record.append_event({"type": "action", "data": "test"})
        lines = record.events_path.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "action"

    def test_write_summary(self, tmp_path: Path):
        battles_dir = tmp_path / "battles"
        battles_dir.mkdir()
        record = BattleRecord(
            battles_dir=battles_dir,
            my_deck="a",
            opponent_deck="b",
            agent_name="llm_deepseek-chat",
            opponent_name="random",
        )
        record.write_summary(
            result="win",
            turn_count=15,
            my_prizes_remaining=3,
            opponent_prizes_remaining=0,
        )
        summary = json.loads(record.summary_path.read_text())
        assert summary["result"] == "win"
        assert summary["turn_count"] == 15
        assert summary["agent_name"] == "llm_deepseek-chat"
        assert summary["my_deck"] == "a"
        assert summary["opponent_deck"] == "b"
        assert summary["my_prizes_remaining"] == 3
        assert summary["opponent_prizes_remaining"] == 0


class TestDeckManagement:
    def test_copy_deck(self, tmp_path: Path):
        profile = AgentProfile(name="llm_test", root=tmp_path)
        profile.ensure_dirs()
        # Create a fake deck file
        deck_file = tmp_path / "charizard_ex.txt"
        deck_file.write_text("Charizard ex\nPidgey\n", encoding="utf-8")

        dest = profile.copy_deck(deck_file)
        assert dest.exists()
        assert dest.name == "charizard_ex.txt"
        assert dest.read_text() == "Charizard ex\nPidgey\n"

    def test_copy_deck_idempotent(self, tmp_path: Path):
        profile = AgentProfile(name="llm_test", root=tmp_path)
        profile.ensure_dirs()
        deck_file = tmp_path / "deck.txt"
        deck_file.write_text("original", encoding="utf-8")

        dest1 = profile.copy_deck(deck_file)
        # Modify source after first copy
        deck_file.write_text("modified", encoding="utf-8")
        dest2 = profile.copy_deck(deck_file)
        assert dest1 == dest2
        # Should still have original content (no-op)
        assert dest1.read_text() == "original"

    def test_copy_deck_normalizes_name(self, tmp_path: Path):
        profile = AgentProfile(name="llm_test", root=tmp_path)
        profile.ensure_dirs()
        deck_file = tmp_path / "My Cool Deck.txt"
        deck_file.write_text("cards\n", encoding="utf-8")

        dest = profile.copy_deck(deck_file)
        assert dest.name == "my_cool_deck.txt"

    def test_deck_name_from_path(self):
        assert AgentProfile.deck_name_from_path("charizard_ex.txt") == "charizard-ex"
        assert AgentProfile.deck_name_from_path("/path/to/gardevoir_ex.txt") == "gardevoir-ex"
        assert AgentProfile.deck_name_from_path("deck.txt") == "deck"
