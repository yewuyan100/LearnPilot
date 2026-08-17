import { CheckCircle2, Database, FileArchive, FolderOpen, Info, Server } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../api/resources";
import { ErrorState, LoadingState } from "../components/States";

function State({ ready, readyLabel = "可用", missingLabel = "未配置" }: { ready: boolean; readyLabel?: string; missingLabel?: string }) {
  return <dd className={ready ? "connection-ok" : "muted"}>{ready && <CheckCircle2 size={15} />}{ready ? readyLabel : missingLabel}</dd>;
}

export function SettingsPage() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: dashboardApi.meta, retry: 1 });

  if (meta.isLoading) return <LoadingState label="正在检查本地服务" />;
  if (meta.isError) return <ErrorState message={meta.error.message} onRetry={() => meta.refetch()} />;
  const data = meta.data!;

  return (
    <div className="page settings-page">
      <header className="page-header"><p className="page-kicker">本地环境</p><h1>设置</h1><p>查看本地模型、数据和连接状态。</p></header>
      <section className="settings-grid">
        <article className="settings-card">
          <div className="settings-card__title"><Server size={19} /><h2>模型连接</h2></div>
          <dl>
            <div><dt>后端服务</dt><State ready={data.backend_status === "connected"} readyLabel="已连接" /></div>
            <div><dt>回答模型</dt><State ready={data.llm_configured} readyLabel={data.llm_model ?? "已配置"} missingLabel="未配置" /></div>
            <div><dt>密钥</dt><dd>仅在服务端读取，不在页面显示</dd></div>
          </dl>
        </article>
        <article className="settings-card">
          <div className="settings-card__title"><FileArchive size={19} /><h2>Embedding 与索引</h2></div>
          <dl>
            <div><dt>Embedding</dt><dd>{data.embedding_model}</dd></div>
            <div><dt>运行方式</dt><dd>{data.embedding_local_only ? `本地文件 · ${data.embedding_device}` : data.embedding_device}</dd></div>
            <div><dt>资料索引</dt><State ready={data.index_ready} readyLabel="索引文件可用" missingLabel="尚未建立" /></div>
          </dl>
        </article>
        <article className="settings-card">
          <div className="settings-card__title"><Database size={19} /><h2>数据存储</h2></div>
          <dl>
            <div><dt>业务数据库</dt><dd>{data.database_type}</dd></div>
            <div className="settings-path"><dt>索引目录</dt><dd>{data.index_directory}</dd></div>
            <div className="settings-path"><dt>上传目录</dt><dd>{data.upload_directory}</dd></div>
          </dl>
        </article>
        <article className="settings-card">
          <div className="settings-card__title"><FolderOpen size={19} /><h2>资料上传</h2></div>
          <dl>
            <div><dt>允许类型</dt><dd>{data.allowed_file_types.join("、")}</dd></div>
            <div><dt>单文件限制</dt><dd>{data.max_file_size_mb} MB</dd></div>
            <div><dt>应用版本</dt><dd>{data.app_version}</dd></div>
          </dl>
        </article>
      </section>
      <div className="notice notice--info"><Info size={18} /><span>清理缓存和导出数据当前没有可用后端接口。资料删除与索引重试请在资料页完成。</span></div>
    </div>
  );
}
