import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { activitiesApi, materialsApi, materialLearningApi, notesApi } from "../api/resources";
import { MaterialDetailPage } from "../pages/MaterialDetailPage";
import { renderApp } from "./render";

const now = "2026-08-11T08:00:00Z";

const readyMaterial = {
  id: 1,
  title: "AI Agents 深度指南",
  original_filename: "AI-Agents-in-Depth-zh-CN.pdf",
  stored_filename: "material-1.pdf",
  file_path: "data/material-1.pdf",
  source_type: "upload",
  mime_type: "application/pdf",
  file_size: 1024,
  processing_status: "completed",
  ingestion_status: "completed",
  indexing_status: "completed",
  chunk_count: 884,
  indexed_chunk_count: 884,
  processed_at: now,
  indexed_at: now,
  archived_at: null,
  error_message: null,
  deletion_status: "active",
  deletion_error: null,
  deletion_requested_at: null,
  deletion_attempts: 0,
  created_at: now,
  updated_at: now,
};

function chunk(chunkIndex: number, content: string, overrides: Record<string, unknown> = {}) {
  return {
    id: chunkIndex + 10,
    material_id: 1,
    chunk_index: chunkIndex,
    content,
    char_count: content.length,
    content_hash: `hash-${chunkIndex}`,
    page_number: null,
    section_title: null,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function chunkPage(page = 1, pages = 89, items = [
  chunk(1, "第二段内容"),
  chunk(0, "第一段内容", { page_number: 3, section_title: "开篇" }),
  chunk(2, "第三段内容"),
]) {
  return { items, total: 884, page, page_size: 10, pages };
}

function mockMaterialDetail() {
  vi.spyOn(materialsApi, "get").mockResolvedValue(readyMaterial as never);
  vi.spyOn(materialsApi, "chunks").mockResolvedValue(chunkPage() as never);
  vi.spyOn(materialLearningApi, "list").mockResolvedValue([{
    id: 21,
    material_id: 1,
    target_type: "learning_goal",
    target_id: 2,
    target_title: "学习 AI Agent",
    relation_type: "reference",
    is_primary: false,
    created_at: now,
    updated_at: now,
  }] as never);
  vi.spyOn(notesApi, "list").mockResolvedValue({
    items: [{ id: 31, title: "Agent 阅读笔记", updated_at: now }],
    total: 1,
    page: 1,
    page_size: 100,
    pages: 1,
  } as never);
  vi.spyOn(activitiesApi, "list").mockResolvedValue({
    items: [{
      id: 41,
      title: "Agent 理解检查",
      question_count: 5,
      source_scope: { material_ids: [1] },
    }],
    total: 1,
    page: 1,
    page_size: 100,
    pages: 1,
  } as never);
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function HistoryControls() {
  const navigate = useNavigate();
  return <div>
    <button type="button" onClick={() => navigate(-1)}>测试后退</button>
    <button type="button" onClick={() => navigate(1)}>测试前进</button>
  </div>;
}

function MaterialRoutes({ historyControls = false }: { historyControls?: boolean }) {
  return <>
    {historyControls && <HistoryControls />}
    <Routes><Route path="/materials/:id" element={<MaterialDetailPage />} /></Routes>
    <LocationProbe />
  </>;
}

function expectActiveView(label: string) {
  expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-current", "page");
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  mockMaterialDetail();
});

describe("Final UX Batch 3C · Material Detail URL contract", () => {
  it.each([
    ["/materials/1", "内容", "资料内容"],
    ["/materials/1?view=content", "内容", "资料内容"],
    ["/materials/1?view=learning", "学习与关联", "关联事项"],
    ["/materials/1?view=foo", "内容", "资料内容"],
  ])("%s 直接打开正确视图", async (path, activeLabel, heading) => {
    renderApp(<MaterialRoutes />, path);
    expect(await screen.findByRole("heading", { level: 1, name: readyMaterial.title })).toBeInTheDocument();
    expectActiveView(activeLabel);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("切换视图保留 chunk 等未知 query params", async () => {
    renderApp(<MaterialRoutes />, "/materials/1?chunk=77&source=citation");
    expect(await screen.findByText("第一段内容")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "学习与关联" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/materials/1?chunk=77&source=citation&view=learning");
    expectActiveView("学习与关联");
  });

  it("Browser Back / Forward 恢复对应视图", async () => {
    renderApp(<MaterialRoutes historyControls />, "/materials/1");
    expect(await screen.findByText("第一段内容")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "学习与关联" }));
    expectActiveView("学习与关联");

    await userEvent.click(screen.getByRole("button", { name: "测试后退" }));
    await waitFor(() => expectActiveView("内容"));
    expect(screen.getByRole("heading", { name: "资料内容" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "测试前进" }));
    await waitFor(() => expectActiveView("学习与关联"));
    expect(screen.getByRole("heading", { name: "关联事项" })).toBeInTheDocument();
  });

  it("refresh-equivalent remount 保留 learning", async () => {
    const first = renderApp(<MaterialRoutes />, "/materials/1?view=learning");
    expect(await screen.findByRole("heading", { name: "关联事项" })).toBeInTheDocument();
    first.unmount();

    renderApp(<MaterialRoutes />, "/materials/1?view=learning");
    expect(await screen.findByRole("heading", { name: "关联事项" })).toBeInTheDocument();
    expectActiveView("学习与关联");
  });
});

describe("Final UX Batch 3C · content surface and pagination", () => {
  it("使用现有分页 chunks API，并按 chunk_index 顺序显示真实内容和可用来源信息", async () => {
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByText("第一段内容")).toBeInTheDocument();
    expect(materialsApi.chunks).toHaveBeenCalledWith(1, 1, 10);

    const rendered = [...document.querySelectorAll<HTMLElement>(".material-content-chunk")];
    expect(rendered.map((item) => item.dataset.chunkIndex)).toEqual(["0", "1", "2"]);
    expect(screen.getByText("第 3 页")).toBeInTheDocument();
    expect(screen.getByText("开篇")).toBeInTheDocument();
    expect(screen.queryByText("无页码")).not.toBeInTheDocument();
    expect(screen.queryByText(/embedding|score|content_hash|chunk_index/i)).not.toBeInTheDocument();
    expect(rendered).toHaveLength(3);
    expect(screen.getAllByText(/共 884 个内容片段/).length).toBeGreaterThan(0);
  });

  it("上一页 / 下一页使用服务端分页，并正确限制边界", async () => {
    vi.mocked(materialsApi.chunks).mockImplementation(async (_id, page) => page === 2
      ? chunkPage(2, 2, [chunk(10, "第二页内容")]) as never
      : chunkPage(1, 2, [chunk(0, "第一页内容")]) as never);
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByText("第一页内容")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "上一页资料内容" })[0]).toBeDisabled();

    await userEvent.click(screen.getAllByRole("button", { name: "下一页资料内容" })[0]);
    expect(await screen.findByText("第二页内容")).toBeInTheDocument();
    expect(materialsApi.chunks).toHaveBeenCalledWith(1, 2, 10);
    expect(screen.getAllByRole("button", { name: "下一页资料内容" })[0]).toBeDisabled();

    await userEvent.click(screen.getAllByRole("button", { name: "上一页资料内容" })[0]);
    expect(await screen.findByText("第一页内容")).toBeInTheDocument();
  });

  it("content 与 learning 主体互相隔离", async () => {
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByRole("heading", { name: "资料内容" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "关联事项" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "练习与反馈" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "学习与关联" }));
    expect(await screen.findByRole("heading", { name: "关联事项" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "练习与反馈" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "相关笔记" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "资料内容" })).not.toBeInTheDocument();
  });
});

describe("Final UX Batch 3C · safe states and existing CTA contract", () => {
  it("chunk loading 保留 Material Header 并显示明确状态", async () => {
    vi.mocked(materialsApi.chunks).mockReturnValue(new Promise(() => undefined));
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByRole("heading", { level: 1, name: readyMaterial.title })).toBeInTheDocument();
    expect(await screen.findByText("正在读取资料内容")).toBeInTheDocument();
  });

  it("chunk error 不让整个详情白屏，并可重试", async () => {
    vi.mocked(materialsApi.chunks).mockRejectedValue(new Error("chunks unavailable"));
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByText("内容暂时无法读取：chunks unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: readyMaterial.title })).toBeInTheDocument();

    vi.mocked(materialsApi.chunks).mockResolvedValue(chunkPage() as never);
    await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByText("第一段内容")).toBeInTheDocument();
  });

  it("empty content 使用诚实空状态", async () => {
    vi.mocked(materialsApi.chunks).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10, pages: 0 });
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByText("当前资料暂无可显示内容")).toBeInTheDocument();
  });

  it("processing material 不请求 chunks，并说明资料正在准备", async () => {
    vi.mocked(materialsApi.get).mockResolvedValue({
      ...readyMaterial,
      ingestion_status: "processing",
      indexing_status: "pending",
      chunk_count: 0,
      indexed_chunk_count: 0,
    } as never);
    renderApp(<MaterialRoutes />, "/materials/1");
    expect(await screen.findByText("资料正在准备，完成后会显示提取内容")).toBeInTheDocument();
    expect(materialsApi.chunks).not.toHaveBeenCalled();
  });

  it("learning 保留关联、笔记、练习和 material-scoped AI URL", async () => {
    renderApp(<MaterialRoutes />, "/materials/1?view=learning");
    expect((await screen.findAllByText("学习 AI Agent")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "管理关联" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "记录笔记" })).toHaveAttribute(
      "href",
      "/knowledge?tab=notes&new=1&note_type=material&entity_type=material&entity_id=1",
    );
    expect(screen.getByRole("link", { name: "限定此资料提问" })).toHaveAttribute(
      "href",
      "/knowledge?tab=qa&scope=material&material_id=1",
    );
    expect(screen.getByRole("link", { name: "带着资料进入 AI 协作" })).toHaveAttribute("href", "/ai?material_id=1");
    expect(screen.getByRole("link", { name: /Agent 理解检查/ })).toHaveAttribute("href", "/activities/41");
    expect(screen.getByRole("link", { name: /Agent 阅读笔记/ })).toHaveAttribute("href", "/knowledge?tab=notes&note=31");
  });

  it("非法 material id 沿用 NotFound contract 且不请求 API", async () => {
    renderApp(<MaterialRoutes />, "/materials/foo?view=learning");
    expect(await screen.findByText("页面不存在")).toBeInTheDocument();
    expect(materialsApi.get).not.toHaveBeenCalled();
    expect(materialsApi.chunks).not.toHaveBeenCalled();
  });
});
