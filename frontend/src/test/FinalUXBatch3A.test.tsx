import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { renderApp } from "./render";

const readFrontendFile = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");

const metaPayload = {
  backend_status: "connected",
  database_type: "SQLite",
  upload_directory: "D:/isolated/uploads",
  allowed_file_types: [".pdf", ".md", ".txt"],
  max_file_size_mb: 20,
  app_version: "6.0.0",
  demo_data_enabled: false,
  llm_configured: true,
  llm_model: "deepseek-chat",
  embedding_model: "BAAI/bge-m3",
  embedding_device: "cpu",
  embedding_local_only: true,
  index_ready: true,
  index_directory: "D:/isolated/index",
  server_date: "2026-08-10",
  server_time: "2026-08-10T12:00:00+08:00",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Final UX Batch 3A copy and chrome contract", () => {
  it("全局壳层只保留真实搜索范围，不显示推进口号、解释提示或营销页脚", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("[]", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))));

    renderApp(<App />, "/missing-final-ux-3a");
    expect(await screen.findByText("页面不存在")).toBeInTheDocument();
    expect(screen.queryByText(/先推进最值得处理的一步/)).not.toBeInTheDocument();
    expect(screen.queryByText(/让事项、行动、资料与建议回到同一个工作空间/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "全局搜索" }));
    expect(screen.getByPlaceholderText("搜索知识、笔记、资料或提问 AI...")).toBeInTheDocument();
    expect(screen.queryByText("只搜索当前已经接入的真实内容。")).not.toBeInTheDocument();
  });

  it("普通页面文案不再暴露内部实体名与索引实现词", () => {
    const copySurfaces = [
      "src/pages/AgentPage.tsx",
      "src/pages/RagPage.tsx",
      "src/components/MaterialSearchPanel.tsx",
      "src/components/TargetMaterialPicker.tsx",
      "src/pages/KnowledgePointDetailPage.tsx",
    ].map(readFrontendFile).join("\n");

    expect(copySurfaces).not.toContain("Goal/Course/KnowledgePoint");
    expect(copySurfaces).not.toContain("真实 MaterialChunk");
    expect(copySurfaces).not.toContain("知识索引可用");
    expect(copySurfaces).not.toContain("回答模型已配置");
    expect(copySurfaces).not.toContain("全部已索引资料");
    expect(copySurfaces).not.toContain("不需要选择或理解内部角色");
    expect(copySurfaces).toContain("事项、路线或步骤");
    expect(copySurfaces).toContain("原始资料片段");
    expect(copySurfaces).toContain("资料可用于问答");
  });

  it("设置页继续展示真实模型、数据、索引和连接状态", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(metaPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))));

    renderApp(<App />, "/settings");
    expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByText("查看本地模型、数据和连接状态。")).toBeInTheDocument();
    expect(screen.getByText("已连接")).toBeInTheDocument();
    expect(screen.getByText("deepseek-chat")).toBeInTheDocument();
    expect(screen.getByText("索引文件可用")).toBeInTheDocument();
    expect(screen.getByText("SQLite")).toBeInTheDocument();
  });

  it("发现页诚实显示未接入状态，不伪装为已启用", async () => {
    renderApp(<App />, "/explore");
    expect(await screen.findByRole("heading", { name: "从已知，继续探索未知" })).toBeInTheDocument();
    expect(screen.getByText("外部资料与趋势来源尚未接入。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "暂无外部内容" })).toBeInTheDocument();
    expect(screen.queryByText(/当前版本|已经就位|已启用/)).not.toBeInTheDocument();
  });
});
