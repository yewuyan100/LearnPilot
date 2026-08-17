import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, screen } from "@testing-library/react";
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
  index_directory: "D:/isolated/data",
  server_date: "2026-08-10",
  server_time: "2026-08-10T12:00:00+08:00",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Final Fix Batch 2C 品牌与版本契约", () => {
  it("声明独立 LearnPilot favicon，且没有 MealCompass 资产引用", () => {
    const index = readFrontendFile("index.html");
    const favicon = readFrontendFile("public/favicon.svg");

    expect(index).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />');
    expect(favicon).toContain("<title>LearnPilot</title>");
    expect(`${index}\n${favicon}`).not.toMatch(/MealCompass/i);
  });

  it("锁定 5173，禁止 Vite 静默切换端口", () => {
    const viteConfig = readFrontendFile("vite.config.ts");
    expect(viteConfig).toMatch(/server:\s*\{\s*port:\s*5173,\s*strictPort:\s*true\s*\}/);
  });

  it("桌面与移动端使用相同的 LearnPilot LP 标志规则", async () => {
    renderApp(<App />, "/missing-batch-2c-route");
    expect(await screen.findByText("页面不存在")).toBeInTheDocument();

    const marks = Array.from(document.querySelectorAll(".brand-mark"));
    expect(marks).toHaveLength(2);
    for (const mark of marks) {
      expect(mark.querySelector(".brand-mark__icon .learnpilot-logo__p")).not.toBeNull();
      expect(mark).toHaveTextContent("LearnPilot");
    }
  });

  it("设置页显示 canonical 版本且不再暴露阶段号", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(metaPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))));

    renderApp(<App />, "/settings");
    expect(await screen.findByText("6.0.0")).toBeInTheDocument();
    expect(screen.queryByText(/\bV7\b/)).not.toBeInTheDocument();
  });

  it("未知地址返回 canonical 工作台且不再显示 V1 文案", async () => {
    renderApp(<App />, "/definitely-not-a-route");

    expect(await screen.findByText("这个地址没有对应的页面。")).toBeInTheDocument();
    expect(screen.queryByText(/\bV1\b/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回工作台" })).toHaveAttribute("href", "/workspace");
  });
});
