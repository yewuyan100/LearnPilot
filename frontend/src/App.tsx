import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { LoadingState } from "./components/States";

const load = <T,>(factory: () => Promise<T>, name: keyof T) =>
  lazy(() => factory().then((module) => ({ default: module[name] as unknown as ComponentType })));

const TodayPage = load(() => import("./pages/TodayPage"), "TodayPage");
const DashboardPage = load(() => import("./pages/DashboardPage"), "DashboardPage");
const GoalsPage = load(() => import("./pages/PlanningPages"), "GoalsPage");
const CoursesPage = load(() => import("./pages/CoursesPage"), "CoursesPage");
const CourseArchitectureDraftsPage = load(() => import("./pages/CourseArchitectureDraftsPage"), "CourseArchitectureDraftsPage");
const CourseArchitectureDraftPage = load(() => import("./pages/CourseArchitectureDraftPage"), "CourseArchitectureDraftPage");
const ActivitiesPage = load(() => import("./pages/ActivitiesPage"), "ActivitiesPage");
const ReviewMasteryPage = load(() => import("./pages/ReviewMasteryPage"), "ReviewMasteryPage");
const InboxPage = load(() => import("./pages/InboxPage"), "InboxPage");
const KnowledgeHubPage = load(() => import("./pages/KnowledgeHubPage"), "KnowledgeHubPage");
const ExplorePage = load(() => import("./pages/ExplorePage"), "ExplorePage");
const MaterialDetailPage = load(() => import("./pages/MaterialDetailPage"), "MaterialDetailPage");
const KnowledgePointDetailPage = load(() => import("./pages/KnowledgePointDetailPage"), "KnowledgePointDetailPage");
const GoalDetailPage = load(() => import("./pages/GoalDetailPage"), "GoalDetailPage");
const CurriculumReviewPage = load(() => import("./pages/CurriculumReviewPage"), "CurriculumReviewPage");
const PlanAdjustmentReviewPage = load(() => import("./pages/PlanAdjustmentReviewPage"), "PlanAdjustmentReviewPage");
const NotesPage = load(() => import("./pages/NotesPage"), "NotesPage");
const AgentPage = load(() => import("./pages/AgentPage"), "AgentPage");
const GrowthReviewPage = load(() => import("./pages/GrowthReviewPage"), "GrowthReviewPage");
const SettingsPage = load(() => import("./pages/SettingsPage"), "SettingsPage");
const MasteryDetailPage = load(() => import("./pages/MasteryDetailPage"), "MasteryDetailPage");
const ActivityBuilderPage = load(() => import("./pages/ActivityBuilderPage"), "ActivityBuilderPage");
const QuizAttemptPage = load(() => import("./pages/QuizAttemptPage"), "QuizAttemptPage");
const QuizResultPage = load(() => import("./pages/QuizResultPage"), "QuizResultPage");
const LearningSessionPage = load(() => import("./pages/LearningSessionPage"), "LearningSessionPage");
const LessonPage = load(() => import("./pages/LessonPage"), "LessonPage");
const NotFoundPage = load(() => import("./pages/NotFoundPage"), "NotFoundPage");

export default function App() {
  return (
    <Suspense fallback={<LoadingState label="正在加载页面…" />}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/workspace" replace />} />
          <Route path="/workspace" element={<DashboardPage />} />
          <Route path="/items" element={<GoalsPage />} />
          <Route path="/items/:id" element={<GoalDetailPage />} />
          <Route path="/knowledge" element={<KnowledgeHubPage />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/ai" element={<AgentPage />} />
          <Route path="/settings" element={<SettingsPage />} />

          {/* Existing capability routes remain available as deep or legacy entry points. */}
          <Route path="/today" element={<TodayPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/course-architecture/drafts" element={<CourseArchitectureDraftsPage />} />
          <Route path="/course-architecture/drafts/:id" element={<CourseArchitectureDraftPage />} />
          <Route path="/activities" element={<ActivitiesPage />} />
          <Route path="/activities/:id" element={<ActivityBuilderPage />} />
          <Route path="/review" element={<ReviewMasteryPage />} />
          <Route path="/mastery/:id" element={<MasteryDetailPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/materials/:id" element={<MaterialDetailPage />} />
          <Route path="/knowledge-points/:id" element={<KnowledgePointDetailPage />} />
          <Route path="/goals/:id" element={<GoalDetailPage />} />
          <Route path="/curriculum-proposals/:id" element={<CurriculumReviewPage />} />
          <Route path="/plan-adjustments/:id" element={<PlanAdjustmentReviewPage />} />
          <Route path="/notes" element={<NotesPage />} />
          <Route path="/growth" element={<GrowthReviewPage />} />

        <Route path="/goals" element={<Navigate to="/items?advanced=planning" replace />} />
          <Route path="/calendar" element={<Navigate to="/items" replace />} />
          <Route path="/reviews" element={<Navigate to="/review?tab=review" replace />} />
          <Route path="/mastery" element={<Navigate to="/review?tab=mastery" replace />} />
          <Route path="/wrong-answers" element={<Navigate to="/review?tab=wrong" replace />} />
          <Route path="/materials" element={<Navigate to="/knowledge?tab=materials&advanced=1" replace />} />
          <Route path="/rag" element={<Navigate to="/knowledge?tab=qa" replace />} />
          <Route path="/support" element={<Navigate to="/ai" replace />} />
          <Route path="/agent" element={<Navigate to="/ai" replace />} />
          <Route path="/reflection" element={<Navigate to="/growth?tab=today" replace />} />
          <Route path="/summary" element={<Navigate to="/growth?tab=summary" replace />} />
          <Route path="/progress" element={<Navigate to="/growth?tab=progress" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="/learning-sessions/:id" element={<LearningSessionPage />} />
        <Route path="/lessons/:id" element={<LessonPage />} />
        <Route path="/quiz-attempts/:id" element={<QuizAttemptPage />} />
        <Route path="/quiz-attempts/:id/result" element={<QuizResultPage />} />
      </Routes>
    </Suspense>
  );
}
