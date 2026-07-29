import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { LoadingState } from "./components/States";

const TodayPage = lazy(() =>
  import("./pages/TodayPage").then((module) => ({ default: module.TodayPage })),
);
const CoursesPage = lazy(() =>
  import("./pages/CoursesPage").then((module) => ({ default: module.CoursesPage })),
);
const MaterialsPage = lazy(() =>
  import("./pages/MaterialsPage").then((module) => ({ default: module.MaterialsPage })),
);
const ReviewsPage = lazy(() =>
  import("./pages/ReviewsPage").then((module) => ({ default: module.ReviewsPage })),
);
const ProgressPage = lazy(() =>
  import("./pages/ProgressPage").then((module) => ({ default: module.ProgressPage })),
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })),
);
const LearningSessionPage = lazy(() =>
  import("./pages/LearningSessionPage").then((module) => ({
    default: module.LearningSessionPage,
  })),
);
const NotFoundPage = lazy(() =>
  import("./pages/NotFoundPage").then((module) => ({ default: module.NotFoundPage })),
);

export default function App() {
  return (
    <Suspense fallback={<LoadingState label="正在加载页面…" />}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/today" replace />} />
          <Route path="/today" element={<TodayPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/materials" element={<MaterialsPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="/learning-sessions/:id" element={<LearningSessionPage />} />
      </Routes>
    </Suspense>
  );
}
