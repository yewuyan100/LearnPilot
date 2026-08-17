from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MaterialTargetType = Literal["learning_goal", "course", "knowledge_point"]
MaterialRelationType = Literal[
    "reference",
    "primary_source",
    "supplementary",
    "prerequisite",
    "practice_source",
]
MaterialVisibility = Literal["direct", "inherited", "descendant"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterialLearningLinkCreate(StrictModel):
    target_type: MaterialTargetType
    learning_goal_id: int | None = Field(default=None, gt=0)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    relation_type: MaterialRelationType = "reference"
    is_primary: bool = False

    @model_validator(mode="after")
    def validate_target(self) -> "MaterialLearningLinkCreate":
        targets = {
            "learning_goal": self.learning_goal_id,
            "course": self.course_id,
            "knowledge_point": self.knowledge_point_id,
        }
        if sum(value is not None for value in targets.values()) != 1:
            raise ValueError("exactly one learning target must be provided")
        if targets[self.target_type] is None:
            raise ValueError("target_type must match the provided target id")
        return self

    @property
    def target_id(self) -> int:
        value = {
            "learning_goal": self.learning_goal_id,
            "course": self.course_id,
            "knowledge_point": self.knowledge_point_id,
        }[self.target_type]
        assert value is not None
        return value


class MaterialLearningLinkBulkCreate(StrictModel):
    links: list[MaterialLearningLinkCreate] = Field(min_length=1, max_length=100)


class MaterialLearningBatchMaterialsCreate(StrictModel):
    material_ids: list[int] = Field(min_length=1, max_length=100)
    link: MaterialLearningLinkCreate

    @model_validator(mode="after")
    def unique_materials(self) -> "MaterialLearningBatchMaterialsCreate":
        if len(self.material_ids) != len(set(self.material_ids)):
            raise ValueError("material_ids cannot contain duplicates")
        if any(material_id <= 0 for material_id in self.material_ids):
            raise ValueError("material_ids must be positive")
        return self


class MaterialLearningLinkUpdate(StrictModel):
    relation_type: MaterialRelationType | None = None
    is_primary: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "MaterialLearningLinkUpdate":
        if self.relation_type is None and self.is_primary is None:
            raise ValueError("at least one field must be provided")
        return self


class MaterialLearningLinkRead(BaseModel):
    id: int
    material_id: int
    target_type: MaterialTargetType
    target_id: int
    target_title: str
    relation_type: MaterialRelationType
    is_primary: bool
    created_at: datetime
    updated_at: datetime


class MaterialLearningContextRead(MaterialLearningLinkRead):
    material_title: str
    original_filename: str
    source_type: str
    processing_status: str
    ingestion_status: str
    indexing_status: str
    deletion_status: str
    visibility: MaterialVisibility


class EffectiveMaterialRead(BaseModel):
    material_id: int
    material_title: str
    original_filename: str
    source_type: str
    processing_status: str
    ingestion_status: str
    indexing_status: str
    deletion_status: str
    contexts: list[MaterialLearningContextRead]


class MaterialLearningBatchItemRead(BaseModel):
    material_id: int
    success: bool
    link: MaterialLearningLinkRead | None = None
    error_code: str | None = None
    error_message: str | None = None


class MaterialLearningBatchResultRead(BaseModel):
    requested: int
    succeeded: int
    failed: int
    items: list[MaterialLearningBatchItemRead]
