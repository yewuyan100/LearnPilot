import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { goalsApi } from "../api/resources";
import type { LearningGoal } from "../types";
import { ActionMenu } from "./ActionMenu";
import { Dialog } from "./Dialog";
import { useToast } from "./toast-context";

export function GoalActions({
  goal,
  returnToPlanning = false,
}: {
  goal: LearningGoal;
  returnToPlanning?: boolean;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [title, setTitle] = useState(goal.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setTitle(goal.title), [goal.title]);

  const closeRename = () => {
    if (busy) return;
    setRenameOpen(false);
    setTitle(goal.title);
    setError("");
  };

  const rename = async () => {
    const nextTitle = title.trim();
    if (!nextTitle) {
      setError("事项名称不能为空");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await goalsApi.update(goal.id, { title: nextTitle });
      queryClient.setQueryData<LearningGoal[]>(["goals"], (items) =>
        items?.map((item) => item.id === goal.id ? updated : item),
      );
      queryClient.setQueryData(["goal", goal.id], updated);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["goals"] }),
        queryClient.invalidateQueries({ queryKey: ["goal", goal.id] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
      ]);
      setRenameOpen(false);
      showToast("事项名称已更新", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "事项重命名失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await goalsApi.remove(goal.id);
      setDeleteOpen(false);
      if (returnToPlanning) {
        navigate("/items", { replace: true, flushSync: true });
      } else {
        queryClient.removeQueries({ queryKey: ["goal", goal.id], exact: true });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["goals"] }),
        queryClient.invalidateQueries({ queryKey: ["courses"] }),
        queryClient.invalidateQueries({ queryKey: ["today"] }),
        queryClient.invalidateQueries({ queryKey: ["notes"] }),
        queryClient.invalidateQueries({ queryKey: ["next-learning-action"] }),
      ]);
      showToast("事项已删除", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "事项删除失败");
    } finally {
      setBusy(false);
    }
  };

  return <>
    <ActionMenu
      label={`管理事项 ${goal.title}`}
      items={[
        { label: "重命名", onSelect: () => { setError(""); setTitle(goal.title); setRenameOpen(true); } },
        { label: "删除事项", destructive: true, onSelect: () => { setError(""); setDeleteOpen(true); } },
      ]}
    />
    <Dialog open={renameOpen} title="重命名事项" onClose={closeRename}>
      <form className="management-dialog" onSubmit={(event) => { event.preventDefault(); void rename(); }}>
        <label><span>事项名称</span><input autoFocus aria-label="新的事项名称" value={title} maxLength={200} onChange={(event) => { setTitle(event.target.value); setError(""); }}/></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog-actions"><button type="button" className="button button--secondary" disabled={busy} onClick={closeRename}>取消</button><button type="submit" className="button button--primary" disabled={busy || !title.trim()}>{busy ? "保存中" : "保存"}</button></div>
      </form>
    </Dialog>
    <Dialog open={deleteOpen} title={`删除事项「${goal.title}」？`} onClose={() => { if (!busy) { setDeleteOpen(false); setError(""); } }}>
      <div className="management-dialog">
        <p>删除后，该事项将不再出现在学习规划中。</p>
        <p className="management-dialog__detail">事项内的路线、安排和推进记录将被删除；资料、笔记、摘录和回答会保留，并移除与此事项的关联。AI 协作会话会归档。</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="dialog-actions"><button type="button" className="button button--secondary" disabled={busy} onClick={() => { setDeleteOpen(false); setError(""); }}>取消</button><button type="button" className="button button--danger" disabled={busy} onClick={() => void remove()}>{busy ? "删除中" : "删除事项"}</button></div>
      </div>
    </Dialog>
  </>;
}
