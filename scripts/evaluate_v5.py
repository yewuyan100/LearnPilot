"""Evaluate V5 routing, tool control, confirmation, checkpoint, citations, and latency."""
from argparse import ArgumentParser
import json, os, subprocess
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx
from acceptance_v3 import ALEMBIC, BACKEND, live_backend, require

ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/"evals"/"agent_v5_cases.json"
FIXTURES=ROOT/"evals"/"fixtures"/"v5"

def pct(values): return mean(float(x) for x in values) if values else 0.0
def percentile(values,p):
    rows=sorted(values)
    if not rows:return 0.0
    return rows[min(len(rows)-1,round((len(rows)-1)*p))]

def seed(client):
    goal=require(client.post("/learning-goals",json={"title":"V5 评测目标","description":"专用评测夹具","target_date":None,"daily_minutes":30,"current_level":"入门","status":"active"}),201)
    course=require(client.post("/courses",json={"learning_goal_id":goal["id"],"title":"V5 Agent","description":"受控工具","status":"active"}),201)
    require(client.post(f"/courses/{course['id']}/knowledge-points",json={"title":"Checkpoint","description":"中断恢复","order_index":0,"estimated_minutes":20,"status":"learning"}),201)
    materials=[]
    for path in sorted(FIXTURES.iterdir()):
        row=require(client.post("/materials/upload",files={"file":(path.name,path.read_bytes(),"text/markdown")}),201)
        materials.append(require(client.post(f"/materials/{row['id']}/process"),200))
    return goal,course,materials

def run_case(client,cid,text,rid):
    started=perf_counter(); response=client.post(f"/agent/conversations/{cid}/runs",json={"input":text,"request_id":rid}); total=round((perf_counter()-started)*1000,2)
    body=require(response,202); tool=sum(x.get("duration_ms") or 0 for x in body["tool_calls"]); return body,total,tool,max(total-tool,0)

def evaluate(base_url):
    cases=json.loads(CASES.read_text(encoding="utf-8")); rows=[]; totals=[]; tools=[]; planners=[]
    with httpx.Client(base_url=base_url,timeout=600) as client:
        agent_status=require(client.get("/agent/status"),200)
        if not agent_status["llm_configured"]: raise RuntimeError("真实 LLM 未配置")
        goal,course,materials=seed(client)
        cid=require(client.post("/agent/conversations",json={"title":"V5 路由评测"}),201)["id"]
        for case in cases:
            text=case["input"].replace("课程 1",f"课程 {course['id']}")
            body,total,tool,planner=run_case(client,cid,text,f"v5-eval-{case['id']}")
            predicted=[x["tool_name"] for x in body["tool_calls"]]
            rows.append({"id":case["id"],"expected_intent":case["intent"],"actual_intent":body["intent"],"expected_tools":case["tools"],"actual_tools":predicted,
                "intent_correct":body["intent"]==case["intent"],"tool_exact":predicted==case["tools"],"plan_valid":body["status"] in {"completed","awaiting_confirmation"},
                "clarification_correct":(case["intent"]!="clarification" or body["intent"]=="clarification"),
                "unsupported_correct":(case["intent"]!="unsupported" or (body["intent"]=="unsupported" and not predicted)),
                "total_latency_ms":total,"tool_latency_ms":tool,"planner_latency_ms":planner})
            totals.append(total);tools.append(tool);planners.append(planner)

        # Controlled write: no write before approval, one write after approval, replay stays one.
        before=len(require(client.get("/today"),200)["tasks"])
        text=f"为学习目标 {goal['id']} 创建任务：标题 V5确认评测，日期 2026-08-01，预计 20 分钟"
        pending,total,tool,planner=run_case(client,cid,text,"v5-eval-write")
        confirmation_required=pending["status"]=="awaiting_confirmation" and pending["confirmation"] is not None
        no_write_before=len(require(client.get("/today"),200)["tasks"])==before
        approved=require(client.post(f"/agent/runs/{pending['id']}/confirm",json={"decision":"approve"}),200)
        after=len(require(client.get("/today"),200)["tasks"])
        replay=require(client.post(f"/agent/runs/{pending['id']}/confirm",json={"decision":"approve"}),200)
        write_idempotent=after==before+1 and len(require(client.get("/today"),200)["tasks"])==after and replay["idempotent_replay"]

        # Reject path.
        rejected_pending,_,_,_=run_case(client,cid,f"为学习目标 {goal['id']} 创建任务：标题 取消项，日期 2026-08-01","v5-eval-reject")
        count_before_reject=len(require(client.get("/today"),200)["tasks"])
        rejected=require(client.post(f"/agent/runs/{rejected_pending['id']}/confirm",json={"decision":"reject"}),200)
        reject_safe=rejected["status"]=="completed" and len(require(client.get("/today"),200)["tasks"])==count_before_reject

        rag=next(x for x in rows if x["id"]=="route-rag")
        rag_run=require(client.get(f"/agent/runs/{require(client.post(f'/agent/conversations/{cid}/runs',json={'input':'根据资料回答：写操作何时执行？','request_id':'v5-eval-citation-extra'}),202)['id']}"),200)
        citation_preserved=bool(rag_run["citations"]) and "[S" in (rag_run["final_answer"] or "")
        security=pct([x["unsupported_correct"] for x in rows if x["expected_intent"]=="unsupported"])
        expected_tool_total=sum(len(x["expected_tools"]) for x in rows); matched=sum(len(set(x["expected_tools"]) & set(x["actual_tools"])) for x in rows)
        checkpoint_resume=approved["status"]=="completed" and pending["conversation_id"]==approved["conversation_id"]
        result={"status":"completed","scope_note":"小型、专用、可核验的路由集合仅用于 V5 回归，不代表通用 Agent 能力或生产分布。",
          "metrics":{
            "Intent Accuracy":pct([x["intent_correct"] for x in rows]),
            "Tool Selection Exact Match":pct([x["tool_exact"] for x in rows]),
            "Tool Selection Recall":matched/max(expected_tool_total,1),
            "Plan/Argument Validity":pct([x["plan_valid"] for x in rows]),
            "Clarification Accuracy":pct([x["clarification_correct"] for x in rows if x["expected_intent"]=="clarification"]),
            "Unsupported Accuracy":security,"Confirmation Requirement":float(confirmation_required),
            "No-write-before-confirmation":float(no_write_before),"Write Idempotency":float(write_idempotent),
            "Tool Success":pct([all((c.get("result") or {}).get("success",False) for c in require(client.get(f"/agent/runs/{approved['id']}"),200)["tool_calls"])]),
            "Citation Preservation":float(citation_preserved),"Checkpoint Resume":float(checkpoint_resume),
            "Security Rejection":security,"Reject Safety":float(reject_safe),
            "Average Planner Latency ms":round(mean(planners),2),"Average Tool Latency ms":round(mean(tools),2),
            "Average Total Latency ms":round(mean(totals),2),"P50 Total Latency ms":percentile(totals,.5),"P95 Total Latency ms":percentile(totals,.95)},
          "cases":rows}
        return result

def main():
    parser=ArgumentParser(); parser.add_argument("--base-url",default="http://127.0.0.1:8000/api"); parser.add_argument("--isolated",action="store_true"); parser.add_argument("--port",type=int,default=8016); parser.add_argument("--output",type=Path); args=parser.parse_args()
    if args.isolated:
        with TemporaryDirectory(prefix="personal-learning-v5-eval-",ignore_cleanup_errors=True) as temp:
            path=Path(temp); env=os.environ.copy(); env.update({"DATABASE_URL":f"sqlite:///{(path/'eval.sqlite3').as_posix()}","UPLOAD_DIR":str(path/'uploads'),
              "FAISS_INDEX_PATH":str(path/'materials.faiss'),"FAISS_MANIFEST_PATH":str(path/'materials.faiss.manifest.json'),"AGENT_CHECKPOINT_DB_PATH":str(path/'checkpoints.sqlite'),
              "EMBEDDING_MODEL_NAME":"BAAI/bge-m3","EMBEDDING_MODEL_REVISION":"local-cache","EMBEDDING_LOCAL_FILES_ONLY":"true","EMBEDDING_DEVICE":"cpu","APP_VERSION":"5.0.0"})
            subprocess.run([str(ALEMBIC),"upgrade","head"],cwd=BACKEND,env=env,check=True,capture_output=True,text=True)
            with live_backend(port=args.port,environment=env,log_path=path/"backend.log") as url: report=evaluate(url)
    else: report=evaluate(args.base_url)
    rendered=json.dumps(report,ensure_ascii=False,indent=2); print(rendered)
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(rendered+"\n",encoding="utf-8")

if __name__=="__main__": main()
