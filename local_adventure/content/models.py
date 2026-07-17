"""Pydantic models for authored world files only."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"


class AuthoredModel(BaseModel):
    """Base model which rejects misspelled authored fields."""

    model_config = ConfigDict(extra="forbid")


class ModelSettings(AuthoredModel):
    backend: Literal["lm_studio"]
    base_url: str
    name: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    api_token_env: str = ""

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must use http or https")
        return value.rstrip("/")


class ContextSettings(AuthoredModel):
    max_chars: int = Field(gt=0)
    system_chars: int = Field(gt=0)
    state_chars: int = Field(gt=0)
    recent_turns_chars: int = Field(gt=0)
    lore_chars: int = Field(gt=0)
    skills_chars: int = Field(gt=0)
    maximum_recent_turns: int = Field(gt=0)
    maximum_lore_documents: int = Field(gt=0)
    maximum_skills: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_section_total(self) -> "ContextSettings":
        sections = self.system_chars + self.state_chars + self.recent_turns_chars + self.lore_chars + self.skills_chars
        if sections > self.max_chars:
            raise ValueError("section budgets must not exceed max_chars")
        return self


class GameplaySettings(AuthoredModel):
    maximum_events_per_turn: int = Field(ge=0, le=50)
    maximum_repair_attempts: int = Field(ge=0, le=1)
    relationship_minimum: int
    relationship_maximum: int
    stat_delta_limit: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_relationship_range(self) -> "GameplaySettings":
        if self.relationship_minimum >= self.relationship_maximum:
            raise ValueError("relationship_minimum must be less than relationship_maximum")
        return self


class AuditSettings(AuthoredModel):
    store_prompts: bool
    store_prompt_hashes: bool
    store_raw_model_responses: bool
    log_level: str = Field(min_length=1)


class WorldConfig(AuthoredModel):
    schema_version: Literal[1]
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1)
    description: str = ""
    default_scenario: str = Field(pattern=ID_PATTERN)
    model: ModelSettings
    context: ContextSettings
    gameplay: GameplaySettings
    audit: AuditSettings


class EntityBase(AuthoredModel):
    schema_version: Literal[1]
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""


Scalar = str | int | float | bool


class Actor(EntityBase):
    location_id: str = Field(pattern=ID_PATTERN)
    is_player: bool
    stats: dict[str, Scalar] = Field(default_factory=dict)
    relationships: dict[str, dict[str, int]] = Field(default_factory=dict)


class Location(EntityBase):
    attributes: dict[str, Scalar] = Field(default_factory=dict)
    connections: list[str] = Field(default_factory=list)


class Item(EntityBase):
    initial_holder_type: Literal["actor", "location", "none"]
    initial_holder_id: str = ""
    attributes: dict[str, Scalar] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_holder(self) -> "Item":
        if self.initial_holder_type == "none" and self.initial_holder_id:
            raise ValueError("initial_holder_id must be empty when initial_holder_type is none")
        if self.initial_holder_type != "none" and not self.initial_holder_id:
            raise ValueError("initial_holder_id is required unless initial_holder_type is none")
        return self


class Quest(EntityBase):
    initial_status: str = Field(min_length=1)
    allowed_statuses: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_initial_status(self) -> "Quest":
        if self.initial_status not in self.allowed_statuses:
            raise ValueError("initial_status must appear in allowed_statuses")
        return self


class Scenario(AuthoredModel):
    schema_version: Literal[1]
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1)
    opening_narration: str = Field(min_length=1)
    player_actor_id: str = Field(pattern=ID_PATTERN)
    starting_location_id: str = Field(pattern=ID_PATTERN)
    active_actor_ids: list[str]
    active_quest_ids: list[str]
    initial_flags: dict[str, Scalar] = Field(default_factory=dict)


class LoreFrontMatter(AuthoredModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    priority: float = Field(default=0.5, ge=0.0)


class LoreDocument(AuthoredModel):
    metadata: LoreFrontMatter
    body: str
    relative_path: str


class SkillConfig(AuthoredModel):
    schema_version: Literal[1]
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    description: str = ""
    priority: float = 0.0
    always_include: bool = False
    trigger_terms: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    maximum_chars: int = Field(gt=0)


class PromptSkill(AuthoredModel):
    config: SkillConfig
    instructions: str
    relative_path: str


class LoadedWorld(AuthoredModel):
    """A fully parsed world, before any runtime state is constructed."""

    root: str
    config: WorldConfig
    world_markdown: str
    narrator_prompt: str
    repair_prompt: str
    rules: list[str]
    actors: dict[str, Actor]
    locations: dict[str, Location]
    items: dict[str, Item]
    quests: dict[str, Quest]
    scenarios: dict[str, Scenario]
    lore_documents: list[LoreDocument]
    skills: list[PromptSkill]
    warnings: list[str] = Field(default_factory=list)
