import type { ReactNode } from "react";


function inline(value: string): ReactNode[] {
  return value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}


export function SafeMarkdown({ content }: { content: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flushList = () => {
    if (list.length) {
      blocks.push(<ul key={`list-${blocks.length}`}>{list.map((item, index) => <li key={index}>{inline(item)}</li>)}</ul>);
      list = [];
    }
  };
  content.split("\n").forEach((line, index) => {
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      list.push(bullet[1]);
      return;
    }
    flushList();
    if (heading) {
      const children = inline(heading[2]);
      if (heading[1].length === 1) blocks.push(<h1 key={index}>{children}</h1>);
      else if (heading[1].length === 2) blocks.push(<h2 key={index}>{children}</h2>);
      else blocks.push(<h3 key={index}>{children}</h3>);
    } else if (line.trim()) {
      blocks.push(<p key={index}>{inline(line)}</p>);
    } else {
      blocks.push(<div className="markdown-spacer" key={index} />);
    }
  });
  flushList();
  return <div className="safe-markdown">{blocks.length ? blocks : <p className="muted">还没有正文。</p>}</div>;
}
