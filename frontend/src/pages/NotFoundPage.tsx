import { Link } from "react-router-dom";

export function NotFoundPage() {
  return <div className="state-panel state-panel--empty"><strong>页面不存在</strong><p>这个地址没有对应的页面。</p><Link className="button button--primary" to="/workspace">返回工作台</Link></div>;
}
