from pydantic import BaseModel, ConfigDict, Field


class RagModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answerable: bool
    answer_markdown: str = Field(max_length=12000)
    cited_source_ids: list[str] = Field(max_length=20)
    refusal_reason: str | None = Field(default=None, max_length=200)


class QueryRewriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standalone_query: str = Field(min_length=1, max_length=2000)
