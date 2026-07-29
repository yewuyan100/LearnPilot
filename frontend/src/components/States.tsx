import type { ReactNode } from "react";
import { AlertCircle, Inbox } from "lucide-react";

export function LoadingState({ label = "正在读取数据" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <AlertCircle size={24} />
      <div>
        <strong>数据未能加载</strong>
        <p>{message}</p>
      </div>
      {onRetry && <button className="button button--secondary" onClick={onRetry}>重新加载</button>}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-panel state-panel--empty">
      <Inbox size={28} />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

