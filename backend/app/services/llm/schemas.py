from pydantic import BaseModel, ConfigDict, Field


class RagEvidenceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_markdown: str = Field(max_length=12000)
    source_ids: list[str] = Field(max_length=20)


class RagGroundedAnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answerable: bool
    blocks: list[RagEvidenceBlock] = Field(max_length=20)
    refusal_reason: str | None = Field(max_length=200)


class QueryRewriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standalone_query: str = Field(min_length=1, max_length=2000)
