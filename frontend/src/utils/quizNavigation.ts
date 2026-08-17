export type QuizOrigin =
  | { kind: "goal"; goalId: number }
  | { kind: "lesson"; lessonId: number; goalId?: number; sessionId?: number }
  | { kind: "activity"; activityId: number; goalId?: number };

export type QuizNavigationContext = {
  kind: QuizOrigin["kind"] | "fallback";
  returnHref: string;
  returnLabel: string;
  goalId?: number;
};

function positiveInteger(value: string | null) {
  if (value === null || value.trim() === "") return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function quizOriginSearch(origin: QuizOrigin) {
  const params = new URLSearchParams({ origin: origin.kind });
  if (origin.kind === "goal") {
    params.set("goal_id", String(origin.goalId));
  }
  if (origin.kind === "lesson") {
    params.set("lesson_id", String(origin.lessonId));
    if (origin.goalId) params.set("goal_id", String(origin.goalId));
    if (origin.sessionId) params.set("session_id", String(origin.sessionId));
  }
  if (origin.kind === "activity") {
    params.set("activity_id", String(origin.activityId));
    if (origin.goalId) params.set("goal_id", String(origin.goalId));
  }
  return `?${params.toString()}`;
}

export function quizAttemptHref(attemptId: number, origin: QuizOrigin) {
  return `/quiz-attempts/${attemptId}${quizOriginSearch(origin)}`;
}

export function parseQuizNavigation(search: string): QuizNavigationContext {
  const params = new URLSearchParams(search);
  const origin = params.get("origin");
  const goalId = positiveInteger(params.get("goal_id"));

  if (origin === "goal" && goalId) {
    return { kind: "goal", goalId, returnHref: `/items/${goalId}`, returnLabel: "返回事项" };
  }

  const lessonId = positiveInteger(params.get("lesson_id"));
  if (origin === "lesson" && lessonId) {
    const sessionId = positiveInteger(params.get("session_id"));
    return {
      kind: "lesson",
      goalId,
      returnHref: `/lessons/${lessonId}${sessionId ? `?session=${sessionId}` : ""}`,
      returnLabel: "返回课节",
    };
  }

  const activityId = positiveInteger(params.get("activity_id"));
  if (origin === "activity" && activityId) {
    return {
      kind: "activity",
      goalId,
      returnHref: `/activities/${activityId}`,
      returnLabel: "返回活动",
    };
  }

  return { kind: "fallback", returnHref: "/workspace", returnLabel: "返回工作台" };
}
