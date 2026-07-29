import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Material } from "../types";
import { renderApp } from "./render";

const now = "2026-07-30T10:00:00";
const material: Material = {
  id: 8,
  title: "MCP 指南",
  original_filename: "mcp-guide.md",
  stored_filename: "8f4c.md",
  file_path: "uploads/8f4c.md",
  source_type: "md",
  mime_type: "text/markdown",
  file_size: 2048,
  processing_status: "ready",
  ingestion_status: "completed",
  indexing_status: "completed",
  chunk_count: 12,
  indexed_chunk_count: 12,
  processed_at: now,
  indexed_at: now,
  error_message: null,
  created_at: now,
  updated_at: now,
};

function response(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function installMaterialApi(overrides?: {
  material?: Material;
  statusAvailable?: boolean;
  process?: () => Promise<Response>;
}) {
  const item = overrides?.material ?? material;
  const fetchMock = vi.fn((input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/materials/index/status")) {
      return response({
        available: overrides?.statusAvailable ?? true,
        building: false,
        model_name: "BAAI/bge-m3",
        embedding_dimension: overrides?.statusAvailable === false ? null : 1024,
        chunk_count: overrides?.statusAvailable === false ? 0 : item.indexed_chunk_count,
        built_at: overrides?.statusAvailable === false ? null : now,
        index_version: overrides?.statusAvailable === false ? null : "v2",
        stale: false,
        error_message: null,
      });
    }
    if (url.endsWith("/materials/index/rebuild") && init?.method === "POST") {
      return response({
        index_version: "v2",
        chunk_count: item.chunk_count,
        model_name: "BAAI/bge-m3",
        embedding_dimension: 1024,
        built_at: now,
      });
    }
    if (url.endsWith(`/materials/${item.id}/process`) && init?.method === "POST") {
      return overrides?.process?.() ?? response(item);
    }
    if (url.endsWith(`/materials/${item.id}`) && init?.method === "DELETE") {
      return response(null, 204);
    }
    if (url.includes(`/materials/${item.id}/chunks`)) {
      return response({
        items: [{
          id: 91,
          material_id: item.id,
          chunk_index: 0,
          content: "Tools 允许模型调用由 Server 暴露的可执行能力。",
          char_count: 31,
          content_hash: "abc",
          page_number: 3,
          section_title: "Tools",
          created_at: now,
          updated_at: now,
        }],
        total: 12,
        page: 1,
        page_size: 10,
        pages: 2,
      });
    }
    if (url.endsWith("/materials/search") && init?.method === "POST") {
      return response({
        query: "Tools",
        model_name: "BAAI/bge-m3",
        index_version: "v2",
        duration_ms: 7,
        results: [{
          rank: 1,
          score: 0.876,
          chunk_id: 91,
          material_id: item.id,
          original_filename: item.original_filename,
          chunk_index: 0,
          content: "Tools 允许模型调用由 Server 暴露的可执行能力。",
          page_number: 3,
          section_title: "Tools",
        }],
      });
    }
    if (url.includes("/materials?")) return response([item]);
    return response([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("资料知识库 V2", () => {
  it("展示资料处理、索引状态和真实片段数量", async () => {
    installMaterialApi();
    renderApp(<App />, "/materials");

    expect((await screen.findAllByText("mcp-guide.md")).length).toBeGreaterThan(0);
    expect(screen.getByText("已解析")).toBeInTheDocument();
    expect(screen.getByText("已索引")).toBeInTheDocument();
    expect(screen.getByText(/12 个片段 · 已索引 12/)).toBeInTheDocument();
    expect(screen.getByText("12 个片段可检索")).toBeInTheDocument();
  });

  it("处理资料期间禁用重复提交并在成功后刷新", async () => {
    let resolveProcess: ((value: Response) => void) | undefined;
    const processPromise = new Promise<Response>((resolve) => {
      resolveProcess = resolve;
    });
    const fetchMock = installMaterialApi({ process: () => processPromise });
    renderApp(<App />, "/materials");

    const button = await screen.findByRole("button", { name: /重新处理/ });
    await userEvent.click(button);
    expect(await screen.findByRole("button", { name: /正在处理/ })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/materials/8/process"),
      expect.objectContaining({ method: "POST" }),
    );

    resolveProcess?.(new Response(JSON.stringify(material), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    await waitFor(() => expect(screen.getByText(/已完成解析和索引/)).toBeInTheDocument());
  });

  it("分页查看片段并明确展示来源", async () => {
    installMaterialApi();
    renderApp(<App />, "/materials");

    await userEvent.click(await screen.findByRole("button", { name: "查看片段" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("第 3 页 · Tools")).toBeInTheDocument();
    expect(within(dialog).getByText(/Tools 允许模型调用/)).toBeInTheDocument();
    expect(within(dialog).getByText(/共 12 个片段 · 第 1\/2 页/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "上一页片段" })).toBeDisabled();
  });

  it("按资料范围执行语义检索并展示非 AI 片段结果", async () => {
    const fetchMock = installMaterialApi();
    renderApp(<App />, "/materials");

    expect(await screen.findByText("当前结果是资料检索片段，不是 AI 生成回答。")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("自然语言检索"), "Tools");
    await userEvent.selectOptions(screen.getByLabelText("资料范围"), "8");
    await userEvent.click(screen.getByRole("button", { name: "检索片段" }));

    expect(await screen.findByText("相似度 0.876")).toBeInTheDocument();
    expect(screen.getByText("片段 1 · 第 3 页 · Tools")).toBeInTheDocument();
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/materials/search"));
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        query: "Tools",
        top_k: 5,
        material_ids: [8],
      });
    });
  });

  it("无索引时给出诚实状态，并可手动重建", async () => {
    const fetchMock = installMaterialApi({ statusAvailable: false });
    renderApp(<App />, "/materials");

    expect(await screen.findByText("尚无可用索引")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重新构建索引" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/materials/index/rebuild"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("展示后端失败原因并保留 V1 删除交互", async () => {
    const failedMaterial = {
      ...material,
      ingestion_status: "failed",
      indexing_status: "failed",
      chunk_count: 0,
      indexed_chunk_count: 0,
      error_message: "当前 PDF 未提取到可用文本，可能是扫描版文件；V2 暂不支持 OCR。",
    };
    const fetchMock = installMaterialApi({
      material: failedMaterial,
      statusAvailable: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp(<App />, "/materials");

    expect(await screen.findByText("解析失败")).toBeInTheDocument();
    expect(screen.getByText("索引失败")).toBeInTheDocument();
    expect(screen.getByText(/V2 暂不支持 OCR/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "删除 mcp-guide.md" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/materials/8"),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
  });
});
