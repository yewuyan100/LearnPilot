import type { ReactNode } from "react";

export function DashboardCard({
  title,
  meta,
  action,
  children,
  className = "",
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return <section className={`dashboard-card ${className}`}>
    <header className="dashboard-card__header">
      <div><h2>{title}</h2>{meta && <p>{meta}</p>}</div>
      {action}
    </header>
    {children}
  </section>;
}

export function SectionHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <header className="section-heading workspace-section-heading">
    <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
    {action}
  </header>;
}
