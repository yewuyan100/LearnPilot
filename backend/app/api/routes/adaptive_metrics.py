from statistics import mean

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.models import (
    AgentRun, KnowledgeMastery, MasteryEvidence, QuizAttempt,
    RagConversation, RagMessage,
)

router = APIRouter(prefix="/adaptive-metrics", tags=["adaptive metrics"])


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    rows = sorted(values)
    index = min(len(rows) - 1, max(0, round((len(rows) - 1) * fraction)))
    return round(rows[index], 2)


@router.get("")
def adaptive_metrics(db: DbSession) -> dict:
    runs = db.scalars(select(AgentRun).where(AgentRun.status.in_(("completed", "failed")))).all()
    performance = [(row.prompt_versions or {}).get("performance") or {} for row in runs]
    latencies = []
    for row in runs:
        if row.started_at and row.completed_at:
            latencies.append(max(0.0, (row.completed_at - row.started_at).total_seconds() * 1000))
    return {
        "rag": {
            "conversation_count": db.scalar(select(func.count()).select_from(RagConversation)) or 0,
            "message_count": db.scalar(select(func.count()).select_from(RagMessage)) or 0,
        },
        "quiz": {
            "completed_attempt_count": db.scalar(select(func.count()).select_from(QuizAttempt).where(QuizAttempt.status == "completed")) or 0,
        },
        "mastery": {
            "assessed_count": db.scalar(select(func.count()).select_from(KnowledgeMastery).where(KnowledgeMastery.mastery_score.is_not(None))) or 0,
            "unassessed_count": db.scalar(select(func.count()).select_from(KnowledgeMastery).where(KnowledgeMastery.mastery_score.is_(None))) or 0,
            "evidence_count": db.scalar(select(func.count()).select_from(MasteryEvidence)) or 0,
            "algorithm_version": "mastery-rule-v1",
        },
        "agent": {
            "run_count": len(runs),
            "fast_route_usage_rate": round(sum(bool(item.get("fast_route_used")) for item in performance) / len(performance), 4) if performance else 0,
            "average_llm_calls_per_run": round(mean(float(item.get("llm_call_count", 0)) for item in performance), 2) if performance else 0,
            "average_total_latency_ms": round(mean(latencies), 2) if latencies else 0,
            "p50_total_latency_ms": percentile(latencies, .50),
            "p95_total_latency_ms": percentile(latencies, .95),
        },
        "scope_note": "这些是本项目固定规则与运行记录指标，不代表通用教育效果。",
    }
