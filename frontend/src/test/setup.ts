import "@testing-library/jest-dom/vitest";

// App keeps these routes lazy in production. Preload the modules before a
// worker starts its tests so UI assertions never include Vite transform time.
import "../pages/TodayPage";
import "../pages/DashboardPage";
import "../pages/PlanningPages";
import "../pages/CoursesPage";
import "../pages/CourseArchitectureDraftsPage";
import "../pages/CourseArchitectureDraftPage";
import "../pages/ActivitiesPage";
import "../pages/ReviewMasteryPage";
import "../pages/InboxPage";
import "../pages/KnowledgeHubPage";
import "../pages/ExplorePage";
import "../pages/MaterialDetailPage";
import "../pages/KnowledgePointDetailPage";
import "../pages/GoalDetailPage";
import "../pages/CurriculumReviewPage";
import "../pages/PlanAdjustmentReviewPage";
import "../pages/NotesPage";
import "../pages/AgentPage";
import "../pages/GrowthReviewPage";
import "../pages/SettingsPage";
import "../pages/MasteryDetailPage";
import "../pages/ActivityBuilderPage";
import "../pages/QuizAttemptPage";
import "../pages/QuizResultPage";
import "../pages/LearningSessionPage";
import "../pages/LessonPage";
import "../pages/NotFoundPage";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock;

HTMLDialogElement.prototype.showModal = function showModal() {
  this.open = true;
};
HTMLDialogElement.prototype.close = function close() {
  this.open = false;
};
