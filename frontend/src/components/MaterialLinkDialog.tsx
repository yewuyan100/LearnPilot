import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { coursesApi, goalsApi, materialLearningApi, type MaterialLinkInput } from "../api/resources";
import type { MaterialRelationType, MaterialTargetType } from "../types";
import { Dialog } from "./Dialog";
import { ErrorState, LoadingState } from "./States";
import { materialRelationLabel as relationLabels } from "./material-link-labels";
import { useToast } from "./toast-context";

export function MaterialLinkDialog({
  open,
  materialIds,
  onClose,
}: {
  open: boolean;
  materialIds: number[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [targetType, setTargetType] = useState<MaterialTargetType>("learning_goal");
  const [targetId, setTargetId] = useState("");
  const [parentCourseId, setParentCourseId] = useState("");
  const [relationType, setRelationType] = useState<MaterialRelationType>("reference");
  const [confirming, setConfirming] = useState(false);
  const goals = useQuery({ queryKey: ["goals"], queryFn: goalsApi.list, enabled: open });
  const courses = useQuery({ queryKey: ["courses"], queryFn: coursesApi.list, enabled: open });
  const points = useQuery({
    queryKey: ["knowledge-points", parentCourseId],
    queryFn: () => coursesApi.points(Number(parentCourseId)),
    enabled: open && targetType === "knowledge_point" && !!parentCourseId,
  });
  const links = useQuery({
    queryKey: ["material-learning-links", materialIds.join(",")],
    queryFn: () => materialLearningApi.all(materialIds),
    enabled: open && materialIds.length > 0,
  });

  const targetOptions = useMemo(() => {
    if (targetType === "learning_goal") return goals.data ?? [];
    if (targetType === "course") return courses.data ?? [];
    return points.data ?? [];
  }, [courses.data, goals.data, points.data, targetType]);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["material-learning-links"] }),
      queryClient.invalidateQueries({ queryKey: ["effective-materials"] }),
      queryClient.invalidateQueries({ queryKey: ["materials"] }),
    ]);
  };
  const save = useMutation({
    mutationFn: async () => {
      const id = Number(targetId);
      const link: MaterialLinkInput = {
        target_type: targetType,
        relation_type: relationType,
        is_primary: relationType === "primary_source",
        ...(targetType === "learning_goal" ? { learning_goal_id: id } : {}),
        ...(targetType === "course" ? { course_id: id } : {}),
        ...(targetType === "knowledge_point" ? { knowledge_point_id: id } : {}),
      };
      return materialIds.length === 1
        ? { requested: 1, succeeded: 1, failed: 0, items: [{ material_id: materialIds[0], success: true, link: await materialLearningApi.create(materialIds[0], link), error_code: null, error_message: null }] }
        : materialLearningApi.bulkMaterials(materialIds, link);
    },
    onSuccess: async (result) => {
      await invalidate();
      setConfirming(false);
      showToast(
        result.failed ? `${result.succeeded} 条已归类，${result.failed} 条未成功` : `${result.succeeded} 条资料已归类`,
        result.failed ? "error" : "success",
      );
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const remove = useMutation({
    mutationFn: ({ materialId, linkId }: { materialId: number; linkId: number }) => materialLearningApi.remove(materialId, linkId),
    onSuccess: invalidate,
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const update = useMutation({
    mutationFn: ({ materialId, linkId, relation }: { materialId: number; linkId: number; relation: MaterialRelationType }) =>
      materialLearningApi.update(materialId, linkId, { relation_type: relation, is_primary: relation === "primary_source" }),
    onSuccess: invalidate,
    onError: (error: Error) => showToast(error.message, "error"),
  });

  return <Dialog open={open} title={materialIds.length > 1 ? `批量关联 ${materialIds.length} 条资料` : "关联事项"} onClose={onClose}>
    <div className="material-link-dialog">
      <p className="muted">资料与事项的关系由你确认；系统只检查所选对象是否存在、关系是否一致。</p>
      <div className="form-grid">
        <label className="field"><span>关联位置</span><select aria-label="关联位置" value={targetType} onChange={(event) => { setTargetType(event.target.value as MaterialTargetType); setTargetId(""); }}><option value="learning_goal">事项</option><option value="course">路线</option><option value="knowledge_point">步骤</option></select></label>
        {targetType === "knowledge_point" && <label className="field"><span>所属路线</span><select aria-label="步骤所属路线" value={parentCourseId} onChange={(event) => { setParentCourseId(event.target.value); setTargetId(""); }}><option value="">选择路线</option>{courses.data?.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label>}
        <label className="field"><span>关联对象</span><select aria-label="关联对象" value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value="">选择对象</option>{targetOptions.map((target) => <option key={target.id} value={target.id}>{target.title}</option>)}</select></label>
        <label className="field"><span>关系</span><select aria-label="关系类型" value={relationType} onChange={(event) => setRelationType(event.target.value as MaterialRelationType)}>{Object.entries(relationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      {confirming ? <div className="notice notice--warning"><p>确认将所选资料关联到“{targetOptions.find((item) => item.id === Number(targetId))?.title}”？</p><div className="button-row"><button className="button button--secondary" onClick={() => setConfirming(false)}>返回检查</button><button className="button button--primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "正在归类" : "确认归类"}</button></div></div> : <div className="form-actions"><button className="button button--secondary" onClick={onClose}>取消</button><button className="button button--primary" disabled={!targetId || save.isPending} onClick={() => setConfirming(true)}><Link2 size={16}/>准备归类</button></div>}
      {materialIds.length === 1 && <section className="material-link-existing"><h3>已有直接关联</h3>{links.isLoading ? <LoadingState label="正在读取关联"/> : links.isError ? <ErrorState message={links.error.message}/> : links.data?.length ? links.data.map((link) => <article key={link.id}><div><strong>{link.target_title}</strong><small>{link.target_type === "learning_goal" ? "事项" : link.target_type === "course" ? "路线" : "步骤"}</small></div><select aria-label={`修改 ${link.target_title} 关系`} value={link.relation_type} onChange={(event) => update.mutate({ materialId: link.material_id, linkId: link.id, relation: event.target.value as MaterialRelationType })}>{Object.entries(relationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button className="icon-button icon-button--danger" aria-label={`删除关联 ${link.target_title}`} onClick={() => remove.mutate({ materialId: link.material_id, linkId: link.id })}><Trash2 size={16}/></button></article>) : <p className="muted">这份资料尚未关联任何事项、路线或步骤。</p>}</section>}
    </div>
  </Dialog>;
}
