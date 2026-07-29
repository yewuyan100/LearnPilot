import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, RefreshCw } from "lucide-react";
import { materialsApi } from "../api/resources";
import { formatDateTime } from "../utils/format";
import { useToast } from "./toast-context";

export function MaterialIndexPanel() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const index = useQuery({
    queryKey: ["material-index"],
    queryFn: materialsApi.indexStatus,
  });
  const rebuild = useMutation({
    mutationFn: materialsApi.rebuildIndex,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["material-index"] });
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      showToast("资料索引已重新构建", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const data = index.data;

  return (
    <section className="index-panel" aria-label="资料索引状态">
      <div className="index-panel__icon"><Database size={21} /></div>
      <div className="index-panel__main">
        <span className="section-label">本地语义索引</span>
        <strong>
          {index.isLoading
            ? "正在读取索引状态"
            : data?.available
              ? `${data.chunk_count} 个片段可检索`
              : "尚无可用索引"}
        </strong>
        <p>
          {index.isError
            ? index.error.message
            : data
              ? `${data.model_name} · ${data.embedding_dimension ?? "—"} 维 · ${formatDateTime(data.built_at)}${data.stale ? " · 需要重建" : ""}`
              : "处理资料后可构建本地 FAISS 索引"}
        </p>
        {data?.error_message && <p className="field-error">{data.error_message}</p>}
      </div>
      <button
        className="button button--secondary"
        disabled={rebuild.isPending || data?.building}
        onClick={() => rebuild.mutate()}
      >
        <RefreshCw size={16} />
        {rebuild.isPending || data?.building ? "正在构建" : "重新构建索引"}
      </button>
    </section>
  );
}
