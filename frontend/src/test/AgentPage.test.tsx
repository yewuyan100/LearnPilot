import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Link, useNavigate } from "react-router-dom";
import App from "../App";
import { renderApp } from "./render";

const now = "2026-08-01T08:00:00Z";
const conversation = { id: 1, title: "学习规划", status: "active", thread_id: "thread-1", context: { context_type: "general", context_id: null }, last_message_at: now, created_at: now, updated_at: now };

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

const goals = {
  1: { id: 1, title: "Goal A" },
  2: { id: 2, title: "Goal B" },
};
const materialOne = { id: 1, title: "Material One", original_filename: "material-one.md" };

function contextFixtureFetch() {
  return vi.fn((input: string | URL) => {
    const url = String(input);
    if (url.endsWith("/today")) return json({ current_goal: goals[2], recent_course: { id: 22 }, tasks: [{ course_id: 22, knowledge_point_id: 222 }] });
    if (url.endsWith("/learning-goals/1")) return json(goals[1]);
    if (url.endsWith("/learning-goals/2")) return json(goals[2]);
    if (url.includes("/learning-goals/999999") || url.includes("/materials/999999")) {
      return json({ error: { code: "not_found", message: "指定的协作对象不存在。" } }, 404);
    }
    if (url.endsWith("/materials/1")) return json(materialOne);
    if (url.endsWith("/courses")) return json([]);
    if (url.includes("/agent/conversations?")) return json([]);
    return json([]);
  });
}

function NavigationHarness() {
  const navigate = useNavigate();
  return <nav aria-label="测试上下文导航">
    <Link to="/ai">General AI</Link>
    <Link to="/ai?goal_id=1">Goal A AI</Link>
    <Link to="/ai?goal_id=2">Goal B AI</Link>
    <Link to="/ai?material_id=1">Material AI</Link>
    <button onClick={() => navigate(-1)}>Back</button>
    <button onClick={() => navigate(1)}>Forward</button>
  </nav>;
}

async function expectContext(path: string) {
  if (path === "/ai") {
    expect(await screen.findByText("尚未选择事项")).toBeInTheDocument();
    expect(screen.getByText("尚未限定资料")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal A" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal B" })).not.toBeInTheDocument();
  } else if (path.includes("goal_id=1")) {
    expect(await screen.findByRole("link", { name: "Goal A" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal B" })).not.toBeInTheDocument();
  } else if (path.includes("goal_id=2")) {
    expect(await screen.findByRole("link", { name: "Goal B" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal A" })).not.toBeInTheDocument();
  } else {
    expect(await screen.findByRole("link", { name: "Material One" })).toBeInTheDocument();
    expect(screen.getByText("尚未选择事项")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal A" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal B" })).not.toBeInTheDocument();
  }
}

describe("AI 协作", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      const body = url.endsWith("/agent/conversations/1")
        ? { ...conversation, messages: [{ id: 1, role: "assistant", content: "我可以查询学习记录，也会在创建内容前征得确认。", citations: [], run_id: 1, created_at: now }] }
        : [conversation];
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    }));
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });
  it("以学习上下文呈现会话，不显示运行限制", async () => {
    renderApp(<App />, "/agent");
    expect(await screen.findByRole("heading", { name: "从当前问题开始" })).toBeInTheDocument();
    expect(await screen.findByText("我可以查询学习记录，也会在创建内容前征得确认。")).toBeInTheDocument();
    expect(screen.getByLabelText("协作范围")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "通用协作" })).toBeInTheDocument();
    expect(screen.queryByText("回答边注")).not.toBeInTheDocument();
    expect(screen.queryByText("参考与处理")).not.toBeInTheDocument();
    expect(screen.queryByText(/内部角色/)).not.toBeInTheDocument();
    expect(screen.queryByText(/最多.*步/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "AI 协作" }).length).toBeGreaterThan(0);
  });

  it("显式事项上下文不回退到今日事项，并隐藏历史内部错误码", async () => {
    const scoped = { ...conversation, id: 7, context: { context_type: "goal", context_id: 7 } };
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/7")) return json({ id: 7, title: "可靠性收尾" });
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("/agent/conversations?context_type=goal&context_id=7")) return json([scoped]);
      if (url.endsWith("/agent/conversations/7")) return json({ ...scoped, messages: [{ id: 70, role: "assistant", content: "操作未完成（tool_arguments_invalid）。", citations: [], run_id: 1, created_at: now }] });
      return json([]);
    }));

    renderApp(<App />, "/ai?goal_id=7");
    expect(await screen.findByRole("link", { name: "可靠性收尾" })).toBeInTheDocument();
    expect(await screen.findByText("AI 协作暂时无法完成这项请求，请重试。")).toBeInTheDocument();
    expect(screen.queryByText(/tool_arguments_invalid/)).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/today"))).toBe(false);
  });

  it("从事项切到资料时切换会话范围，不继续展示旧会话", async () => {
    const goalConversation = { ...conversation, id: 71, context: { context_type: "goal", context_id: 7 } };
    const materialConversation = { ...conversation, id: 91, context: { context_type: "material", context_id: 9 } };
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/7")) return json({ id: 7, title: "可靠性收尾" });
      if (url.endsWith("/materials/9")) return json({ id: 9, title: "可靠性资料", original_filename: "reliability.md" });
      if (url.endsWith("/material-learning-links?material_ids=9")) return json([{ material_id: 9, target_type: "learning_goal", target_id: 7 }]);
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("context_type=goal&context_id=7")) return json([goalConversation]);
      if (url.includes("context_type=material&context_id=9")) return json([materialConversation]);
      if (url.endsWith("/agent/conversations/71")) return json({ ...goalConversation, messages: [{ id: 1, role: "assistant", content: "事项专属会话", citations: [], run_id: 1, created_at: now }] });
      if (url.endsWith("/agent/conversations/91")) return json({ ...materialConversation, messages: [{ id: 2, role: "assistant", content: "资料专属会话", citations: [], run_id: 2, created_at: now }] });
      return json([]);
    }));

    renderApp(<><Link to="/ai?material_id=9">切换资料上下文</Link><App /></>, "/ai?goal_id=7");
    expect(await screen.findByText("事项专属会话")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "切换资料上下文" }));
    expect(await screen.findByText("资料专属会话")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("事项专属会话")).not.toBeInTheDocument());
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("context_type=material&context_id=9"))).toBe(true);
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/today"))).toBe(false);
  });

  it("T1 Goal B 后从全局入口进入 /ai 时严格恢复 General", async () => {
    const fetchMock = contextFixtureFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<><NavigationHarness /><App /></>, "/ai?goal_id=2");

    await expectContext("/ai?goal_id=2");
    await userEvent.click(screen.getByRole("link", { name: "General AI" }));
    await expectContext("/ai");
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/today"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("context_type=general"))).toBe(true);
  });

  it("T2 Goal B 后在 /ai 新建会话仍提交 General metadata", async () => {
    const createBodies: unknown[] = [];
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/2")) return json(goals[2]);
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("/agent/conversations?") && init?.method !== "POST") return json([]);
      if (url.endsWith("/agent/conversations") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        createBodies.push(body);
        return json({ ...conversation, id: 202, context: body.context });
      }
      if (url.endsWith("/agent/conversations/202")) return json({ ...conversation, id: 202, context: { context_type: "general", context_id: null }, messages: [] });
      return json([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<><NavigationHarness /><App /></>, "/ai?goal_id=2");

    await expectContext("/ai?goal_id=2");
    await userEvent.click(screen.getByRole("link", { name: "General AI" }));
    await expectContext("/ai");
    await userEvent.click(screen.getByRole("button", { name: /新建协作会话/ }));
    await waitFor(() => expect(createBodies).toHaveLength(1));
    expect(createBodies[0]).toMatchObject({ context: { context_type: "general", context_id: null } });
  });

  it("T3 Goal A 后进入资料 AI 时只保留 Material 1", async () => {
    const fetchMock = contextFixtureFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<><NavigationHarness /><App /></>, "/ai?goal_id=1");

    await expectContext("/ai?goal_id=1");
    await userEvent.click(screen.getByRole("link", { name: "Material AI" }));
    await expectContext("/ai?material_id=1");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("material-learning-links"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("context_type=material&context_id=1"))).toBe(true);
  });

  it("T4 Goal A 切换到 Goal B 后不保留 Goal A", async () => {
    const fetchMock = contextFixtureFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<><NavigationHarness /><App /></>, "/ai?goal_id=1");

    await expectContext("/ai?goal_id=1");
    await userEvent.click(screen.getByRole("link", { name: "Goal B AI" }));
    await expectContext("/ai?goal_id=2");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("context_type=goal&context_id=2"))).toBe(true);
  });

  it.each(["/ai", "/ai?goal_id=1", "/ai?goal_id=2", "/ai?material_id=1"])("T5 refresh 后保持 canonical identity：%s", async (path) => {
    const fetchMock = contextFixtureFetch();
    vi.stubGlobal("fetch", fetchMock);
    const first = renderApp(<App />, path);
    await expectContext(path);
    first.unmount();

    renderApp(<App />, path);
    await expectContext(path);
    const expectedQuery = path === "/ai" ? "context_type=general"
      : path.includes("goal_id=1") ? "context_type=goal&context_id=1"
        : path.includes("goal_id=2") ? "context_type=goal&context_id=2"
          : "context_type=material&context_id=1";
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes(expectedQuery)).length).toBeGreaterThanOrEqual(2);
  });

  it("T6 Back / Forward 始终按当前 URL 恢复上下文", async () => {
    const fetchMock = contextFixtureFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<><NavigationHarness /><App /></>, "/ai?goal_id=1");

    await expectContext("/ai?goal_id=1");
    await userEvent.click(screen.getByRole("link", { name: "Goal B AI" }));
    await expectContext("/ai?goal_id=2");
    await userEvent.click(screen.getByRole("link", { name: "Material AI" }));
    await expectContext("/ai?material_id=1");
    await userEvent.click(screen.getByRole("link", { name: "General AI" }));
    await expectContext("/ai");

    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    await expectContext("/ai?material_id=1");
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    await expectContext("/ai?goal_id=2");
    await userEvent.click(screen.getByRole("button", { name: "Forward" }));
    await expectContext("/ai?material_id=1");
    await userEvent.click(screen.getByRole("button", { name: "Forward" }));
    await expectContext("/ai");
  });

  it.each([
    "/ai?goal_id=invalid",
    "/ai?material_id=invalid",
    "/ai?goal_id=999999",
    "/ai?material_id=999999",
    "/ai?goal_id=1&material_id=1",
  ])("T7 invalid / ambiguous context 安全失败且不绑定其它对象：%s", async (path) => {
    const fetchMock = contextFixtureFetch();
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<App />, path);

    expect(await screen.findByText(/协作上下文链接|当前协作上下文无法加载/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal A" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Goal B" })).not.toBeInTheDocument();
    expect(screen.queryByText(/not_found|HTTP 404|tool_arguments_invalid/)).not.toBeInTheDocument();
  });

  it.each([
    ["General", "/ai", { context_type: "general", context_id: null }],
    ["Goal", "/ai?goal_id=1", { context_type: "goal", context_id: 1 }],
    ["Material", "/ai?material_id=1", { context_type: "material", context_id: 1 }],
  ] as const)("T8 %s outbound metadata 与 stream input 无 stale context", async (_label, path, expectedContext) => {
    const createBodies: Array<{ context: unknown }> = [];
    const streamBodies: Array<{ input: string }> = [];
    const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/1")) return json(goals[1]);
      if (url.endsWith("/materials/1")) return json(materialOne);
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("/agent/conversations?") && init?.method !== "POST") return json([]);
      if (url.endsWith("/agent/conversations") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        createBodies.push(body);
        return json({ ...conversation, id: 208, context: body.context });
      }
      if (url.endsWith("/agent/conversations/208/runs/stream") && init?.method === "POST") {
        streamBodies.push(JSON.parse(String(init.body)));
        return Promise.resolve(new Response('event: run.completed\ndata: {"run_id":208}\n\n', { status: 200, headers: { "Content-Type": "text/event-stream" } }));
      }
      if (url.endsWith("/agent/conversations/208")) return json({ ...conversation, id: 208, context: expectedContext, messages: [] });
      return json([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(<App />, path);

    await screen.findByLabelText("给 AI 协作发送消息");
    const composer = await screen.findByLabelText("给 AI 协作发送消息");
    await waitFor(() => expect(composer).not.toBeDisabled());
    await userEvent.type(composer, "验证上下文");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(streamBodies).toHaveLength(1));
    expect(createBodies[0]).toMatchObject({ context: expectedContext });
    if (expectedContext.context_type === "general") {
      expect(streamBodies[0].input).toBe("验证上下文");
    } else if (expectedContext.context_type === "goal") {
      expect(streamBodies[0].input).toContain("learning_goal_id=1");
      expect(streamBodies[0].input).not.toContain("material_ids=");
    } else {
      expect(streamBodies[0].input).toContain("material_ids=[1]");
      expect(streamBodies[0].input).not.toMatch(/learning_goal_id=|course_id=|knowledge_point_id=/);
    }
  });

  it("Lesson 入口使用 lesson 会话范围并解析关联事项", async () => {
    const lessonConversation = { ...conversation, id: 31, context: { context_type: "lesson", context_id: 3 } };
    vi.stubGlobal("fetch", vi.fn((input: string | URL) => {
      const url = String(input);
      if (url.endsWith("/lessons/3")) return json({ id: 3, title: "结构化输出", learning_goal_id: 7, course_id: 2, active_version: { knowledge_points: [] } });
      if (url.endsWith("/learning-goals/7")) return json({ id: 7, title: "可靠性收尾" });
      if (url.endsWith("/courses")) return json([]);
      if (url.endsWith("/courses/2/knowledge-points")) return json([]);
      if (url.includes("context_type=lesson&context_id=3")) return json([lessonConversation]);
      if (url.endsWith("/agent/conversations/31")) return json({ ...lessonConversation, messages: [] });
      return json([]);
    }));

    renderApp(<App />, "/ai?lesson_id=3");
    expect((await screen.findAllByText("结构化输出")).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByRole("link", { name: "可靠性收尾" })).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("context_type=lesson&context_id=3"))).toBe(true);
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/today"))).toBe(false);
  });

  it("SSE 失败只展示 safe_message 并提供重试", async () => {
    const scoped = { ...conversation, id: 7, context: { context_type: "goal", context_id: 7 } };
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/7")) return json({ id: 7, title: "可靠性收尾" });
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("context_type=goal&context_id=7")) return json([scoped]);
      if (url.endsWith("/agent/conversations/7/runs/stream") && init?.method === "POST") {
        return Promise.resolve(new Response(
          'event: run.failed\ndata: {"code":"agent_plan_invalid","safe_message":"请换一种说法后重试。","retryable":true}\n\n',
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ));
      }
      if (url.endsWith("/agent/conversations/7")) return json({ ...scoped, messages: [{ id: 1, role: "assistant", content: "准备就绪", citations: [], run_id: null, created_at: now }] });
      return json([]);
    }));

    renderApp(<App />, "/ai?goal_id=7");
    await screen.findByText("准备就绪");
    const composer = await screen.findByLabelText("给 AI 协作发送消息");
    await userEvent.type(composer, "列出当前课程");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    const retry = await screen.findByRole("button", { name: "重试" });
    expect(retry.parentElement).toHaveTextContent("请换一种说法后重试。");
    expect(screen.queryByText(/agent_plan_invalid|tool_arguments_invalid/)).not.toBeInTheDocument();
  });

  it("SSE 完成后以持久化消息替换临时回答，不重复渲染", async () => {
    const scoped = { ...conversation, id: 7, context: { context_type: "goal", context_id: 7 } };
    let streamCompleted = false;
    vi.stubGlobal("fetch", vi.fn((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/learning-goals/7")) return json({ id: 7, title: "可靠性收尾" });
      if (url.endsWith("/courses")) return json([]);
      if (url.includes("context_type=goal&context_id=7")) return json([scoped]);
      if (url.endsWith("/agent/conversations/7/runs/stream") && init?.method === "POST") {
        streamCompleted = true;
        return Promise.resolve(new Response(
          'event: answer.completed\ndata: {"text":"最终回答"}\n\nevent: run.completed\ndata: {"run_id":1}\n\n',
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ));
      }
      if (url.endsWith("/agent/conversations/7")) return json({
        ...scoped,
        messages: streamCompleted
          ? [
              { id: 1, role: "assistant", content: "准备就绪", citations: [], run_id: null, created_at: now },
              { id: 2, role: "assistant", content: "最终回答", citations: [], run_id: 1, created_at: now },
            ]
          : [{ id: 1, role: "assistant", content: "准备就绪", citations: [], run_id: null, created_at: now }],
      });
      return json([]);
    }));

    renderApp(<App />, "/ai?goal_id=7");
    await screen.findByText("准备就绪");
    const composer = await screen.findByLabelText("给 AI 协作发送消息");
    await userEvent.type(composer, "梳理下一步");
    await userEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(screen.getAllByText("最终回答")).toHaveLength(1));
  });
});
