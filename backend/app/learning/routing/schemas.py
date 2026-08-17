from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.learning.context.schemas import LearnerContext, SurfaceContext


UserIntent = Literal["learning_question", "curriculum", "operation"]


class RoutingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input: str
    user_intent: UserIntent
    context: LearnerContext
    surface_context: SurfaceContext


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_agent: Literal["tutor", "curriculum", "operations"]
    adapter_key: Literal["tutor_agent", "curriculum_agent", "operations_agent"]
    reason_code: str
