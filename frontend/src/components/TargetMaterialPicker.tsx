import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { materialsApi, materialLearningApi, type MaterialLinkInput } from "../api/resources";
import type { MaterialRelationType, MaterialTargetType } from "../types";
import { Dialog } from "./Dialog";
import { LoadingState } from "./States";
import { useToast } from "./toast-context";
import { materialRelationLabel } from "./material-link-labels";

export function TargetMaterialPicker({ open, targetType, targetId, targetTitle, onClose }: {
  open: boolean;
  targetType: MaterialTargetType;
  targetId: number;
  targetTitle: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [materialId, setMaterialId] = useState("");
  const [relationType, setRelationType] = useState<MaterialRelationType>("reference");
  const materials = useQuery({ queryKey: ["materials", "", ""], queryFn: () => materialsApi.list(), enabled: open });
  const save = useMutation({
    mutationFn: () => {
      const input: MaterialLinkInput = {
        target_type: targetType,
        relation_type: relationType,
        is_primary: relationType === "primary_source",
        ...(targetType === "learning_goal" ? { learning_goal_id: targetId } : {}),
        ...(targetType === "course" ? { course_id: targetId } : {}),
        ...(targetType === "knowledge_point" ? { knowledge_point_id: targetId } : {}),
      };
      return materialLearningApi.create(Number(materialId), input);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["effective-materials"] }),
        queryClient.invalidateQueries({ queryKey: ["material-learning-links"] }),
      ]);
      showToast("资料已加入学习范围", "success");
      setMaterialId("");
      onClose();
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const usable = (materials.data ?? []).filter((item) => !item.archived_at && item.deletion_status === "active");
  return <Dialog open={open} title={`添加资料到 ${targetTitle}`} onClose={onClose}>
    {materials.isLoading ? <LoadingState/> : <div className="form-stack"><label className="field"><span>现有资料</span><select aria-label="选择现有资料" value={materialId} onChange={(event) => setMaterialId(event.target.value)}><option value="">选择资料</option>{usable.map((item) => <option key={item.id} value={item.id}>{item.title || item.original_filename}</option>)}</select></label><label className="field"><span>关系</span><select aria-label="添加资料关系" value={relationType} onChange={(event) => setRelationType(event.target.value as MaterialRelationType)}>{Object.entries(materialRelationLabel).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><p className="muted">系统会校验资料是否与已有事项、路线或步骤的归属冲突。</p><div className="form-actions"><button className="button button--secondary" onClick={onClose}>取消</button><button className="button button--primary" disabled={!materialId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "正在添加" : "确认添加"}</button></div></div>}
  </Dialog>;
}
