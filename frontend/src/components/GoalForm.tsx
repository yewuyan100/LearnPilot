import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { goalsApi } from "../api/resources";
import { useToast } from "./toast-context";

export function GoalForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [form, setForm] = useState({
    title: "",
    description: "",
    target_date: "",
    daily_minutes: 40,
    current_level: "",
  });
  const mutation = useMutation({
    mutationFn: () =>
      goalsApi.create({ ...form, target_date: form.target_date || null, status: "active" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["goals"] });
      await queryClient.invalidateQueries({ queryKey: ["today"] });
      showToast("学习目标已创建", "success");
      onDone();
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <form className="form-stack" onSubmit={submit}>
      <label className="field">
        <span>目标名称</span>
        <input
          required
          maxLength={200}
          value={form.title}
          onChange={(event) => setForm({ ...form, title: event.target.value })}
          placeholder="例如：三周入门 MCP"
        />
      </label>
      <label className="field">
        <span>目标描述</span>
        <textarea
          value={form.description}
          onChange={(event) => setForm({ ...form, description: event.target.value })}
          placeholder="写清楚你希望达到的结果"
        />
      </label>
      <div className="form-grid">
        <label className="field">
          <span>目标日期</span>
          <input
            type="date"
            value={form.target_date}
            onChange={(event) => setForm({ ...form, target_date: event.target.value })}
          />
        </label>
        <label className="field">
          <span>每日学习时间（分钟）</span>
          <input
            type="number"
            min={5}
            max={1440}
            required
            value={form.daily_minutes}
            onChange={(event) => setForm({ ...form, daily_minutes: Number(event.target.value) })}
          />
        </label>
      </div>
      <label className="field">
        <span>当前水平</span>
        <input
          maxLength={200}
          value={form.current_level}
          onChange={(event) => setForm({ ...form, current_level: event.target.value })}
          placeholder="例如：了解普通 API"
        />
      </label>
      <div className="form-actions">
        <button className="button button--secondary" type="button" onClick={onDone}>
          取消
        </button>
        <button className="button button--primary" disabled={mutation.isPending} type="submit">
          {mutation.isPending ? "正在创建" : "创建目标"}
        </button>
      </div>
    </form>
  );
}
