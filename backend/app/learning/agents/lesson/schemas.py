from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.rag.types import RagSource


class GenerationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LessonGenerationKnowledgePoint(GenerationModel):
    id: int
    title: str
    description: str
    role: Literal["primary", "supporting"]
    mastery_band: str


class LessonGenerationPrerequisite(GenerationModel):
    id: int
    title: str


class LessonGenerationMaterial(GenerationModel):
    material_id: int
    title: str
    original_filename: str
    source_type: str


class LessonGenerationMaterialScope(GenerationModel):
    requested_scope: dict
    material_ids: list[int] = Field(default_factory=list)
    materials: list[LessonGenerationMaterial] = Field(default_factory=list)
    scoped: bool
    empty: bool


class LessonGenerationRequest(GenerationModel):
    lesson_title: str
    lesson_description: str
    goal_title: str
    current_level: str
    course_title: str
    knowledge_points: list[LessonGenerationKnowledgePoint]
    prerequisites: list[LessonGenerationPrerequisite] = Field(default_factory=list)
    material_scope: LessonGenerationMaterialScope
    target_minutes: int = Field(ge=5, le=240)


class GeneratedLessonExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    explanation_markdown: str = Field(min_length=1, max_length=4000)


class GeneratedGuidedPractice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)
    hint: str = Field(min_length=1, max_length=1000)
    expected_approach: str = Field(min_length=1, max_length=2000)


class GeneratedUnderstandingCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)
    check_type: Literal["reflection", "single_choice", "short_answer"]
    options: list[str] = Field(default_factory=list, max_length=8)
    expected_concepts: list[str] = Field(default_factory=list, max_length=12)


class GeneratedLessonDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objectives: list[str] = Field(min_length=1, max_length=12)
    core_explanation_markdown: str = Field(min_length=1, max_length=16000)
    common_mistakes: list[str] = Field(min_length=1, max_length=12)
    examples: list[GeneratedLessonExample] = Field(min_length=1, max_length=10)
    guided_practice: list[GeneratedGuidedPractice] = Field(min_length=1, max_length=10)
    checks: list[GeneratedUnderstandingCheck] = Field(min_length=1, max_length=12)
    estimated_minutes: int = Field(ge=5, le=240)
    cited_source_ids: list[str] = Field(min_length=1, max_length=20)


@dataclass(frozen=True)
class LessonAgentResult:
    draft: GeneratedLessonDraft
    sources: list[RagSource]
    model_name: str
