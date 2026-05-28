"""Skill discovery, parsing, and catalog management."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


@dataclass
class Skill:
    """A parsed skill with its metadata and content."""

    name: str
    description: str
    location: Path
    body: str = ""
    skill_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.skill_dir = self.location.parent

    def list_resources(self) -> list[str]:
        """Return filenames of non-SKILL.md files in the skill directory."""
        if not self.skill_dir.is_dir():
            return []
        return sorted(
            f.name for f in self.skill_dir.iterdir() if f.is_file() and f.name != "SKILL.md"
        )

    def load_resource(self, filename: str) -> str | None:
        """Load a resource file by filename. Returns None if not found."""
        path = self.skill_dir / filename
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return None


class SkillRegistry:
    """Discovers and manages skills from a skills/ directory."""

    def __init__(self, skills_dir: Path) -> None:
        self._skills: dict[str, Skill] = {}
        self._skills_dir = skills_dir
        self._discover()

    def _discover(self) -> None:
        """Scan the skills directory for SKILL.md files and parse them."""
        if not self._skills_dir.is_dir():
            logger.debug("Skills directory does not exist: %s", self._skills_dir)
            return

        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue
            skill = self._parse_skill(skill_md)
            if skill is not None:
                if skill.name in self._skills:
                    logger.warning("Duplicate skill name '%s', keeping first", skill.name)
                else:
                    self._skills[skill.name] = skill

    def _parse_skill(self, path: Path) -> Skill | None:
        """Parse a SKILL.md file into a Skill. Returns None on failure."""
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("Cannot read %s: %s", path, e)
            return None

        match = _FRONTMATTER_RE.match(content)
        if not match:
            logger.error("No valid frontmatter in %s", path)
            return None

        yaml_block, body = match.group(1), match.group(2)

        try:
            frontmatter = yaml.safe_load(yaml_block)
        except yaml.YAMLError as e:
            logger.error("Malformed YAML in %s: %s", path, e)
            return None

        if not isinstance(frontmatter, dict):
            logger.error("Frontmatter is not a mapping in %s", path)
            return None

        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")

        if not description or not str(description).strip():
            logger.warning("Missing or empty description in %s, skipping", path)
            return None

        name = str(name).strip() or path.parent.name
        expected_dir = path.parent.name
        if name != expected_dir:
            logger.warning("Skill name '%s' doesn't match directory '%s'", name, expected_dir)

        return Skill(
            name=name,
            description=str(description).strip(),
            location=path,
            body=body.strip(),
        )

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def skill_names(self) -> list[str]:
        return sorted(self._skills.keys())

    def build_catalog(self) -> str:
        """Build a formatted catalog string for the system prompt."""
        if not self._skills:
            return ""
        lines = ["<available_skills>"]
        for name in self.skill_names():
            skill = self._skills[name]
            lines.append(f"  <skill>")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{skill.description}</description>")
            lines.append(f"  </skill>")
        lines.append("</available_skills>")
        return "\n".join(lines)
