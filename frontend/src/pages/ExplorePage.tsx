import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

export function ExplorePage() {
  return <div className="page composition-page explore-page">
    <section className="discovery-canvas" aria-labelledby="discovery-title">
      <div className="discovery-copy">
        <span className="discovery-status">规划中</span>
        <h1 id="discovery-title">从已知，继续探索未知</h1>
        <p>未来会把你的资料、事项与学习线索连接起来；此刻不生成并不存在的推荐。</p>
        <div className="discovery-availability"><h2>暂无外部内容</h2><p>外部资料与趋势来源尚未接入。</p></div>
        <div className="discovery-planned" aria-label="计划中的探索线索"><span>已有关联资料</span><span>正在推进的主题</span><span>可继续追问的线索</span></div>
        <div className="button-row"><Link className="button button--primary" to="/knowledge">查看已有内容<ArrowRight size={16}/></Link><Link className="text-link" to="/ai">带着问题进入 AI 协作</Link></div>
      </div>
      <div className="discovery-map" aria-hidden="true"><svg viewBox="0 0 640 520" role="presentation"><path className="discovery-map__path discovery-map__path--known" d="M72 398C160 380 172 304 254 294C344 283 360 216 430 202"/><path className="discovery-map__path discovery-map__path--future" d="M430 202C494 190 510 116 576 88"/><path className="discovery-map__branch" d="M254 294C286 344 332 362 380 372"/><circle className="discovery-map__node discovery-map__node--known" cx="72" cy="398" r="12"/><circle className="discovery-map__node discovery-map__node--known" cx="254" cy="294" r="10"/><circle className="discovery-map__node discovery-map__node--current" cx="430" cy="202" r="15"/><circle className="discovery-map__node discovery-map__node--future" cx="576" cy="88" r="10"/><circle className="discovery-map__node discovery-map__node--future" cx="380" cy="372" r="8"/></svg></div>
    </section>
  </div>;
}
