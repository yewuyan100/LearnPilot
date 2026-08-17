"""Author Real-world Gold Dataset V1 from frozen sources, without running RAG or an LLM."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[5]
CORPUS_ROOT = ROOT / "evals" / "rag_real_world_corpus" / "v1"
HERE = Path(__file__).resolve().parent


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


ANCHOR_SPECS: list[dict[str, Any]] = [
    # RAG retrieval
    {"id":"bge-capabilities","doc":"rw-rag-bge-m3","lines":[3,6],"section":"BGE-M3 introduction","region":"early"},
    {"id":"bge-pipeline","doc":"rw-rag-bge-m3","lines":[10,21],"section":"Suggestions for retrieval pipeline in RAG","region":"early"},
    {"id":"bge-miracl-correction","doc":"rw-rag-bge-m3","lines":[24,38],"section":"News","region":"early"},
    {"id":"bge-specs","doc":"rw-rag-bge-m3","lines":[42,53],"section":"Specs","region":"early"},
    {"id":"bge-methods","doc":"rw-rag-bge-m3","lines":[64,70],"section":"FAQ: different retrieval methods","region":"early"},
    {"id":"bge-no-query-instruction","doc":"rw-rag-bge-m3","lines":[73,79],"section":"FAQ: use in other projects","region":"middle"},
    {"id":"bge-dense-usage","doc":"rw-rag-bge-m3","lines":[109,132],"section":"Generate Embedding for text: Dense Embedding","region":"middle"},
    {"id":"bge-sparse-usage","doc":"rw-rag-bge-m3","lines":[136,162],"section":"Sparse Embedding (Lexical Weight)","region":"middle"},
    {"id":"bge-score-weights","doc":"rw-rag-bge-m3","lines":[184,207],"section":"Compute score for text pairs","region":"deep"},
    {"id":"bge-long-eval","doc":"rw-rag-bge-m3","lines":[224,252],"section":"Evaluation: Our results","region":"deep"},
    {"id":"bge-training","doc":"rw-rag-bge-m3","lines":[258,266],"section":"Training","region":"deep"},
    {"id":"faiss-purpose","doc":"rw-rag-faiss-overview","lines":[1,3],"section":"Faiss","region":"early"},
    {"id":"faiss-distance","doc":"rw-rag-faiss-overview","lines":[9,15],"section":"Introduction","region":"early"},
    {"id":"faiss-install","doc":"rw-rag-faiss-overview","lines":[17,19],"section":"Installing","region":"middle"},
    {"id":"faiss-tradeoffs","doc":"rw-rag-faiss-overview","lines":[21,32],"section":"How Faiss works","region":"middle"},
    {"id":"faiss-docs","doc":"rw-rag-faiss-overview","lines":[34,41],"section":"Full documentation of Faiss","region":"deep"},
    {"id":"faiss-license","doc":"rw-rag-faiss-overview","lines":[88,92],"section":"Legal","region":"deep"},
    # Agent engineering
    {"id":"agent-overview-purpose","doc":"rw-agent-langgraph-overview","lines":[22,33],"section":"Repository overview","region":"early"},
    {"id":"agent-overview-capabilities","doc":"rw-agent-langgraph-overview","lines":[35,46],"section":"Why use LangGraph?","region":"middle"},
    {"id":"agent-overview-ecosystem","doc":"rw-agent-langgraph-overview","lines":[48,57],"section":"LangGraph ecosystem","region":"middle"},
    {"id":"agent-overview-resources","doc":"rw-agent-langgraph-overview","lines":[61,75],"section":"Documentation and Additional resources","region":"deep"},
    {"id":"agent-overview-inspiration","doc":"rw-agent-langgraph-overview","lines":[80,82],"section":"Acknowledgements","region":"deep"},
    {"id":"persist-overview","doc":"rw-agent-persistence","lines":[14,21],"section":"Persistence overview","region":"early"},
    {"id":"persist-quickstart","doc":"rw-agent-persistence","lines":[23,63],"section":"Quickstart","region":"early"},
    {"id":"persist-comparison","doc":"rw-agent-persistence","lines":[65,74],"section":"Checkpointer vs. store","region":"middle"},
    {"id":"persist-thread-id","doc":"rw-agent-persistence","lines":[78,89],"section":"PostgresSaver: thread_id too long","region":"middle"},
    {"id":"persist-memorysaver","doc":"rw-agent-persistence","lines":[92,100],"section":"MemorySaver does not persist between restarts","region":"middle"},
    {"id":"persist-pruning","doc":"rw-agent-persistence","lines":[101,114],"section":"Checkpoints growing unboundedly","region":"deep"},
    {"id":"persist-subgraph","doc":"rw-agent-persistence","lines":[117,126],"section":"State access from parent graph to subgraph","region":"deep"},
    {"id":"interrupt-mechanism","doc":"rw-agent-interrupts","page":2,"region":"early","contains":"Graph execution gets suspended"},
    {"id":"interrupt-resume","doc":"rw-agent-interrupts","page":3,"region":"early","contains":"thread_id is the durable pointer back to the saved checkpoint"},
    {"id":"interrupt-streaming","doc":"rw-agent-interrupts","page":4,"region":"early","contains":"Detect interrupts via"},
    {"id":"interrupt-multiple","doc":"rw-agent-interrupts","page":5,"region":"middle","contains":"resume all pending interrupts at once"},
    {"id":"interrupt-approval","doc":"rw-agent-interrupts","page":6,"region":"middle","contains":"pass `True` to approve or `False` to reject"},
    {"id":"interrupt-review-edit","doc":"rw-agent-interrupts","page":8,"region":"middle","contains":"Review and edit this content"},
    {"id":"interrupt-tool-approval","doc":"rw-agent-interrupts","page":9,"region":"middle","contains":"Approve sending this email"},
    {"id":"interrupt-validation","doc":"rw-agent-interrupts","page":13,"region":"deep","contains":"exactly once per invocation"},
    {"id":"interrupt-restart-rule","doc":"rw-agent-interrupts","page":14,"region":"deep","contains":"Rules of interrupts"},
    {"id":"interrupt-try-catch","doc":"rw-agent-interrupts","page":15,"region":"deep","contains":"Conditionally handling errors"},
    {"id":"interrupt-order","doc":"rw-agent-interrupts","page":16,"region":"deep","contains":"same order every time"},
    {"id":"interrupt-serializable","doc":"rw-agent-interrupts","page":17,"region":"deep","contains":"simple, JSON-serializable types"},
    {"id":"interrupt-complex-values","doc":"rw-agent-interrupts","page":18,"region":"deep","contains":"function cannot be serialized"},
    {"id":"interrupt-side-effects","doc":"rw-agent-interrupts","page":19,"region":"deep","contains":"Use idempotent operations before"},
    {"id":"interrupt-side-effects-nodes","doc":"rw-agent-interrupts","page":20,"region":"deep","contains":"Separating into different nodes"},
    {"id":"interrupt-duplicate-risk","doc":"rw-agent-interrupts","page":21,"region":"deep","contains":"create duplicate records on each resume"},
    {"id":"interrupt-static","doc":"rw-agent-interrupts","page":22,"region":"deep","contains":"static interrupts as breakpoints"},
    {"id":"interrupt-runtime-static","doc":"rw-agent-interrupts","page":23,"region":"deep","contains":"run-time configuration"},
    # Backend
    {"id":"async-tldr","doc":"rw-backend-fastapi-async","lines":[5,53],"section":"In a hurry?","region":"early"},
    {"id":"async-io-bound","doc":"rw-backend-fastapi-async","lines":[67,94],"section":"Asynchronous Code","region":"early"},
    {"id":"async-concurrency-web","doc":"rw-backend-fastapi-async","lines":[236,260],"section":"Burger Conclusion","region":"middle"},
    {"id":"async-cpu-bound","doc":"rw-backend-fastapi-async","lines":[270,301],"section":"Concurrency + Parallelism","region":"middle"},
    {"id":"async-await-rules","doc":"rw-backend-fastapi-async","lines":[303,360],"section":"async and await","region":"deep"},
    {"id":"async-anyio","doc":"rw-backend-fastapi-async","lines":[364,386],"section":"Write your own async code","region":"deep"},
    {"id":"async-coroutine","doc":"rw-backend-fastapi-async","lines":[388,402],"section":"Coroutines","region":"deep"},
    {"id":"async-threadpool","doc":"rw-backend-fastapi-async","lines":[416,438],"section":"Very Technical Details","region":"deep"},
    {"id":"deps-meaning","doc":"rw-backend-fastapi-dependencies","lines":[7,20],"section":"What is Dependency Injection","region":"early"},
    {"id":"deps-dependable","doc":"rw-backend-fastapi-dependencies","lines":[28,52],"section":"Create a dependency","region":"early"},
    {"id":"deps-call","doc":"rw-backend-fastapi-dependencies","lines":[68,113],"section":"Declare the dependency","region":"middle"},
    {"id":"deps-annotated","doc":"rw-backend-fastapi-dependencies","lines":[117,141],"section":"Share Annotated dependencies","region":"middle"},
    {"id":"deps-mixed-async","doc":"rw-backend-fastapi-dependencies","lines":[143,155],"section":"To async or not to async","region":"middle"},
    {"id":"deps-openapi","doc":"rw-backend-fastapi-dependencies","lines":[159,175],"section":"Integrated with OpenAPI","region":"deep"},
    {"id":"deps-hierarchy","doc":"rw-backend-fastapi-dependencies","lines":[206,250],"section":"Simple and Powerful","region":"deep"},
    {"id":"errors-client-range","doc":"rw-backend-fastapi-errors","lines":[3,20],"section":"Handling Errors","region":"early"},
    {"id":"errors-http-exception","doc":"rw-backend-fastapi-errors","lines":[22,68],"section":"Use HTTPException","region":"early"},
    {"id":"errors-custom-headers","doc":"rw-backend-fastapi-errors","lines":[72,80],"section":"Add custom headers","region":"middle"},
    {"id":"errors-custom-handler","doc":"rw-backend-fastapi-errors","lines":[82,108],"section":"Install custom exception handlers","region":"middle"},
    {"id":"errors-override-validation","doc":"rw-backend-fastapi-errors","lines":[112,154],"section":"Override request validation exceptions","region":"middle"},
    {"id":"errors-leak-warning","doc":"rw-backend-fastapi-errors","lines":[172,186],"section":"RequestValidationError body warning","region":"deep"},
    {"id":"errors-fastapi-starlette","doc":"rw-backend-fastapi-errors","lines":[218,236],"section":"FastAPI HTTPException vs Starlette HTTPException","region":"deep"},
    {"id":"errors-reuse-handlers","doc":"rw-backend-fastapi-errors","lines":[238,244],"section":"Reuse FastAPI exception handlers","region":"deep"},
    # Evaluation and reliability
    {"id":"ragas-components","doc":"rw-eval-ragas-workflow","lines":[23,29],"section":"Build a Simple RAG System","region":"early"},
    {"id":"ragas-simple-retriever","doc":"rw-eval-ragas-workflow","lines":[46,73],"section":"Simple RAG implementation","region":"early"},
    {"id":"ragas-collect-data","doc":"rw-eval-ragas-workflow","lines":[116,164],"section":"Collect Evaluation Data","region":"middle"},
    {"id":"ragas-evaluate","doc":"rw-eval-ragas-workflow","lines":[166,185],"section":"Evaluate","region":"deep"},
    {"id":"ragas-embedding-interface","doc":"rw-eval-ragas-workflow","lines":[20,21],"section":"OpenAI Embeddings API note","region":"early"},
    {"id":"precision-definition","doc":"rw-eval-context-precision","lines":[1,15],"section":"Context Precision","region":"early"},
    {"id":"precision-reference-response","doc":"rw-eval-context-precision","lines":[19,66],"section":"Context Precision and Context Utilization","region":"early"},
    {"id":"precision-rank-effect","doc":"rw-eval-context-precision","lines":[63,113],"section":"Context Utilization rank example","region":"middle"},
    {"id":"precision-deprecation","doc":"rw-eval-context-precision","lines":[115,121],"section":"Legacy Metrics API","region":"middle"},
    {"id":"precision-without-reference","doc":"rw-eval-context-precision","lines":[144,167],"section":"Context Precision without reference","region":"middle"},
    {"id":"precision-with-reference","doc":"rw-eval-context-precision","lines":[170,193],"section":"Context Precision with reference","region":"deep"},
    {"id":"precision-nonllm","doc":"rw-eval-context-precision","lines":[196,225],"section":"Non LLM Based Context Precision","region":"deep"},
    {"id":"precision-id-based","doc":"rw-eval-context-precision","lines":[227,257],"section":"ID Based Context Precision","region":"deep"},
    {"id":"otel-trace-overview","doc":"rw-eval-otel-traces","page":1,"region":"early","contains":"give us the big picture"},
    {"id":"otel-parent-child","doc":"rw-eval-otel-traces","page":2,"region":"early","contains":"indicating it's a part of the same trace"},
    {"id":"otel-propagation-span","doc":"rw-eval-otel-traces","page":3,"region":"middle","contains":"Context Propagation is the core concept"},
    {"id":"otel-attributes-events","doc":"rw-eval-otel-traces","page":4,"region":"middle","contains":"Attributes are key-value pairs"},
    {"id":"otel-links-status","doc":"rw-eval-otel-traces","page":5,"region":"deep","contains":"The three possible values are"},
    {"id":"otel-async-spans","doc":"rw-eval-otel-traces","page":6,"region":"deep","contains":"start long after the producer span"}
]


def build_anchors(manifest: dict[str, Any]) -> dict[str, Any]:
    doc_by_id = {item["document_id"]:item for item in manifest["documents"]}
    anchors: list[dict[str, Any]] = []
    for spec in ANCHOR_SPECS:
        document = doc_by_id[spec["doc"]]
        path = ROOT / document["repository_path"]
        if "lines" in spec:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            start, end = spec["lines"]
            text = normalize("\n".join(lines[start - 1:end]))
            locator = {
                "kind":"SOURCE_LINES", "source_path":document["repository_path"],
                "start_line":start, "end_line":end, "section_title":spec["section"], "region":spec["region"],
            }
        else:
            page_number = spec["page"]
            text = normalize(PdfReader(str(path)).pages[page_number - 1].extract_text() or "")
            locator = {
                "kind":"PDF_PAGE", "source_path":document["repository_path"],
                "page_number":page_number, "region":spec["region"],
            }
            if normalize(spec["contains"]).casefold() not in text.casefold():
                raise RuntimeError(f"PDF anchor clue not found: {spec['id']}")
        excerpt = text[:417] + ("..." if len(text) > 417 else "")
        anchors.append({
            "evidence_id":"ev-rw-" + spec["id"], "document_id":spec["doc"], "locator":locator,
            "anchor_text_hash":sha256(text.encode("utf-8")).hexdigest(), "excerpt":excerpt,
            "language":"en", "notes":"Frozen source representation; hash covers the complete normalized locator text.",
        })
    return {
        "schema_version":"1.0.0",
        "corpus_ref":{"corpus_id":manifest["corpus_id"], "corpus_version":manifest["corpus_version"]},
        "anchor_count":len(anchors), "anchors":anchors,
    }


def ev(name: str) -> str:
    return "ev-rw-" + name


def claim(text: str, groups: list[int], mode: str = "SEMANTIC_REVIEW", terms: list[str] | None = None) -> dict[str, Any]:
    return {"text":text, "groups":groups, "mode":mode, "terms":terms}


def case(
    slug: str, tier: str, case_type: str, question: str, language: str, topic: str,
    difficulty: str, groups: list[list[str]], claims: list[dict[str, Any]], *,
    secondary: list[str] | None = None, accepts: list[tuple[str, list[str], str]] | None = None,
    distractors: list[tuple[str, str]] | None = None, region: str = "not_applicable",
    absent: tuple[list[str], list[str], str] | None = None,
) -> dict[str, Any]:
    return {
        "slug":slug, "tier":tier, "case_type":case_type, "question":question,
        "language":language, "topic":topic, "difficulty":difficulty, "groups":groups,
        "claims":claims, "secondary":secondary or [], "accepts":accepts or [],
        "distractors":distractors or [], "region":region, "absent":absent,
    }


CASES: list[dict[str, Any]] = [
    # CORE: single_doc_fact (10)
    case("single-bge-shape","CORE","single_doc_fact","BGE-M3 的向量维度和最大序列长度分别是多少？","zh-CN","rag_retrieval","easy",[["bge-specs"]],[claim("BAAI/bge-m3 has dimension 1024.",[0],"NUMERIC_EXACT",["1024"]),claim("BAAI/bge-m3 has sequence length 8192.",[0],"NUMERIC_EXACT",["8192"])]),
    case("single-faiss-cosine","CORE","single_doc_fact","Faiss 在什么条件下可以用点积来实现余弦相似度检索？","zh-CN","rag_retrieval","easy",[["faiss-distance"]],[claim("Faiss supports cosine similarity as dot product on normalized vectors.",[0])]),
    case("single-persist-thread-id","CORE","single_doc_fact","PostgresSaver 的 thread_id 应控制在什么长度以内，文档建议超长时怎么生成稳定 ID？","zh-CN","agent_engineering","easy",[["persist-thread-id"]],[claim("PostgresSaver thread_id values should stay under 255 characters.",[0],"NUMERIC_EXACT",["255"]),claim("A UUID or hash can be used when deterministic IDs are needed.",[0])]),
    case("single-interrupt-status","CORE","single_doc_fact","恢复审批节点时，布尔值 True 和 False 分别会把流程导向哪里？","zh-CN","agent_engineering","easy",[["interrupt-approval"]],[claim("A True resume value routes to proceed.",[0],"STRUCTURED_EXACT",["True","proceed"]),claim("A False resume value routes to cancel.",[0],"STRUCTURED_EXACT",["False","cancel"])]),
    case("single-dependency-defaults","CORE","single_doc_fact","FastAPI 文档里的 common_parameters 示例中，skip 和 limit 的默认值是什么？","zh-CN","ai_app_backend","easy",[["deps-dependable"]],[claim("skip defaults to 0.",[0],"NUMERIC_EXACT",["skip","0"]),claim("limit defaults to 100.",[0],"NUMERIC_EXACT",["limit","100"])]),
    case("single-error-response","CORE","single_doc_fact","访问不存在的 item_id='bar' 时，示例返回的 HTTP 状态码和 JSON detail 是什么？","zh-CN","ai_app_backend","easy",[["errors-http-exception"]],[claim("The response status is 404.",[0],"NUMERIC_EXACT",["404"]),claim("The JSON detail is 'Item not found'.",[0],"IDENTIFIER_EXACT",["Item not found"])]),
    case("single-precision-id","CORE","single_doc_fact","IDBasedContextPrecision 的示例里，4 个 retrieved IDs 命中 2 个 reference IDs，最终分数是多少？","zh-CN","evaluation_reliability","easy",[["precision-id-based"]],[claim("The example score is 0.5 (50%).",[0],"NUMERIC_EXACT",["0.5"])]),
    case("single-otel-status","CORE","single_doc_fact","OpenTelemetry span status 有哪三个取值，默认是哪一个？","zh-CN","evaluation_reliability","easy",[["otel-links-status"]],[claim("Span status values are Unset, Error, and Ok.",[0],"STRUCTURED_EXACT",["Unset","Error","Ok"]),claim("The default span status is Unset.",[0],"IDENTIFIER_EXACT",["Unset"])]),
    case("single-ragas-dataset","CORE","single_doc_fact","Ragas 教程把收集好的列表装载成哪个 dataset object？","zh-CN","evaluation_reliability","easy",[["ragas-collect-data"]],[claim("The list is loaded with EvaluationDataset.from_list into an EvaluationDataset.",[0],"IDENTIFIER_EXACT",["EvaluationDataset","from_list"])]),
    case("single-langgraph-js","CORE","single_doc_fact","What repository is identified as the equivalent JavaScript/TypeScript LangGraph library?","en","agent_engineering","easy",[["agent-overview-purpose"]],[claim("The equivalent JavaScript/TypeScript library is LangGraph.js.",[0],"IDENTIFIER_EXACT",["LangGraph.js"])]),

    # CORE: semantic_paraphrase (10)
    case("semantic-bge-functions","CORE","semantic_paraphrase","如果我想让同一个 embedding 模型同时做语义向量、词项匹配和细粒度多向量交互，BGE-M3 是否覆盖这三类能力？","zh-CN","rag_retrieval","medium",[["bge-capabilities","bge-methods"]],[claim("BGE-M3 supports dense retrieval, sparse retrieval, and multi-vector retrieval.",[0])]),
    case("semantic-faiss-compression","CORE","semantic_paraphrase","为了把十亿级向量装进单机内存，Faiss 的某些索引会牺牲什么，并且可以不保留什么？","zh-CN","rag_retrieval","medium",[["faiss-distance"]],[claim("Some compressed Faiss methods do not keep the original vectors.",[0]),claim("The compression/scaling trade-off is less precise search.",[0])]),
    case("semantic-checkpointer-store","CORE","semantic_paraphrase","为什么长期运行的 agent 既要有 durable execution 与 memory 能力，又要区分 thread-scoped checkpoint 和跨 thread store？","zh-CN","agent_engineering","medium",[["agent-overview-capabilities","persist-overview"],["persist-comparison"]],[claim("LangGraph's high-level capabilities and persistence guide both support durable continuity and memory for long-running agents.",[0]),claim("A checkpointer holds thread-scoped graph state, while a store holds application-defined cross-thread data such as preferences.",[1])]),
    case("semantic-interrupt-replay","CORE","semantic_paraphrase","暂停后继续执行时，为什么节点开头的代码可能再次运行，而不是从 interrupt 调用的下一行原地继续？","zh-CN","agent_engineering","medium",[["interrupt-restart-rule"]],[claim("Resuming restarts the entire node from the beginning rather than continuing at the call site.",[0])]),
    case("semantic-fastapi-blocking","CORE","semantic_paraphrase","第三方数据库库没有 await 接口时，FastAPI endpoint 应该写成普通 def 还是 async def？这种写法会不会让整个应用失去异步能力？","zh-CN","ai_app_backend","medium",[["async-tldr"]],[claim("A blocking third-party library should be used from a normal def path operation function.",[0]),claim("FastAPI still works asynchronously and can mix def with async def.",[0])]),
    case("semantic-deps-automatic","CORE","semantic_paraphrase","为什么 endpoint 不必手动调用每个依赖函数，仍能拿到它们的返回结果？","zh-CN","ai_app_backend","medium",[["deps-call"]],[claim("The endpoint declares a dependency by passing the callable to Depends without calling it.",[0]),claim("FastAPI calls it with parameters and injects its result into the path operation parameter.",[0])]),
    case("semantic-error-raise","CORE","semantic_paraphrase","在深层 utility function 里发现资源不存在时，抛出 HTTPException 为什么能立即终止当前请求？","zh-CN","ai_app_backend","medium",[["errors-http-exception"]],[claim("HTTPException is raised as a Python exception, so remaining path operation code is not executed.",[0]),claim("FastAPI sends the HTTP error carried by the exception to the client.",[0])]),
    case("semantic-context-order","CORE","semantic_paraphrase","两个检索片段一个相关、一个无关，仅交换它们的先后顺序，为什么 context precision 会下降？","zh-CN","evaluation_reliability","medium",[["precision-definition"],["precision-rank-effect"]],[claim("Context precision rewards relevant chunks appearing earlier in the ranking.",[0]),claim("Putting the irrelevant chunk first lowers the example score from about 1.0 to about 0.5.",[1])]),
    case("semantic-trace-correlation","CORE","semantic_paraphrase","服务链路里的 span 分散在不同进程生成时，靠什么机制把它们重新拼成一条 trace？","zh-CN","evaluation_reliability","medium",[["otel-propagation-span"]],[claim("Context propagation correlates spans and assembles them into a trace across generation locations.",[0])]),
    case("semantic-ragas-data","CORE","semantic_paraphrase","What four fields does the tutorial collect per query before building an EvaluationDataset, and which one can come from a prepared gold answer?","en","evaluation_reliability","medium",[["ragas-collect-data"]],[claim("Each record contains user_input, retrieved_contexts, response, and reference.",[0],"STRUCTURED_EXACT",["user_input","retrieved_contexts","response","reference"]),claim("The optional prepared golden answer becomes the reference.",[0])]),

    # CORE: long_doc_localization (10)
    case("long-bge-query-instruction","CORE","long_doc_localization","BGE-M3 用于 embedding retrieval 时，相比普通 BGE，query 预处理上有什么唯一差异？","zh-CN","rag_retrieval","hard",[["bge-no-query-instruction"]],[claim("BGE-M3 no longer requires adding instructions to queries.",[0])],region="middle"),
    case("long-bge-score-mix","CORE","long_doc_localization","BGE-M3 文档的 text-pair 评分示例如何把 dense、sparse 和 ColBERT 三种得分组合起来？","zh-CN","rag_retrieval","hard",[["bge-score-weights"]],[claim("compute_score accepts weights_for_different_modes and forms a weighted sum of dense, sparse, and ColBERT scores.",[0]),claim("The shown weights are 0.4, 0.2, and 0.4.",[0],"STRUCTURED_EXACT",["0.4","0.2"])],region="deep"),
    case("long-bge-training","CORE","long_doc_localization","BGE-M3 的训练部分怎样同时处理多检索模式监督、长文本批处理效率和资源不足时的长文本能力？","zh-CN","rag_retrieval","hard",[["bge-training"]],[claim("Self-knowledge distillation combines outputs from multiple retrieval modes as reward signals.",[0]),claim("Efficient batching targets long-text fine-tuning efficiency.",[0]),claim("MCLS improves long-text performance without fine-tuning when resources are insufficient.",[0])],region="deep"),
    case("long-langgraph-positioning","CORE","long_doc_localization","LangGraph 在长文档开头如何定位自身：它面向哪类 agent，又强调给开发者哪两类底层控制？","zh-CN","agent_engineering","hard",[["agent-overview-purpose"]],[claim("LangGraph positions itself as a low-level orchestration framework for long-running, stateful agents.",[0]),claim("It emphasizes control over both agent workflows and agent state.",[0])],region="early"),
    case("long-interrupt-validation","CORE","long_doc_localization","需要反复校验人工输入时，为什么不应在同一个节点里用 while 循环多次 interrupt，推荐的图结构是什么？","zh-CN","agent_engineering","hard",[["interrupt-validation"],["interrupt-order"]],[claim("The node should call interrupt exactly once using a question stored in state.",[0]),claim("Invalid input should update state and a conditional edge should route back for another invocation.",[0]),claim("Non-deterministic loops can change interrupt ordering across re-executions and are discouraged.",[1])],region="deep"),
    case("long-interrupt-static","CORE","long_doc_localization","静态 interrupt 适合调试还是人工审批？它可以在编译时和运行时分别怎样指定暂停位置？","zh-CN","agent_engineering","hard",[["interrupt-static"],["interrupt-runtime-static"]],[claim("Static interrupts are for debugging/testing as breakpoints, not recommended for human-in-the-loop workflows.",[0]),claim("Compile-time configuration uses interrupt_before/interrupt_after on compilation.",[0]),claim("Run-time invocation can provide interrupt_before/interrupt_after per invocation.",[1])],region="deep"),
    case("long-async-threadpool","CORE","long_doc_localization","FastAPI 对普通 def 的 path operation、普通 def 的 dependency，以及应用自己直接调用的普通 utility function，线程池处理有什么区别？","zh-CN","ai_app_backend","hard",[["async-threadpool"]],[claim("Normal def path operations run in an external threadpool and are awaited.",[0]),claim("Normal def dependencies also run in the external threadpool.",[0]),claim("A directly called normal def utility function is called directly, not automatically moved to the threadpool.",[0])],region="deep"),
    case("long-deps-hierarchy","CORE","long_doc_localization","FastAPI 如何解析多层 sub-dependencies，并把这些层级要求反映到 API 文档里？","zh-CN","ai_app_backend","hard",[["deps-hierarchy"],["deps-openapi"]],[claim("FastAPI builds and resolves a hierarchical dependency tree and injects results at each step.",[0]),claim("Dependency requirements and validations are included in the OpenAPI schema and interactive docs.",[1])],region="deep"),
    case("long-precision-nonllm","CORE","long_doc_localization","不使用 LLM 的 context precision 变体如何判断 retrieved context 是否相关，它还需要安装哪个额外包？","zh-CN","evaluation_reliability","hard",[["precision-nonllm"]],[claim("It compares each retrieved context with reference contexts using a non-LLM similarity measure such as Levenshtein distance.",[0]),claim("The example requires the rapidfuzz package.",[0],"IDENTIFIER_EXACT",["rapidfuzz"])],region="deep"),
    case("long-otel-links","CORE","long_doc_localization","When two operations are causally related but belong to separate traces, what OpenTelemetry mechanism associates them, and must they share a parent-child relationship?","en","evaluation_reliability","hard",[["otel-links-status"]],[claim("Span Links associate spans across traces causally.",[0]),claim("Links are optional and do not require the spans to be in the same parent-child trace.",[0])],region="deep"),

    # CORE: multi_doc_synthesis (10)
    case("multi-hybrid-index","CORE","multi_doc_synthesis","要搭一个 hybrid retrieval 管线，BGE-M3 能提供哪些检索信号，而 Faiss 负责什么？两者的职责不要混在一起。","zh-CN","rag_retrieval","hard",[["bge-pipeline"],["faiss-purpose","faiss-distance"]],[claim("BGE-M3 can supply dense and sparse retrieval signals and recommends hybrid retrieval plus reranking.",[0]),claim("Faiss indexes and searches dense vector representations using vector distances or dot products.",[1])],secondary=[]),
    case("multi-retrieval-eval","CORE","multi_doc_synthesis","Faiss 向量索引产出的检索结果，怎样作为 Ragas 的 retrieved_contexts 进入评估数据，并由 context precision 检查排序质量？","zh-CN","evaluation_reliability","hard",[["faiss-purpose","faiss-distance"],["ragas-collect-data"],["precision-definition"]],[claim("Faiss indexes and searches dense vectors by vector distance or dot product.",[0]),claim("The evaluation record supplies retrieved_contexts for each user_input.",[1]),claim("Context precision evaluates whether relevant chunks are ranked ahead of irrelevant chunks.",[2])],secondary=["rag_retrieval"]),
    case("multi-agent-resume","CORE","multi_doc_synthesis","长时间运行的 LangGraph agent 为何既需要 checkpointer，又需要在 interrupt 恢复时保持相同 thread_id？","zh-CN","agent_engineering","hard",[["persist-overview","persist-comparison"],["interrupt-resume"]],[claim("The checkpointer persists thread-scoped graph state as checkpoints for continuity and recovery.",[0]),claim("The same thread_id is the durable pointer used to return to the saved checkpoint when resuming.",[1])]),
    case("multi-agent-memory-hitl","CORE","multi_doc_synthesis","如何组合 checkpointer、store 和 interrupt，既支持当前审批流程恢复，又保留跨会话用户偏好？","zh-CN","agent_engineering","hard",[["persist-comparison"],["interrupt-mechanism"]],[claim("A checkpointer provides thread-scoped state for the interrupted workflow.",[0]),claim("A store carries cross-thread application data such as user preferences.",[0]),claim("interrupt suspends execution and returns an external resume value into the node.",[1])]),
    case("multi-backend-control","CORE","multi_doc_synthesis","FastAPI 接口在等待异步 I/O、复用鉴权依赖、以及把权限失败返回给客户端时，三部分各应依赖什么机制？","zh-CN","ai_app_backend","hard",[["async-tldr"],["deps-meaning","deps-hierarchy"],["errors-http-exception"]],[claim("Await-capable I/O belongs in async def path operations.",[0]),claim("Shared authentication/authorization requirements can be modeled as dependencies and sub-dependencies.",[1]),claim("An HTTPException can immediately return an appropriate client error.",[2])],secondary=[],region="mixed"),
    case("multi-async-dependency","CORE","multi_doc_synthesis","普通 def dependency 放进 async def endpoint 时，框架怎样执行它？依赖文档与并发文档分别提供了什么依据？","zh-CN","ai_app_backend","hard",[["deps-mixed-async"],["async-threadpool"]],[claim("FastAPI permits def dependencies inside async def path operations.",[0]),claim("A normal def dependency is executed in the external threadpool rather than awaited directly.",[1])]),
    case("multi-error-observability","CORE","multi_doc_synthesis","API 请求失败时，FastAPI 的异常处理负责客户端响应，而 OpenTelemetry span 应记录哪些状态语义？","zh-CN","ai_app_backend","hard",[["errors-http-exception"],["otel-links-status"]],[claim("FastAPI raises HTTPException to terminate the request and send an HTTP error response.",[0]),claim("A span status can be Error for a failed operation; Unset is the default and can still mean successful completion.",[1])],secondary=["evaluation_reliability"]),
    case("multi-eval-stack","CORE","multi_doc_synthesis","评估一个 RAG 系统时，Ragas workflow 提供的 reference/response/retrieved_contexts 与 context precision 的有 reference、无 reference 两种用法如何对应？","zh-CN","evaluation_reliability","hard",[["ragas-collect-data"],["precision-reference-response","precision-without-reference","precision-with-reference"]],[claim("The workflow record includes response, retrieved_contexts, and an optional reference.",[0]),claim("Reference-based context precision compares contexts to a reference response.",[1]),claim("Without-reference context precision compares contexts to the generated response.",[1])]),
    case("multi-rag-tracing","CORE","multi_doc_synthesis","一个 RAG 请求先检索再生成时，评估数据和 trace/span 结构分别怎样描述这条执行链？","zh-CN","evaluation_reliability","hard",[["ragas-components","ragas-collect-data"],["otel-trace-overview","otel-propagation-span"]],[claim("The RAG workflow separates vectorization, retrieval, and response generation and records retrieved contexts with the response.",[0]),claim("A trace represents the request path and spans represent units of work correlated through context propagation.",[1])],secondary=["rag_retrieval"]),
    case("multi-faiss-context-precision","CORE","multi_doc_synthesis","How do Faiss's index trade-offs and context precision measure different parts of retrieval quality, and why can improving speed alone not establish better ranking?","en","rag_retrieval","hard",[["faiss-tradeoffs"],["precision-definition"]],[claim("Faiss index choices trade search time, quality, memory, training time, and adding time.",[0]),claim("Context precision specifically measures how highly relevant retrieved chunks are ranked.",[1]),claim("A faster index does not by itself prove a better relevance ordering.",[0,1])],secondary=["evaluation_reliability"]),

    # CORE: source_disambiguation (10)
    case("disambig-bge-faiss","CORE","source_disambiguation","哪个来源说明模型能同时输出 dense/sparse/multi-vector 信号，哪个来源说明向量索引如何按 L2 或 dot product 搜索？","zh-CN","rag_retrieval","hard",[["bge-capabilities","bge-methods"],["faiss-distance"]],[claim("BGE-M3 documentation owns the three retrieval-functionality claim.",[0]),claim("Faiss documentation owns the L2/dot-product index-search claim.",[1])],distractors=[("rw-eval-context-precision","UNSUPPORTED for model capabilities and index mechanics.")]),
    case("disambig-bge-long","CORE","source_disambiguation","问到 8192-token 输入能力时，应引用 BGE-M3 规格还是 Faiss 的索引说明？邻近来源能提供什么、不能提供什么？","zh-CN","rag_retrieval","medium",[["bge-capabilities","bge-specs"]],[claim("The 8192-token input/sequence-length claim is documented by BGE-M3.",[0])],accepts=[("rw-rag-faiss-overview",["faiss-purpose"],"Faiss supports vector search context but not model token length.")],distractors=[("rw-eval-context-precision","Does not state embedding-model sequence length.")]),
    case("disambig-agent-persist-interrupt","CORE","source_disambiguation","“跨进程重启仍保留 checkpoint”与“人工暂停后用 Command 恢复”分别应该从 persistence TXT 和 interrupts PDF 的哪类证据判断？","zh-CN","agent_engineering","hard",[["persist-memorysaver","persist-comparison"],["interrupt-resume"]],[claim("Persistence documentation distinguishes in-memory savers from persistent checkpointers across restarts.",[0]),claim("Interrupts documentation explains Command resume using the durable thread pointer.",[1])],accepts=[("rw-agent-langgraph-overview",["agent-overview-capabilities"],"High-level durable execution and human-in-the-loop support, but not the detailed contracts.")],distractors=[("rw-eval-otel-traces","Tracing spans does not define checkpoint storage or Command resume semantics.")]),
    case("disambig-agent-memory","CORE","source_disambiguation","短期 thread state、跨 thread memory 和 human-in-the-loop 暂停这三个概念，三个 LangGraph 来源各自最适合支持哪一部分？","zh-CN","agent_engineering","hard",[["persist-comparison"],["interrupt-mechanism"]],[claim("Persistence TXT specifies checkpointer versus store scopes.",[0]),claim("Interrupts PDF specifies the pause/resume mechanism.",[1])],accepts=[("rw-agent-langgraph-overview",["agent-overview-capabilities"],"Provides high-level labels for durable execution, HITL, and memory.")],distractors=[("rw-eval-otel-traces","Trace context is not LangGraph thread memory or pause/resume state.")]),
    case("disambig-interrupt-static","CORE","source_disambiguation","为什么调试断点问题要找 interrupts PDF，而不是 LangGraph overview 或 persistence TXT？","zh-CN","agent_engineering","medium",[["interrupt-static","interrupt-runtime-static"]],[claim("Only the interrupts PDF specifies static interrupt breakpoints and their compile/run-time configuration.",[0])],accepts=[("rw-agent-langgraph-overview",["agent-overview-capabilities"],"Mentions debugging and HITL generally."), ("rw-agent-persistence",["persist-overview"],"Explains state persistence needed by workflows generally.")],distractors=[("rw-backend-fastapi-async","Async execution guidance does not define graph breakpoints.")]),
    case("disambig-fastapi-async-deps","CORE","source_disambiguation","endpoint 本身的 def/async def 选择与 dependency 的混用规则，应该分别依赖哪两份 FastAPI 文档？","zh-CN","ai_app_backend","hard",[["async-tldr","async-threadpool"],["deps-mixed-async"]],[claim("The async document provides endpoint selection and threadpool behavior.",[0]),claim("The dependency document states def/async def dependencies can be mixed with either endpoint style.",[1])],distractors=[("rw-backend-fastapi-errors","Does not govern async/dependency execution.")]),
    case("disambig-fastapi-errors","CORE","source_disambiguation","依赖解析成功后仍要返回 404，这个状态与 detail 由 dependency 文档还是 error-handling 文档定义？","zh-CN","ai_app_backend","medium",[["errors-http-exception"]],[claim("The error-handling document defines raising HTTPException and the 404/detail response.",[0])],accepts=[("rw-backend-fastapi-dependencies",["deps-call"],"Can explain that a dependency is invoked before the endpoint, not the HTTP error payload.")],distractors=[("rw-backend-fastapi-async","Concurrency guidance does not define the 404 response payload.")]),
    case("disambig-fastapi-exceptions","CORE","source_disambiguation","注册全局 HTTPException handler 时，为什么应对 Starlette 类型注册，却仍可在业务代码里抛 FastAPI 类型？","zh-CN","ai_app_backend","hard",[["errors-fastapi-starlette"]],[claim("FastAPI HTTPException inherits from Starlette HTTPException and accepts any JSON-able detail.",[0]),claim("Handlers should register for Starlette HTTPException to catch errors from Starlette and extensions.",[0])],accepts=[("rw-backend-fastapi-async",["async-threadpool"],"May explain execution context but not exception type hierarchy.")],distractors=[("rw-backend-fastapi-dependencies","Does not define exception-class hierarchy.")]),
    case("disambig-ragas-metrics","CORE","source_disambiguation","“怎样组织评估数据”与“怎样衡量相关 chunk 的排序”分别应查 Ragas workflow 还是 context precision 文档？","zh-CN","evaluation_reliability","hard",[["ragas-collect-data"],["precision-definition"]],[claim("The workflow document defines the evaluation dataset fields and construction.",[0]),claim("The context precision document defines the ranking metric and formula.",[1])],distractors=[("rw-eval-otel-traces","Tracing does not define Ragas dataset or precision metric.")]),
    case("disambig-ragas-otel","CORE","source_disambiguation","检索质量排序与分布式请求路径都属于 observability 邻域，但 context precision 和 trace 各自回答什么不同问题？","zh-CN","evaluation_reliability","hard",[["precision-definition"],["otel-trace-overview","otel-propagation-span"]],[claim("Context precision answers whether relevant retrieved chunks are ranked near the top.",[0]),claim("Tracing answers how work/spans form the end-to-end path of a request across services.",[1])],accepts=[("rw-eval-ragas-workflow",["ragas-evaluate"],"Supports the broader evaluation workflow only.")],distractors=[("rw-rag-faiss-overview","Vector indexing mechanics do not define the metric or distributed trace assembly.")]),
]
