"""Safe loading of TOML and Markdown authored-world files."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError

from ..errors import ContentParseError, WorldValidationError
from .frontmatter import read_lore_document
from .models import Actor, Item, LoadedWorld, Location, PromptSkill, Quest, Scenario, SkillConfig, WorldConfig
from .validator import validate_world

ModelType = TypeVar("ModelType", bound=BaseModel)


def load_world(world_path: str | Path) -> LoadedWorld:
    """Load, validate, and return a world without following escaping symlinks."""
    root = Path(world_path).expanduser().resolve()
    if not root.is_dir():
        raise WorldValidationError(f"{world_path}: world directory does not exist or is not a directory")
    config_path = root / "world.toml"
    _ensure_inside(root, config_path)
    config = _load_toml(config_path, WorldConfig)
    actors = _load_entities(root, "actors", Actor)
    locations = _load_entities(root, "locations", Location)
    items = _load_entities(root, "items", Item)
    quests = _load_entities(root, "quests", Quest)
    scenarios = _load_scenarios(root)
    lore_documents = _load_lore(root)
    skills = _load_skills(root)
    loaded = LoadedWorld(
        root=str(root), config=config,
        world_markdown=_read_required_text(root, "WORLD.md"),
        narrator_prompt=_read_required_text(root, "prompts/narrator.md"),
        repair_prompt=_read_required_text(root, "prompts/repair.md"),
        rules=[_read_text(path) for path in _safe_rglob(root, "rules", "*.md")],
        actors=actors, locations=locations, items=items, quests=quests, scenarios=scenarios,
        lore_documents=lore_documents, skills=skills, warnings=_endpoint_warnings(config),
    )
    validate_world(loaded)
    return loaded


def _load_toml(path: Path, model_type: type[ModelType]) -> ModelType:
    data = _read_toml(path)
    try:
        return model_type.model_validate(data)
    except ValidationError as error:
        raise ContentParseError(f"{path}: {error}") from error


def _read_toml(path: Path) -> dict[str, object]:
    text = _read_text(path)
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ContentParseError(f"{path}: TOML: {error}") from error


def _load_entities(root: Path, kind: str, model_type: type[ModelType]) -> dict[str, ModelType]:
    return _load_model_directory(root, f"entities/{kind}", model_type)


def _load_scenarios(root: Path) -> dict[str, Scenario]:
    return _load_model_directory(root, "scenarios", Scenario)


def _load_model_directory(root: Path, directory: str, model_type: type[ModelType]) -> dict[str, ModelType]:
    models: dict[str, ModelType] = {}
    for path in _safe_rglob(root, directory, "*.toml"):
        model = _load_toml(path, model_type)
        if model.id in models:
            raise WorldValidationError(f"{path}: id '{model.id}' duplicates another {directory} file")
        models[model.id] = model
    return models


def _load_lore(root: Path) -> list:
    documents = []
    for path in _safe_rglob(root, "lore", "*.md"):
        documents.append(read_lore_document(path, path.relative_to(root).as_posix()))
    return documents


def _load_skills(root: Path) -> list[PromptSkill]:
    skills: list[PromptSkill] = []
    for skill_path in _safe_rglob(root, "skills", "skill.toml"):
        config = _load_toml(skill_path, SkillConfig)
        instructions_path = skill_path.parent / "SKILL.md"
        _ensure_inside(root, instructions_path)
        instructions = _read_text(instructions_path)
        if not instructions.strip():
            raise ContentParseError(f"{instructions_path}: skill instructions must not be empty")
        skills.append(PromptSkill(config=config, instructions=instructions, relative_path=skill_path.parent.relative_to(root).as_posix()))
    return skills


def _safe_rglob(root: Path, relative_directory: str, pattern: str) -> list[Path]:
    directory = root / relative_directory
    if not directory.exists():
        return []
    _ensure_inside(root, directory)
    paths = []
    for path in directory.rglob(pattern):
        _ensure_inside(root, path)
        if path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix())


def _read_required_text(root: Path, relative_path: str) -> str:
    path = root / relative_path
    _ensure_inside(root, path)
    if not path.is_file():
        raise ContentParseError(f"{path}: required file is missing")
    return _read_text(path)


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ContentParseError(f"{path}: unable to read file: {error}") from error
    if b"\0" in raw:
        raise ContentParseError(f"{path}: NUL bytes are not allowed")
    try:
        return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as error:
        raise ContentParseError(f"{path}: file must be UTF-8") from error


def _ensure_inside(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root)
    except ValueError as error:
        raise WorldValidationError(f"{path}: path escapes selected world root") from error


def _endpoint_warnings(config: WorldConfig) -> list[str]:
    hostname = urlparse(config.model.base_url).hostname
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        return ["model.base_url is not loopback; game prompts and content will be sent to that endpoint. Enable API authentication."]
    return []
