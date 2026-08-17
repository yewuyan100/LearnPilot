from app.learning.agents.planning.schemas import MasteryChangeInput


PLANNING_PROMPT_VERSION = "v11f.planning.deterministic.1"

PLANNING_SYSTEM_PROMPT = """Planning Agent 只解释掌握状态变化为什么值得调整未来路径，并提出等待用户确认的建议。它不计算日期、不创建 DailyTask、不发布 StudyPlan，也不输出内部思维过程。"""

MASTERY_LEVEL_LABELS = {
    "unassessed": "尚未评估",
    "beginner": "入门",
    "developing": "发展中",
    "proficient": "熟练",
    "strong": "稳固",
}


def adjustment_reason(change: MasteryChangeInput, evidence_count: int) -> str:
    level = MASTERY_LEVEL_LABELS.get(change.new_level, change.new_level)
    return (
        f"最近 {evidence_count} 条有效学习证据显示《{change.knowledge_point_title}》"
        f"当前掌握等级为“{level}”（置信度 {change.confidence:.0f}%），需要在后续计划中补一次复习。"
    )
