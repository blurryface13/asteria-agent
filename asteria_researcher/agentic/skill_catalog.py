"""Trusted skill catalog. Instructions never grant tools or execute bundled scripts."""
import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).with_name("skills")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str
    kind: Literal["content", "guidance", "policy", "contract"]
    selectable: bool
    version: str
    phases: list[Literal["research", "writing", "formatting"]]
    description: str
    source: str
    files: list[str] = Field(min_length=1)


def catalog(phase=None):
    entries = [Manifest.model_validate(e).model_dump() for e in json.loads((ROOT / "catalog.json").read_text())]
    if len({e["id"] for e in entries}) != len(entries):
        raise ValueError("Duplicate skill IDs in catalog")
    return [e for e in entries if phase is None or phase in e["phases"]]


def skill_detail(skill_id):
    entry = next((e for e in catalog() if e["id"] == skill_id), None)
    if not entry:
        raise ValueError(f"Unknown skill: {skill_id}")
    texts = []
    for filename in entry["files"]:
        path = (ROOT / filename).resolve()
        if not path.is_relative_to(ROOT.resolve()) or path.suffix != ".md":
            raise ValueError("Skill resources must be trusted local Markdown")
        texts.append(path.read_text(encoding="utf-8"))
    content = "\n\n".join(texts)
    return {**entry, "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}


class SkillOptions(BaseModel):
    """Request-scoped additive pins; empty selection means autonomous discovery."""
    model_config = ConfigDict(extra="forbid", strict=True)
    skill_ids: list[str] = Field(default_factory=list, max_length=3)
    format_profile: str | None = None

    @model_validator(mode="after")
    def check(self):
        from .latex import format_profiles
        available = {e["id"]: e for e in catalog() if e["selectable"]}
        if len(set(self.skill_ids)) != len(self.skill_ids):
            raise ValueError("Duplicate requested skills")
        if not set(self.skill_ids) <= available.keys():
            raise ValueError("Unknown or non-selectable requested skill")
        if sum(available[i]["kind"] == "content" for i in self.skill_ids) > 1:
            raise ValueError("Choose at most one primary writing skill")
        if self.format_profile is not None and self.format_profile not in format_profiles():
            raise ValueError("Unknown format profile")
        return self


class SkillSession:
    def __init__(self, phase, options=None):
        self.phase, self.loaded = phase, {}
        # Freeze bodies and metadata together: discoveries cannot change mid-session.
        self.entries = {e["id"]: skill_detail(e["id"]) for e in catalog(phase)}
        self.options = options or SkillOptions()
        for skill_id in self.options.skill_ids:
            if skill_id in self.entries:
                self.load(skill_id, origin="user")

    def discover(self):
        return [{k: e[k] for k in ("id", "title", "kind", "description", "version")}
                for e in self.entries.values() if e["selectable"] or e["id"] in self.loaded]

    def load(self, skill_id, origin="agent"):
        if skill_id in self.loaded:
            return self.loaded[skill_id]
        if skill_id not in self.entries:
            raise ValueError(f"Skill {skill_id!r} unavailable in phase {self.phase}")
        result = {**self.entries[skill_id], "phase": self.phase, "origin": origin}
        self.loaded[skill_id] = result
        return result

    def prompt(self):
        return "\n\n".join(f"<skill id='{s['id']}' version='{s['version']}'>\n{s['content']}\n</skill>" for s in self.loaded.values())

    def trace(self):
        return [{k: s[k] for k in ("id", "title", "version", "sha256", "phase", "origin")} for s in self.loaded.values()]


class WritingSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_ids: list[str] = Field(min_length=1, max_length=3)
    format_profile: str
    reason: str = Field(min_length=1, max_length=600)


async def select_writing(model, task, context, options=None):
    """Model selects guidance; validation enforces pins and exclusive content roles."""
    from .latex import format_profiles
    options = options or SkillOptions()
    session = SkillSession("writing", options)
    profiles = format_profiles()
    schema = WritingSelection.model_json_schema()
    schema["properties"]["skill_ids"]["items"]["enum"] = list(session.entries)
    schema["properties"]["format_profile"]["enum"] = list(profiles)
    payload = dict(task=task, context=context, available_skills=session.discover(), format_profiles=profiles,
                   user_selection=options.model_dump())
    for attempt in range(2):
        raw = await model(
            "Select exactly ONE content skill and optional relevant guidance skills from the catalog. "
            "All user-pinned writing skills MUST be included; do not replace them. If user specified a format, "
            "use it exactly. Otherwise choose independently by deliverable needs. Do not select by keywords alone. "
            "Skills change writing guidance, never tool permissions, research scope or evidence rules. "
            "Return ONLY JSON: " + json.dumps(schema), json.dumps(payload, ensure_ascii=False))
        try:
            selection = WritingSelection.model_validate_json(raw)
            checked = SkillOptions(skill_ids=selection.skill_ids, format_profile=selection.format_profile)
            if not set(checked.skill_ids) <= session.entries.keys():
                raise ValueError("Unavailable writing skill")
            if sum(session.entries[i]["kind"] == "content" for i in checked.skill_ids) != 1:
                raise ValueError("Select exactly one content-writing skill")
            if not set(session.loaded) <= set(checked.skill_ids):
                raise ValueError("User-pinned skills cannot be omitted")
            if options.format_profile and selection.format_profile != options.format_profile:
                raise ValueError("Use the user-selected format profile")
            for skill_id in selection.skill_ids:
                session.load(skill_id)
            contract = SkillSession("formatting")
            contract.load("report_formatting", origin="system")
            return selection, session.prompt() + "\n\n" + contract.prompt(), session.trace() + contract.trace()
        except ValueError as error:
            if attempt:
                raise
            payload["selection_error"] = str(error)
