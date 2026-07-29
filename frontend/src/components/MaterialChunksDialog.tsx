import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FileText } from "lucide-react";
import { useState } from "react";
import { materialsApi } from "../api/resources";
import type { Material } from "../types";
import { Dialog } from "./Dialog";
import { EmptyState, ErrorState, LoadingState } from "./States";

export function MaterialChunksDialog({
  material,
  onClose,
}: {
  material: Material | null;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const chunks = useQuery({
    queryKey: ["material-chunks", material?.id, page],
    queryFn: () => materialsApi.chunks(material!.id, page, 10),
    enabled: Boolean(material),
  });

  return (
    <Dialog
      open={Boolean(material)}
      title={material ? `资料片段 · ${material.original_filename}` : "资料片段"}
      onClose={() => {
        setPage(1);
        onClose();
      }}
    >
      <div className="chunk-dialog">
        {chunks.isLoading ? (
          <LoadingState label="正在读取资料片段" />
        ) : chunks.isError ? (
          <ErrorState message={chunks.error.message} onRetry={() => chunks.refetch()} />
        ) : !chunks.data?.items.length ? (
          <EmptyState
            title="还没有资料片段"
            description="请先处理资料，再查看清洗和切片结果。"
          />
        ) : (
          <>
            <div className="chunk-list">
              {chunks.data.items.map((chunk) => (
                <article className="chunk-card" key={chunk.id}>
                  <header>
                    <span><FileText size={15} />片段 {chunk.chunk_index + 1}</span>
                    <span>{chunk.char_count} 字符</span>
                  </header>
                  <div className="chunk-source">
                    {chunk.page_number ? `第 ${chunk.page_number} 页` : "无页码"}
                    {chunk.section_title ? ` · ${chunk.section_title}` : ""}
                  </div>
                  <pre>{chunk.content}</pre>
                </article>
              ))}
            </div>
            <footer className="pagination">
              <span>共 {chunks.data.total} 个片段 · 第 {chunks.data.page}/{Math.max(chunks.data.pages, 1)} 页</span>
              <div className="button-row">
                <button
                  className="icon-button"
                  aria-label="上一页片段"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => current - 1)}
                >
                  <ChevronLeft size={17} />
                </button>
                <button
                  className="icon-button"
                  aria-label="下一页片段"
                  disabled={page >= chunks.data.pages}
                  onClick={() => setPage((current) => current + 1)}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
            </footer>
          </>
        )}
      </div>
    </Dialog>
  );
}
