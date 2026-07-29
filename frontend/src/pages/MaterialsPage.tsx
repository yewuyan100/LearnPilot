import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Eye,
  FileText,
  Filter,
  RefreshCw,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { materialsApi } from "../api/resources";
import { MaterialChunksDialog } from "../components/MaterialChunksDialog";
import { MaterialIndexPanel } from "../components/MaterialIndexPanel";
import { MaterialSearchPanel } from "../components/MaterialSearchPanel";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { useToast } from "../components/toast-context";
import type { Material } from "../types";
import {
  formatBytes,
  formatDateTime,
  indexingStatusLabel,
  ingestionStatusLabel,
  statusLabel,
} from "../utils/format";

export function MaterialsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [dragging, setDragging] = useState(false);
  const [chunkMaterial, setChunkMaterial] = useState<Material | null>(null);
  const materials = useQuery({
    queryKey: ["materials", search, type],
    queryFn: () => materialsApi.list(search, type),
  });
  const upload = useMutation({
    mutationFn: materialsApi.upload,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      showToast("资料已保存，请点击“处理资料”建立知识片段", "success");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const processMaterial = useMutation({
    mutationFn: materialsApi.process,
    onSuccess: async (material) => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      await queryClient.invalidateQueries({ queryKey: ["material-index"] });
      showToast(`${material.original_filename} 已完成解析和索引`, "success");
    },
    onError: (error: Error) => {
      queryClient.invalidateQueries({ queryKey: ["materials"] });
      queryClient.invalidateQueries({ queryKey: ["material-index"] });
      showToast(error.message, "error");
    },
  });
  const remove = useMutation({
    mutationFn: materialsApi.remove,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      await queryClient.invalidateQueries({ queryKey: ["material-index"] });
      showToast("资料、片段和本地索引已更新", "success");
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

  const materialItems = materials.data ?? [];

  return (
    <div className="page">
      <header className="page-header">
        <h1>资料知识库</h1>
        <p>上传本地资料，解析为稳定片段，并使用本地 BGE-M3 与 FAISS 进行语义检索。</p>
      </header>

      <MaterialIndexPanel />

      <section
        className={`upload-zone ${dragging ? "upload-zone--dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <UploadCloud size={30} />
        <div>
          <strong>{upload.isPending ? "正在保存文件" : "拖入文件，或从本地选择"}</strong>
          <p>允许 PDF、MD、Markdown、TXT，最大 20 MB；上传后由你确认开始处理。</p>
        </div>
        <button
          className="button button--primary"
          disabled={upload.isPending}
          onClick={() => inputRef.current?.click()}
        >
          选择文件
        </button>
        <input
          ref={inputRef}
          hidden
          type="file"
          accept=".pdf,.md,.markdown,.txt"
          onChange={(event) => {
            acceptFile(event.target.files?.[0]);
            event.currentTarget.value = "";
          }}
        />
      </section>

      <div className="toolbar">
        <label className="search-field">
          <Search size={17} />
          <input
            aria-label="搜索资料"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索文件名"
          />
        </label>
        <label className="select-field">
          <Filter size={16} />
          <select aria-label="按类型筛选" value={type} onChange={(event) => setType(event.target.value)}>
            <option value="">全部类型</option>
            <option value="pdf">PDF</option>
            <option value="md">Markdown (.md)</option>
            <option value="markdown">Markdown (.markdown)</option>
            <option value="txt">TXT</option>
          </select>
        </label>
      </div>

      {materials.isLoading ? (
        <LoadingState label="正在读取资料列表" />
      ) : materials.isError ? (
        <ErrorState message={materials.error.message} onRetry={() => materials.refetch()} />
      ) : !materialItems.length ? (
        <EmptyState
          title="资料知识库是空的"
          description="上传一份本地资料，文件会先保存，再由你启动解析和索引。"
          action={<button className="button button--primary" onClick={() => inputRef.current?.click()}>上传资料</button>}
        />
      ) : (
        <div className="material-list">
          {materialItems.map((material) => {
            const processing =
              processMaterial.isPending && processMaterial.variables === material.id;
            return (
              <article className="material-card" key={material.id}>
                <div className="material-card__file">
                  <span className="file-icon"><FileText size={20} /></span>
                  <div>
                    <strong>{material.original_filename}</strong>
                    <span>
                      {material.source_type.toUpperCase()} · {formatBytes(material.file_size)} · {formatDateTime(material.created_at)}
                    </span>
                    <span>{statusLabel[material.processing_status]} · {material.chunk_count} 个片段 · 已索引 {material.indexed_chunk_count}</span>
                  </div>
                </div>
                <div className="material-card__states">
                  <span className={`status status--${material.ingestion_status}`}>
                    {ingestionStatusLabel[material.ingestion_status] ?? material.ingestion_status}
                  </span>
                  <span className={`status status--${material.indexing_status}`}>
                    {indexingStatusLabel[material.indexing_status] ?? material.indexing_status}
                  </span>
                </div>
                <dl className="material-card__dates">
                  <div><dt>处理完成</dt><dd>{formatDateTime(material.processed_at)}</dd></div>
                  <div><dt>索引完成</dt><dd>{formatDateTime(material.indexed_at)}</dd></div>
                </dl>
                {material.error_message && (
                  <p className="material-card__error">{material.error_message}</p>
                )}
                <div className="material-card__actions">
                  <button
                    className="button button--primary"
                    disabled={processing || material.ingestion_status === "processing" || material.indexing_status === "indexing"}
                    onClick={() => processMaterial.mutate(material.id)}
                  >
                    <RefreshCw size={16} />
                    {processing
                      ? "正在处理"
                      : material.ingestion_status === "completed"
                        ? "重新处理"
                        : "处理资料"}
                  </button>
                  <button
                    className="button button--secondary"
                    disabled={material.chunk_count === 0}
                    onClick={() => setChunkMaterial(material)}
                  >
                    <Eye size={16} />查看片段
                  </button>
                  <button
                    className="icon-button icon-button--danger"
                    aria-label={`删除 ${material.original_filename}`}
                    disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm(`确认删除“${material.original_filename}”？本地文件、资料片段和索引都会更新。`)) {
                        remove.mutate(material.id);
                      }
                    }}
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <MaterialSearchPanel materials={materialItems} />
      <MaterialChunksDialog material={chunkMaterial} onClose={() => setChunkMaterial(null)} />
    </div>
  );
}
