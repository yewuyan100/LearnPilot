from enum import StrEnum


class EvidenceType(StrEnum):
    objective_quiz = "objective_quiz"
    short_answer_quiz = "short_answer_quiz"
    wrong_answer = "wrong_answer"
    successful_review = "successful_review"
    task_completion = "task_completion"
    learning_session = "learning_session"
    self_assessment = "self_assessment"


class MasteryLevel(StrEnum):
    unassessed = "unassessed"
    beginner = "beginner"
    developing = "developing"
    proficient = "proficient"
    strong = "strong"


ACTIVE_SCHEDULE_STATUSES = ("pending", "scheduled")
ACTIVE_RECOMMENDATION_STATUSES = ("pending", "accepted")
