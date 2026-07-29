import { Link } from "react-router-dom";

export function NotFoundPage() {
  return <div className="state-panel state-panel--empty"><strong>页面不存在</strong><p>这个地址没有对应的 V1 页面。</p><Link className="button button--primary" to="/today">返回今日学习</Link></div>;
}

