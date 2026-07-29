import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Filter, Search, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { materialsApi } from "../api/resources";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import { formatBytes, formatDateTime, statusLabel } from "../utils/format";

export function MaterialsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [dragging, setDragging] = useState(false);
  const materials = useQuery({
    queryKey: ["materials", search, type],
    queryFn: () => materialsApi.list(search, type),
  });
  const upload = useMutation({
    mutationFn: materialsApi.upload,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      showToast("资料已保存到本地", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const remove = useMutation({
    mutationFn: materialsApi.remove,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      showToast("资料和本地文件已删除", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const acceptFile = (file?: File) => {
    if (file) upload.mutate(file);
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files[0]);
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>资料</h1>
        <p>保存 PDF、Markdown 和 TXT 文件。V1 只管理文件与元数据，不解析正文。</p>
      </header>
      <section
        className={`upload-zone ${dragging ? "upload-zone--dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <UploadCloud size={30} />
        <div><strong>{upload.isPending ? "正在保存文件" : "拖入文件，或从本地选择"}</strong><p>允许 PDF、MD、Markdown、TXT，最大 20 MB</p></div>
        <button className="button button--primary" disabled={upload.isPending} onClick={() => inputRef.current?.click()}>
          选择文件
        </button>
        <input ref={inputRef} hidden type="file" accept=".pdf,.md,.markdown,.txt" onChange={(event) => acceptFile(event.target.files?.[0])} />
      </section>
      <div className="toolbar">
        <label className="search-field"><Search size={17} /><input aria-label="搜索资料" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索文件名" /></label>
        <label className="select-field"><Filter size={16} /><select aria-label="按类型筛选" value={type} onChange={(e) => setType(e.target.value)}><option value="">全部类型</option><option value="pdf">PDF</option><option value="md">Markdown</option><option value="markdown">Markdown</option><option value="txt">TXT</option></select></label>
      </div>
      {materials.isLoading ? <LoadingState label="正在读取资料列表" /> : materials.isError ? (
        <ErrorState message={materials.error.message} onRetry={() => materials.refetch()} />
      ) : !materials.data?.length ? (
        <EmptyState title="资料收件箱是空的" description="上传一份本地资料，文件会保存到受控目录。" action={<button className="button button--primary" onClick={() => inputRef.current?.click()}>上传资料</button>} />
      ) : (
        <div className="data-list">
          {materials.data.map((material) => (
            <article className="data-row" key={material.id}>
              <span className="file-icon"><FileText size={20} /></span>
              <div className="data-row__main">
                <strong>{material.original_filename}</strong>
                <span>{material.source_type.toUpperCase()} · {formatBytes(material.file_size)} · {formatDateTime(material.created_at)}</span>
              </div>
              <span className={`status status--${material.processing_status}`}>{statusLabel[material.processing_status]}</span>
              <button
                className="icon-button icon-button--danger"
                aria-label={`删除 ${material.original_filename}`}
                onClick={() => {
                  if (window.confirm(`确认删除“${material.original_filename}”？本地文件也会被删除。`)) remove.mutate(material.id);
                }}
              ><Trash2 size={17} /></button>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
