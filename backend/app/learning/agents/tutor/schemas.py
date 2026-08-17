from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.learning.context.schemas import LearnerContext, MaterialScopeContext


class TutorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TutorRequest(TutorModel):
    question: str = Field(min_length=1, max_length=4000)
    learner_context: LearnerContext
    material_scope: MaterialScopeContext
    conversation_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def scope_must_match_context(self):
        if self.material_scope != self.learner_context.material_scope:
            raise ValueError("material_scope must be the effective scope in learner_context")
        return self


class TutorCitation(TutorModel):
    source_label: str
    material_id: int
    chunk_id: int
    original_filename: str
    page_number: int | None = None
    section_title: str | None = None
    content_excerpt: str
    score: float


class TutorContextReference(TutorModel):
    kind: Literal[
        "learning_goal",
        "course",
        "knowledge_point",
        "lesson",
        "lesson_version",
        "learning_session",
        "daily_task",
        "material",
    ]
    id: int
    title: str


class TutorAnswer(TutorModel):
    answer_markdown: str = Field(min_length=1, max_length=14000)
    teaching_mode: str = Field(min_length=1, max_length=64)
    citations: list[TutorCitation] = Field(default_factory=list, max_length=20)
    context_references: list[TutorContextReference] = Field(default_factory=list, max_length=30)
    follow_up_check: str | None = Field(default=None, max_length=1000)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class TutorModelAnswer(BaseModel):
    """Structured output requested from the LLM; validated at the Module boundary."""

    model_config = ConfigDict(extra="forbid")

    answer_markdown: str = Field(min_length=1, max_length=12000)
    teaching_mode: Literal["explanation", "worked_example", "guided_question", "remediation"]
    cited_source_ids: list[str] = Field(default_factory=list, max_length=20)
    follow_up_check: str | None = Field(default=None, max_length=1000)
    limitations: list[str] = Field(default_factory=list, max_length=20)
