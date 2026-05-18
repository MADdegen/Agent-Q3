"""
Agent-Q3 — Skills loader.

Skills are markdown files in /app/skills/ describing capability prompts that
get injected into the system message when their trigger pattern matches the
user query. They override base system prompts for specific tasks.

Skill file format (frontmatter + body):

    ---
    name: deep-research
    description: Multi-source deep research synthesis
    triggers: [research, investigate, analyze deeply, sources]
    roles: [reasoner, coder]
    ---
    When the user asks for research, follow this protocol:
    1. ...

The loader scans the directory on boot, parses every *.md file, and exposes
skill objects through `skills.find_for(query, role)`.
"""

import re
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

SKILLS_DIR = Path("/app/skills")


class Skill:
    __slots__ = ("name", "description", "triggers", "roles", "body", "path")

    def __init__(self, name: str, description: str, triggers: list[str],
                 roles: list[str], body: str, path: str):
        self.name = name
        self.description = description
        self.triggers = [t.lower() for t in triggers]
        self.roles = [r.lower() for r in roles] or ["*"]
        self.body = body
        self.path = path

    def matches(self, query: str, role: str | None = None) -> bool:
        q = query.lower()
        if role and "*" not in self.roles and role.lower() not in self.roles:
            return False
        return any(t in q for t in self.triggers)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "roles": self.roles,
            "path": self.path,
        }


class SkillRegistry:
    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self.skills_dir = skills_dir
        self._skills: list[Skill] = []

    def load(self) -> int:
        self._skills.clear()
        if not self.skills_dir.exists():
            log.info("skills directory missing — none loaded", path=str(self.skills_dir))
            return 0

        for path in sorted(self.skills_dir.glob("*.md")):
            try:
                skill = self._parse(path)
                if skill:
                    self._skills.append(skill)
            except Exception as e:
                log.warning("skill parse failed", path=str(path), error=str(e))

        log.info("skills loaded", count=len(self._skills),
                 names=[s.name for s in self._skills])
        return len(self._skills)

    @staticmethod
    def _parse(path: Path) -> Optional[Skill]:
        text = path.read_text(encoding="utf-8")
        # frontmatter delimited by leading and trailing ---
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
        if not m:
            return None
        fm_block, body = m.group(1), m.group(2).strip()

        fm = {}
        for line in fm_block.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                fm[key.strip()] = items
            else:
                fm[key.strip()] = val.strip("'\"")

        return Skill(
            name=fm.get("name", path.stem),
            description=fm.get("description", ""),
            triggers=fm.get("triggers", []) if isinstance(fm.get("triggers"), list) else [],
            roles=fm.get("roles", []) if isinstance(fm.get("roles"), list) else [],
            body=body,
            path=str(path),
        )

    @property
    def all(self) -> list[Skill]:
        return list(self._skills)

    def find_for(self, query: str, role: str | None = None) -> list[Skill]:
        return [s for s in self._skills if s.matches(query, role)]

    def get(self, name: str) -> Optional[Skill]:
        for s in self._skills:
            if s.name == name:
                return s
        return None


skills = SkillRegistry()
