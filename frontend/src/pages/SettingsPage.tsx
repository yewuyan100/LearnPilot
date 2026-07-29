import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, FolderOpen, Info, Server, Trash2 } from "lucide-react";
import { dashboardApi, demoApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const meta = useQuery({ queryKey: ["meta"], queryFn: dashboardApi.meta, retry: 1 });
  const seed = useMutation({
    mutationFn: demoApi.seed,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      showToast("Demo 数据已导入", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const clear = useMutation({
    mutationFn: demoApi.clear,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries();
      showToast(result.deleted_goals ? "Demo 数据已清理" : "当前没有 Demo 数据", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  if (meta.isLoading) return <LoadingState label="正在检查本地服务" />;
  if (meta.isError) return <ErrorState message={meta.error.message} onRetry={() => meta.refetch()} />;
  const data = meta.data!;

  return (
    <div className="page">
      <header className="page-header"><h1>设置</h1><p>查看 V1 本地运行信息和 Demo 数据状态。</p></header>
      <section className="settings-grid">
        <article className="settings-card">
          <div className="settings-card__title"><Server size={19} /><h2>运行状态</h2></div>
          <dl>
            <div><dt>后端连接</dt><dd className="connection-ok"><CheckCircle2 size={15} />已连接</dd></div>
            <div><dt>应用版本</dt><dd>{data.app_version}</dd></div>
            <div><dt>数据库类型</dt><dd>{data.database_type}</dd></div>
            <div><dt>自动 Demo</dt><dd>{data.demo_data_enabled ? "已启用" : "未启用"}</dd></div>
          </dl>
        </article>
        <article className="settings-card">
          <div className="settings-card__title"><FolderOpen size={19} /><h2>文件上传</h2></div>
          <dl>
            <div><dt>允许类型</dt><dd>{data.allowed_file_types.join("、")}</dd></div>
            <div><dt>大小限制</dt><dd>{data.max_file_size_mb} MB</dd></div>
            <div className="settings-path"><dt>上传目录</dt><dd>{data.upload_directory}</dd></div>
          </dl>
        </article>
      </section>
      <section className="settings-card settings-card--wide">
        <div className="settings-card__title"><Database size={19} /><h2>Demo 数据</h2></div>
        <p>Demo 数据通过后端脚本和 API 创建，前端没有硬编码课程内容。重复导入不会创建副本。</p>
        <div className="button-row">
          <button className="button button--secondary" disabled={seed.isPending} onClick={() => seed.mutate()}>
            {seed.isPending ? "正在导入" : "导入 Demo 数据"}
          </button>
          <button
            className="button button--danger"
            disabled={clear.isPending}
            onClick={() => {
              if (window.confirm("确认清理所有标记为 Demo 的目标及其关联数据？")) clear.mutate();
            }}
          ><Trash2 size={16} />清理 Demo 数据</button>
        </div>
      </section>
      <div className="notice notice--info"><Info size={18} /><span>LLM、Embedding、RAG、Agent、MCP 和自动复习不属于 V1，当前没有可用开关。</span></div>
    </div>
  );
}
