import { FileText } from "lucide-react";
import type { EffectiveMaterial } from "../types";
import { EmptyState } from "./States";
import { materialRelationLabel } from "./material-link-labels";

const visibilityLabel = { direct: "直接关联", inherited: "继承资料", descendant: "下级关联" };

export function EffectiveMaterials({ items, emptyText }: { items: EffectiveMaterial[]; emptyText: string }) {
  if (!items.length) return <EmptyState title="还没有关联资料" description={emptyText} />;
  return <div className="effective-material-list">{items.map((item) => <article key={item.material_id}><FileText size={18}/><div><strong>{item.material_title || item.original_filename}</strong><p>{item.original_filename}</p><div className="tag-list">{item.contexts.map((context) => <span key={context.id} className={`ownership ownership--${context.visibility}`}>{visibilityLabel[context.visibility]} · {context.target_title} · {materialRelationLabel[context.relation_type]}</span>)}</div></div><span className={`status status--${item.indexing_status}`}>{item.indexing_status === "completed" ? "已索引" : "索引未完成"}</span></article>)}</div>;
}
