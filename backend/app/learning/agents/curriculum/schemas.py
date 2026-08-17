from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CurriculumModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CurriculumDiagnosticBaseline(CurriculumModel):
    knowledge_point: str
    ability_level: str
    score_percentage: float | None = None
    confidence: float = Field(ge=0, le=1)
    is_skill_gap: bool


class CurriculumExistingSkill(CurriculumModel):
    knowledge_point: str
    level: str
    score: float | None = None
    evidence_source: Literal["diagnostic", "mastery"]


class CurriculumMaterial(CurriculumModel):
    material_id: int
    title: str
    original_filename: str


class CurriculumMaterialChunk(CurriculumModel):
    chunk_id: int
    material_id: int
    locator: str
    content: str


class CurriculumMaterialScope(CurriculumModel):
    mode: Literal["goal_only", "source_grounded"]
    materials: list[CurriculumMaterial] = Field(default_factory=list)
    chunks: list[CurriculumMaterialChunk] = Field(default_factory=list)


class CurriculumAgentRequest(CurriculumModel):
    user_request: str
    goal_id: int
    goal_title: str
    goal_description: str
    current_level: str
    target_date: date | None
    daily_minutes: int = Field(ge=5, le=1440)
    diagnostic_baseline: list[CurriculumDiagnosticBaseline] = Field(default_factory=list)
    existing_skills: list[CurriculumExistingSkill] = Field(default_factory=list)
    material_scope: CurriculumMaterialScope


class CurriculumKnowledgePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    learning_objectives: list[str] = Field(min_length=1, max_length=10)
    key_terms: list[str] = Field(default_factory=list, max_length=15)
    difficulty_label: str = Field(min_length=1, max_length=40)
    source_chunk_ids: list[int] = Field(default_factory=list, max_length=6)


class CurriculumPrerequisite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prerequisite_title: str = Field(min_length=1, max_length=200)
    dependent_title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0.8, ge=0, le=1)


class CurriculumLessonBlueprint(BaseModel):
    """A planning handoff. It deliberately contains no teaching content."""

    model_config = ConfigDict(extra="forbid")

    knowledge_point: str = Field(min_length=1, max_length=200)
    lesson_goal: str = Field(min_length=1, max_length=1000)
    estimated_minutes: int = Field(ge=5, le=240)
    requires_lesson_generation: Literal[True] = True


class CurriculumCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_alignment: str = Field(min_length=1, max_length=2000)
    covered_topics: list[str] = Field(min_length=1, max_length=40)
    gaps: list[str] = Field(default_factory=list, max_length=20)
    material_grounding: Literal["goal_only_unverified", "source_grounded"]


class CurriculumProposalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_title: str = Field(min_length=1, max_length=200)
    course_description: str = Field(min_length=1, max_length=5000)
    knowledge_points: list[CurriculumKnowledgePoint] = Field(min_length=1, max_length=80)
    prerequisites: list[CurriculumPrerequisite] = Field(default_factory=list, max_length=100)
    learning_order: list[str] = Field(min_length=1, max_length=80)
    estimated_duration: int = Field(ge=5, le=100000)
    lesson_blueprints: list[CurriculumLessonBlueprint] = Field(min_length=1, max_length=80)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    coverage_report: CurriculumCoverageReport

    @model_validator(mode="after")
    def structural_contract(self) -> "CurriculumProposalDraft":
        titles = [item.title.strip().casefold() for item in self.knowledge_points]
        if len(titles) != len(set(titles)):
            raise ValueError("knowledge point titles must be unique")
        order = [item.strip().casefold() for item in self.learning_order]
        if len(order) != len(titles) or set(order) != set(titles):
            raise ValueError("learning_order must contain every knowledge point exactly once")
        blueprints = [item.knowledge_point.strip().casefold() for item in self.lesson_blueprints]
        if len(blueprints) != len(titles) or set(blueprints) != set(titles):
            raise ValueError("lesson_blueprints must contain every knowledge point exactly once")
        if sum(item.estimated_minutes for item in self.lesson_blueprints) != self.estimated_duration:
            raise ValueError("estimated_duration must equal the lesson blueprint total")
        return self


@dataclass(frozen=True)
class CurriculumAgentResult:
    proposal: CurriculumProposalDraft
    model_name: str
    prompt_version: str
