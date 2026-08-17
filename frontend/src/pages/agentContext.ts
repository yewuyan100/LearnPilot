import type { AgentConversationContext } from "../types";

export interface AgentRouteContext {
  context: AgentConversationContext;
  goalId: number | null;
  materialId: number | null;
  lessonId: number | null;
  error: string;
}

function positiveParam(value: string | null) {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : NaN;
}

export function resolveAgentRouteContext(params: URLSearchParams): AgentRouteContext {
  const goalId = positiveParam(params.get("goal_id"));
  const materialId = positiveParam(params.get("material_id"));
  const lessonId = positiveParam(params.get("lesson_id"));
  const explicitIds = [goalId, materialId, lessonId].filter((id) => id !== null);

  if (explicitIds.some((id) => Number.isNaN(id))) {
    return {
      context: { context_type: "general", context_id: null },
      goalId,
      materialId,
      lessonId,
      error: "协作上下文链接无效，请从原页面重新进入 AI 协作。",
    };
  }

  if (explicitIds.length > 1) {
    return {
      context: { context_type: "general", context_id: null },
      goalId,
      materialId,
      lessonId,
      error: "协作上下文链接包含多个对象，请从一个明确入口重新进入。",
    };
  }

  if (goalId !== null) return { context: { context_type: "goal", context_id: goalId }, goalId, materialId, lessonId, error: "" };
  if (materialId !== null) return { context: { context_type: "material", context_id: materialId }, goalId, materialId, lessonId, error: "" };
  if (lessonId !== null) return { context: { context_type: "lesson", context_id: lessonId }, goalId, materialId, lessonId, error: "" };
  return { context: { context_type: "general", context_id: null }, goalId, materialId, lessonId, error: "" };
}
