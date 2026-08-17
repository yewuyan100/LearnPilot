from app.models.course import Course
from app.models.activity_question import ActivityQuestion
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint, KnowledgePointLifecycleChange
from app.models.knowledge_point_source import KnowledgePointSource
from app.models.learning_goal import LearningGoal
from app.models.learning_session import LearningSession
from app.models.learning_activity import LearningActivity
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.models.material_learning_link import MaterialLearningLink
from app.models.rag_citation import RagCitation
from app.models.rag_conversation import RagConversation
from app.models.rag_message import RagMessage
from app.models.question_source import QuestionSource
from app.models.quiz_answer import QuizAnswer
from app.models.quiz_attempt import QuizAttempt
from app.models.wrong_answer import WrongAnswer
from app.models.agent import AgentConversation, AgentMessage, AgentRun, AgentToolCall, AgentConfirmation
from app.models.adaptive_recommendation import AdaptiveRecommendation
from app.models.knowledge_mastery import KnowledgeMastery
from app.models.mastery_evidence import MasteryEvidence
from app.models.mastery_snapshot import MasterySnapshot
from app.models.review_schedule import ReviewSchedule
from app.models.maintenance_task import MaintenanceTask
from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.note_source import NoteSource
from app.models.note_tag import NoteTag
from app.models.course_architecture import (
    CourseArchitectureDraft,
    CourseArchitectureDraftCourse,
    CourseArchitectureDraftKnowledgePoint,
    CourseArchitectureDraftMaterial,
    CourseArchitectureDraftPrerequisite,
    CourseArchitectureDraftSource,
    CourseArchitectureDraftVersion,
    KnowledgePointPrerequisite,
)
from app.models.diagnostic import (
    DiagnosticAdjustment,
    DiagnosticAnswerAssessment,
    DiagnosticItem,
    DiagnosticKnowledgeResult,
    DiagnosticSession,
)
from app.models.study_plan import StudyPlan, StudyPlanItem, StudyPlanVersion
from app.models.next_learning_action import NextActionAcceptance
from app.models.harness_run import HarnessRun
from app.models.learning_event import LearningEvent
from app.models.learning_proposal import LearningProposal
from app.models.lesson import (
    Lesson,
    LessonSource,
    LessonVersion,
    LessonVersionKnowledgePoint,
)

__all__ = [
    "Course",
    "ActivityQuestion",
    "DailyTask",
    "KnowledgePoint",
    "KnowledgePointLifecycleChange",
    "KnowledgePointSource",
    "LearningGoal",
    "LearningSession",
    "LearningActivity",
    "Material",
    "MaterialChunk",
    "MaterialLearningLink",
    "RagCitation",
    "RagConversation",
    "RagMessage",
    "QuestionSource",
    "QuizAnswer",
    "QuizAttempt",
    "WrongAnswer",
    "AgentConversation",
    "AgentMessage",
    "AgentRun",
    "AgentToolCall",
    "AgentConfirmation",
    "AdaptiveRecommendation",
    "KnowledgeMastery",
    "MasteryEvidence",
    "MasterySnapshot",
    "ReviewSchedule",
    "MaintenanceTask",
    "Note",
    "NoteLink",
    "NoteSource",
    "NoteTag",
    "CourseArchitectureDraft",
    "CourseArchitectureDraftCourse",
    "CourseArchitectureDraftKnowledgePoint",
    "CourseArchitectureDraftMaterial",
    "CourseArchitectureDraftPrerequisite",
    "CourseArchitectureDraftSource",
    "CourseArchitectureDraftVersion",
    "KnowledgePointPrerequisite",
    "DiagnosticAdjustment",
    "DiagnosticAnswerAssessment",
    "DiagnosticItem",
    "DiagnosticKnowledgeResult",
    "DiagnosticSession",
    "StudyPlan",
    "StudyPlanItem",
    "StudyPlanVersion",
    "NextActionAcceptance",
    "HarnessRun",
    "LearningEvent",
    "LearningProposal",
    "Lesson",
    "LessonVersion",
    "LessonVersionKnowledgePoint",
    "LessonSource",
]
