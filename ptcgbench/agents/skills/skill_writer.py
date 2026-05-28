"""SkillWriter — generates and updates deck skills from game reflections."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI

from ptcgbench.agents.common.model_client import build_client, chat_completion_with_retry

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    keep_trailing_newline=True,
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)

_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List all existing skills with their names and descriptions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Read the full content of an existing skill file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact skill name as returned by list_skills.",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": "Write a new skill file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Full SKILL.md content including YAML frontmatter.",
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refine_skill",
            "description": "Update an existing skill by replacing its entire content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact skill name to update, as returned by list_skills.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full updated SKILL.md content including frontmatter.",
                    },
                },
                "required": ["name", "content"],
            },
        },
    },
]

_MAX_TURNS = 6


def _validate_frontmatter(content: str) -> tuple[bool, str]:
    """Check that content has valid YAML frontmatter with name + description."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return False, "No YAML frontmatter found."
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        return False, f"Malformed YAML: {e}"
    if not isinstance(frontmatter, dict):
        return False, "Frontmatter is not a YAML mapping."
    if not str(frontmatter.get("name", "")).strip():
        return False, "Missing or empty 'name' in frontmatter."
    if not str(frontmatter.get("description", "")).strip():
        return False, "Missing or empty 'description' in frontmatter."
    return True, ""


def _has_insight_data(reflection: dict[str, Any]) -> bool:
    """Return True if the reflection contains any lessons or heuristics."""
    return bool(reflection.get("lessons")) or bool(reflection.get("heuristics"))


class SkillWriter:
    """Generates deck-specific skill files from game reflection data."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        skills_dir: Path | None = None,
        temperature: float = 0.3,
        max_completion_tokens: int = 3000,
        client: OpenAI | None = None,
    ) -> None:
        self.model = model
        self.skills_dir = skills_dir
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self._client = client or build_client(self.model)

    def write(
        self,
        reflection: dict[str, Any],
        battle_summary: dict[str, Any],
    ) -> Path | None:
        """Generate or update a skill from reflection data and write to disk.

        Returns the path to the created/updated SKILL.md, or None if skipped.
        """
        if not _has_insight_data(reflection):
            logger.info("Skipping skill creation: no lessons or heuristics.")
            return None
        if self.skills_dir is None:
            logger.warning("No skills_dir configured.")
            return None
        return self._run_agent(reflection, battle_summary)

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------

    def _run_agent(
        self,
        reflection: dict[str, Any],
        battle_summary: dict[str, Any],
    ) -> Path | None:
        messages: list[dict] = [
            {
                "role": "system",
                "content": _jinja_env.get_template("skill_writer/system.md").render(),
            },
            {"role": "user", "content": self._build_task_message(reflection, battle_summary)},
        ]
        written_path: Path | None = None

        for _ in range(_MAX_TURNS):
            try:
                response = chat_completion_with_retry(
                    self._client,
                    model=self.model,
                    messages=messages,
                    tools=_TOOLS,
                    temperature=self.temperature,
                    max_completion_tokens=self.max_completion_tokens,
                )
            except Exception as e:
                logger.error("LLM call failed: %s", e)
                break

            message = response.choices[0].message
            messages.append(message.model_dump(exclude_unset=True))

            if not message.tool_calls:
                break

            for tool_call in message.tool_calls:
                result, path = self._execute_tool(tool_call)
                if path is not None:
                    written_path = path
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

            if written_path is not None:
                break

        return written_path

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _execute_tool(self, tool_call: Any) -> tuple[str, Path | None]:
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError:
            return "Error: invalid JSON arguments.", None

        if name == "list_skills":
            return self._tool_list_skills(), None
        if name == "read_skill":
            return self._tool_read_skill(args.get("name", "")), None
        if name == "create_skill":
            return self._tool_create_skill(args.get("content", ""))
        if name == "refine_skill":
            return self._tool_refine_skill(args.get("name", ""), args.get("content", ""))
        return f"Error: unknown tool '{name}'.", None

    def _tool_list_skills(self) -> str:
        catalog: list[dict] = []
        if self.skills_dir and self.skills_dir.is_dir():
            for entry in sorted(self.skills_dir.iterdir()):
                if not entry.is_dir():
                    continue
                skill_md = entry / "SKILL.md"
                if not skill_md.is_file():
                    continue
                try:
                    raw = skill_md.read_text(encoding="utf-8")
                except OSError:
                    continue
                m = _FRONTMATTER_RE.match(raw)
                if not m:
                    continue
                try:
                    fm = yaml.safe_load(m.group(1))
                except yaml.YAMLError:
                    continue
                if isinstance(fm, dict):
                    name = str(fm.get("name", "")).strip()
                    if name:
                        catalog.append(
                            {"name": name, "description": str(fm.get("description", "")).strip()}
                        )
        return json.dumps(catalog)

    def _tool_read_skill(self, name: str) -> str:
        if not name:
            return "Error: name is required."
        path = self._find_skill_path(name)
        if path is None:
            return f"Error: skill '{name}' not found."
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error reading skill: {e}"

    def _tool_create_skill(self, content: str) -> tuple[str, Path | None]:
        if not content:
            return "Error: content is required.", None
        valid, error = _validate_frontmatter(content)
        if not valid:
            return f"Error: invalid frontmatter — {error}", None
        path = self._write_new_skill(content)
        return f"Skill created at {path}.", path

    def _tool_refine_skill(self, name: str, content: str) -> tuple[str, Path | None]:
        if not name or not content:
            return "Error: both name and content are required.", None
        path = self._find_skill_path(name)
        if path is None:
            return f"Error: skill '{name}' not found.", None
        valid, error = _validate_frontmatter(content)
        if not valid:
            return f"Error: invalid frontmatter — {error}", None
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return f"Error writing skill: {e}", None
        logger.info("Skill refined at %s", path)
        return f"Skill '{name}' updated at {path}.", path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_skill_path(self, name: str) -> Path | None:
        """Return the SKILL.md path whose frontmatter name matches exactly."""
        if not self.skills_dir or not self.skills_dir.is_dir():
            return None
        for entry in self.skills_dir.iterdir():
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                raw = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            m = _FRONTMATTER_RE.match(raw)
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1))
            except yaml.YAMLError:
                continue
            if isinstance(fm, dict) and str(fm.get("name", "")).strip() == name:
                return skill_md
        return None

    def _write_new_skill(self, content: str) -> Path:
        """Create a new skill directory named after the skill and write SKILL.md."""
        m = _FRONTMATTER_RE.match(content)
        name = "unnamed-skill"
        if m:
            try:
                fm = yaml.safe_load(m.group(1))
                name = str(fm.get("name", "unnamed-skill")).strip()
            except yaml.YAMLError:
                pass
        skill_dir = self.skills_dir / name.lower().replace(" ", "-")  # type: ignore[operator]
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(content, encoding="utf-8")
        logger.info("Skill written to %s", skill_path)
        return skill_path

    def _build_task_message(
        self,
        reflection: dict[str, Any],
        battle_summary: dict[str, Any],
    ) -> str:
        return _jinja_env.get_template("skill_writer/task.md").render(
            deck_name=battle_summary.get("my_deck", "unknown"),
            result=battle_summary.get("result", "unknown"),
            turn_count=battle_summary.get("turn_count", 0),
            lessons=reflection.get("lessons", []),
            heuristics=reflection.get("heuristics", []),
        )
