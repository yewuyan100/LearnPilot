import type { CurriculumProposal, Lesson, QuizAttempt } from "../types";
import { activitiesApi, coursesApi, lessonsApi } from "./resources";

export type FirstLessonResult = {
  lesson: Lesson;
  created: boolean;
};

function firstBlueprint(proposal: CurriculumProposal) {
  const firstTitle = proposal.curriculum.learning_order[0]
    ?? proposal.curriculum.knowledge_points[0]?.title;
  const blueprint = proposal.curriculum.lesson_blueprints.find(
    (item) => item.knowledge_point === firstTitle,
  ) ?? proposal.curriculum.lesson_blueprints[0];
  if (!firstTitle || !blueprint) {
    throw new Error("这条路线还没有可准备的第一步，请返回路线建议重新检查。");
  }
  return { firstTitle, blueprint };
}

async function resolveFirstLesson(
  proposal: CurriculumProposal,
  publishedCourseIds: number[] = [],
) {
  const { firstTitle, blueprint } = firstBlueprint(proposal);
  const courses = await coursesApi.list();
  const course = courses.find((item) => publishedCourseIds.includes(item.id))
    ?? courses.find((item) => (
      item.learning_goal_id === proposal.goal.id
      && item.title === proposal.curriculum.course_title
    ));
  if (!course) {
    throw new Error("路线已经确认，但暂时找不到第一步内容所属的路线。");
  }
  const points = await coursesApi.points(course.id);
  const point = points.find((item) => item.title === firstTitle) ?? points[0];
  if (!point) {
    throw new Error("路线已经确认，但第一步还没有正式建立。");
  }
  const lessons = await lessonsApi.list(course.id);
  const lesson = lessons.find((item) => (
    item.active_version?.knowledge_points.some((linked) => linked.knowledge_point_id === point.id)
    || item.latest_version?.knowledge_points.some((linked) => linked.knowledge_point_id === point.id)
  )) ?? lessons.find((item) => item.order_index === 1 || item.title === firstTitle);
  return { course, point, lesson, blueprint };
}

export async function findFirstLesson(
  proposal: CurriculumProposal,
  publishedCourseIds: number[] = [],
): Promise<Lesson | null> {
  const resolved = await resolveFirstLesson(proposal, publishedCourseIds);
  return resolved.lesson?.active_version ? resolved.lesson : null;
}

export async function prepareFirstLesson(
  proposal: CurriculumProposal,
  publishedCourseIds: number[] = [],
): Promise<FirstLessonResult> {
  const { course, point, lesson: existing, blueprint } = await resolveFirstLesson(
    proposal,
    publishedCourseIds,
  );
  let lesson = existing;
  let created = false;
  if (!lesson) {
    lesson = await lessonsApi.create(course.id, {
      title: point.title,
      description: blueprint.lesson_goal,
      order_index: 1,
    });
    created = true;
  }
  if (lesson.active_version) return { lesson, created };
  if (lesson.latest_version?.status !== "ready") {
    lesson = await lessonsApi.generate(lesson.id, {
      request_id: crypto.randomUUID(),
      knowledge_point_ids: [point.id],
      primary_knowledge_point_id: point.id,
      target_minutes: blueprint.estimated_minutes,
    });
  }
  if (!lesson.latest_version || lesson.latest_version.status !== "ready") {
    throw new Error("第一步内容还没有准备好，请稍后重新准备。");
  }
  lesson = await lessonsApi.publish(
    lesson.id,
    lesson.latest_version.version_number,
    lesson.current_version_number,
  );
  return { lesson, created };
}

export async function prepareLessonAssessment(
  lesson: Lesson,
  learningSessionId: number | null,
): Promise<QuizAttempt> {
  const version = lesson.active_version;
  const primaryPoint = version?.knowledge_points.find((item) => item.role === "primary")
    ?? version?.knowledge_points[0];
  if (!version || !primaryPoint) {
    throw new Error("当前内容还没有可用于检查理解的正式版本。");
  }
  const available = await activitiesApi.forContext(
    lesson.course_id,
    primaryPoint.knowledge_point_id,
  );
  let activity = available.items.find((item) => item.status === "published")
    ? await activitiesApi.get(available.items.find((item) => item.status === "published")!.id)
    : null;
  if (!activity) {
    const reusableDraft = available.items.find((item) => item.status === "draft");
    activity = reusableDraft
      ? await activitiesApi.get(reusableDraft.id)
      : await activitiesApi.generate({
        title: `${lesson.title} · 理解检查`,
        description: "完成当前内容后，用一次简短练习检查理解并获得反馈。",
        learning_goal_id: lesson.learning_goal_id,
        course_id: lesson.course_id,
        knowledge_point_id: primaryPoint.knowledge_point_id,
        material_ids: version.sources.length
          ? [...new Set(version.sources.map((source) => source.material_id))]
          : null,
        source_mode: version.sources.length ? "materials" : "without_materials",
        question_types: ["single_choice", "true_false", "short_answer"],
        question_count: 5,
        difficulty: "mixed",
        request_id: crypto.randomUUID(),
      });
    activity = await activitiesApi.publish(activity.id);
  }
  return activitiesApi.start(activity.id, learningSessionId);
}
