export function LearnPilotLogo({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 40 40"
      aria-hidden="true"
      focusable="false"
    >
      <path className="learnpilot-logo__l" d="M8 6v21.5c0 3.6 2.9 6.5 6.5 6.5H19" />
      <path className="learnpilot-logo__p" d="M20 34V8h7a6.5 6.5 0 0 1 0 13h-7" />
      <circle className="learnpilot-logo__waypoint" cx="27" cy="8" r="2.25" />
    </svg>
  );
}
