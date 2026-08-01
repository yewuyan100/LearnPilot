"""Stable import aliases used by documentation and tests."""

from app.services.adaptive_learning.evidence_collector import LearningEvidenceCollector
from app.services.adaptive_learning.mastery import KnowledgeMasteryService
from app.services.adaptive_learning.recommendations import AdaptiveRecommendationService
from app.services.adaptive_learning.scheduler import ReviewScheduler
from app.services.adaptive_learning.weak_points import WeakPointService

__all__ = [
    "LearningEvidenceCollector", "KnowledgeMasteryService", "WeakPointService",
    "ReviewScheduler", "AdaptiveRecommendationService",
]
