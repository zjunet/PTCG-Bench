"""Tests for SkillRegistry — discovery, parsing, catalog, and resources."""

from __future__ import annotations

from pathlib import Path

from ptcgbench.agents.skills.skill_registry import Skill, SkillRegistry


def _write_skill(
    skills_dir: Path,
    name: str,
    description: str = "A test skill.",
    body: str = "# Test Skill\nSome instructions.",
) -> Path:
    """Helper to create a skill directory with a SKILL.md."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_md


class TestSkillDataclass:
    def test_list_resources(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\n---\n")
        (skill_dir / "REFERENCE.md").write_text("ref")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "run.py").write_text("code")

        skill = Skill(
            name="my-skill",
            description="test",
            location=skill_dir / "SKILL.md",
            body="body",
        )
        resources = skill.list_resources()
        assert "REFERENCE.md" in resources
        assert "scripts" not in resources  # directories excluded
        assert "SKILL.md" not in resources

    def test_load_resource(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\n---\n")
        (skill_dir / "REFERENCE.md").write_text("ref content", encoding="utf-8")

        skill = Skill(name="my-skill", description="test", location=skill_dir / "SKILL.md")
        assert skill.load_resource("REFERENCE.md") == "ref content"
        assert skill.load_resource("nonexistent.md") is None


class TestDiscovery:
    def test_discovers_skills(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "alpha", description="Alpha skill")
        _write_skill(skills_dir, "beta", description="Beta skill")

        registry = SkillRegistry(skills_dir)
        assert set(registry.skill_names()) == {"alpha", "beta"}

    def test_empty_directory(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        registry = SkillRegistry(skills_dir)
        assert registry.skill_names() == []

    def test_nonexistent_directory(self, tmp_path: Path):
        registry = SkillRegistry(tmp_path / "no-such-dir")
        assert registry.skill_names() == []
        assert registry.build_catalog() == ""

    def test_skips_dirs_without_skill_md(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "no-skill").mkdir()
        _write_skill(skills_dir, "has-skill", description="Valid")

        registry = SkillRegistry(skills_dir)
        assert registry.skill_names() == ["has-skill"]

    def test_skips_files_in_skills_dir(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "README.md").write_text("Not a skill")
        _write_skill(skills_dir, "real-skill", description="Valid")

        registry = SkillRegistry(skills_dir)
        assert registry.skill_names() == ["real-skill"]

    def test_duplicate_skill_name_keeps_first(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "alpha", description="First")
        # Manually create another "alpha" by writing a different name in frontmatter
        dup_dir = skills_dir / "alpha-copy"
        dup_dir.mkdir()
        (dup_dir / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Duplicate\n---\n\nBody\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(skills_dir)
        skill = registry.get("alpha")
        assert skill is not None
        assert skill.description == "First"


class TestParsing:
    def test_parses_frontmatter_and_body(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "test-skill", description="Desc", body="# Body\nContent")

        registry = SkillRegistry(skills_dir)
        skill = registry.get("test-skill")
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "Desc"
        assert "# Body" in skill.body
        assert "Content" in skill.body

    def test_missing_description_skipped(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "no-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\n\nBody\n", encoding="utf-8")

        registry = SkillRegistry(skills_dir)
        assert registry.get("no-desc") is None

    def test_empty_description_skipped(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "empty-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: empty-desc\ndescription: ''\n---\n\nBody\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(skills_dir)
        assert registry.get("empty-desc") is None

    def test_unparseable_yaml_skipped(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "bad-yaml"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: [invalid: yaml: syntax\n---\n\nBody\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(skills_dir)
        assert registry.get("bad-yaml") is None

    def test_no_frontmatter_skipped(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "no-front"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Just markdown, no frontmatter.", encoding="utf-8")

        registry = SkillRegistry(skills_dir)
        assert registry.get("no-front") is None

    def test_name_mismatch_with_directory_warns_but_loads(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "dir-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: different-name\ndescription: Has desc\n---\n\nBody\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(skills_dir)
        skill = registry.get("different-name")
        assert skill is not None
        assert skill.description == "Has desc"

    def test_missing_name_uses_directory_name(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "fallback-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: Has desc\n---\n\nBody\n", encoding="utf-8"
        )

        registry = SkillRegistry(skills_dir)
        skill = registry.get("fallback-name")
        assert skill is not None
        assert skill.name == "fallback-name"


class TestCatalog:
    def test_builds_catalog(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "alpha", description="Alpha skill")
        _write_skill(skills_dir, "beta", description="Beta skill")

        registry = SkillRegistry(skills_dir)
        catalog = registry.build_catalog()
        assert "<available_skills>" in catalog
        assert "<name>alpha</name>" in catalog
        assert "<description>Alpha skill</description>" in catalog
        assert "<name>beta</name>" in catalog
        assert "</available_skills>" in catalog

    def test_empty_catalog_returns_empty_string(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        registry = SkillRegistry(skills_dir)
        assert registry.build_catalog() == ""


class TestResourceLoading:
    def test_list_resources(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "with-resources", description="Has resources")
        skill_dir = skills_dir / "with-resources"
        (skill_dir / "REFERENCE.md").write_text("ref", encoding="utf-8")
        (skill_dir / "data.csv").write_text("a,b", encoding="utf-8")

        registry = SkillRegistry(skills_dir)
        skill = registry.get("with-resources")
        assert skill is not None
        resources = skill.list_resources()
        assert "REFERENCE.md" in resources
        assert "data.csv" in resources

    def test_load_resource_content(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "with-resources", description="Has resources")
        skill_dir = skills_dir / "with-resources"
        (skill_dir / "REFERENCE.md").write_text("Detailed reference content", encoding="utf-8")

        registry = SkillRegistry(skills_dir)
        skill = registry.get("with-resources")
        assert skill is not None
        content = skill.load_resource("REFERENCE.md")
        assert content == "Detailed reference content"

    def test_load_nonexistent_resource(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "skill", description="A skill")

        registry = SkillRegistry(skills_dir)
        skill = registry.get("skill")
        assert skill is not None
        assert skill.load_resource("nope.md") is None
