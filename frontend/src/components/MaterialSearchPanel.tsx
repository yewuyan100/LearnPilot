import { useMutation } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { materialsApi } from "../api/resources";
import type { Material } from "../types";
import { EmptyState } from "./States";
import { useToast } from "./toast-context";

export function MaterialSearchPanel({ materials }: { materials: Material[] }) {
  const { showToast } = useToast();
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [materialId, setMaterialId] = useState("");
  const search = useMutation({
    mutationFn: () =>
      materialsApi.search({
        query: query.trim(),
        top_k: topK,
        material_ids: materialId ? [Number(materialId)] : null,
      }),
    onError: (error: Error) => showToast(error.message, "error"),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) {
      showToast("请输入要检索的内容", "error");
      return;
    }
    search.mutate();
  };

  return (
    <section className="search-panel">
      <div className="section-heading">
        <div>
          <h2>资料检索测试</h2>
          <p>当前结果是资料检索片段，不是 AI 生成回答。</p>
        </div>
      </div>
      <form className="search-form" onSubmit={submit}>
        <label className="field search-form__query">
          <span>自然语言检索</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：MCP 中 Tools 和 Resources 有什么区别？"
          />
        </label>
        <label className="field">
          <span>资料范围</span>
          <select value={materialId} onChange={(event) => setMaterialId(event.target.value)}>
            <option value="">全部已索引资料</option>
            {materials
              .filter((material) => material.indexing_status === "completed")
              .map((material) => (
                <option key={material.id} value={material.id}>
                  {material.original_filename}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          <span>Top K</span>
          <select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
            {[3, 5, 10, 20].map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <button className="button button--primary" disabled={search.isPending} type="submit">
          <Search size={16} />{search.isPending ? "正在检索" : "检索片段"}
        </button>
      </form>

      {search.data && (
        <div className="search-results" aria-live="polite">
          <div className="search-results__meta">
            <span>{search.data.results.length} 条结果</span>
            <span>{search.data.model_name} · {search.data.duration_ms} ms</span>
          </div>
          {search.data.results.length === 0 ? (
            <EmptyState title="没有匹配片段" description="尝试更换关键词、资料范围或提高 Top K。" />
          ) : (
            search.data.results.map((result) => (
              <article className="search-result" key={result.chunk_id}>
                <div className="search-result__rank">{result.rank}</div>
                <div>
                  <header>
                    <strong>{result.original_filename}</strong>
                    <span>相似度 {result.score.toFixed(3)}</span>
                  </header>
                  <p className="chunk-source">
                    片段 {result.chunk_index + 1}
                    {result.page_number ? ` · 第 ${result.page_number} 页` : ""}
                    {result.section_title ? ` · ${result.section_title}` : ""}
                  </p>
                  <p>{result.content}</p>
                </div>
              </article>
            ))
          )}
        </div>
      )}
    </section>
  );
}
