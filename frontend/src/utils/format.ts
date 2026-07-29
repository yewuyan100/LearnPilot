export const formatDate = (value?: string | null) =>
  value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value)) : "未设置";

export const formatDateTime = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "—";

export const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

export const statusLabel: Record<string, string> = {
  active: "进行中",
  paused: "已暂停",
  completed: "已完成",
  archived: "已归档",
  cancelled: "已取消",
  draft: "草稿",
  ready: "已保存",
  uploaded: "已上传",
  failed: "失败",
  not_started: "未开始",
  learning: "学习中",
  locked: "已锁定",
  pending: "待完成",
  in_progress: "进行中",
  skipped: "已跳过",
};

