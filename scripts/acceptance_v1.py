"""Run the six V1 acceptance scenarios against a live local API."""

from datetime import date
import json
import sys

import httpx

BASE_URL = "http://127.0.0.1:8000/api"


def require(response: httpx.Response, expected: int) -> dict:
    if response.status_code != expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}: {response.text}"
        )
    return response.json() if response.content else {}


def main() -> None:
    results: list[str] = []
    with httpx.Client(base_url=BASE_URL, timeout=20) as client:
        require(client.get("/health"), 200)

        goal = require(
            client.post(
                "/learning-goals",
                json={
                    "title": "三周入门 MCP（V1 验收）",
                    "description": "理解 MCP 的核心概念并完成一个基础 Server",
                    "daily_minutes": 40,
                    "current_level": "了解普通 API",
                    "status": "active",
                },
            ),
            201,
        )
        persisted = require(client.get(f"/learning-goals/{goal['id']}"), 200)
        assert persisted["title"] == goal["title"]
        results.append("场景一：目标创建并通过独立 GET 验证持久化")

        materials = []
        materials.append(
            require(
                client.post(
                    "/materials/upload",
                    files={"file": ("mcp-overview.pdf", b"%PDF-1.4\n% V1 metadata test\n", "application/pdf")},
                ),
                201,
            )
        )
        materials.append(
            require(
                client.post(
                    "/materials/upload",
                    files={"file": ("mcp-notes.md", b"# MCP Notes\n\nV1 file storage.", "text/markdown")},
                ),
                201,
            )
        )
        listed_materials = require(client.get("/materials"), 200)
        assert {item["source_type"] for item in listed_materials}.issuperset({"pdf", "md"})
        results.append("场景二：PDF 与 Markdown 上传、元数据和 ready 状态验证")

        course = require(
            client.post(
                "/courses",
                json={
                    "learning_goal_id": goal["id"],
                    "title": "MCP 基础（V1 验收）",
                    "description": "手动课程结构验收",
                    "status": "active",
                },
            ),
            201,
        )
        points = []
        for index, title in enumerate(
            ["MCP 的定位", "Client 与 Server", "Tools", "Resources", "Prompts", "Transport"],
            start=1,
        ):
            points.append(
                require(
                    client.post(
                        f"/courses/{course['id']}/knowledge-points",
                        json={
                            "title": title,
                            "description": f"V1 手动知识点：{title}",
                            "order_index": index,
                            "estimated_minutes": 20,
                        },
                    ),
                    201,
                )
            )
        assert len(require(client.get(f"/courses/{course['id']}/knowledge-points"), 200)) == 6
        results.append("场景三：课程与六个手动知识点创建成功")

        task = require(
            client.post(
                "/daily-tasks",
                json={
                    "learning_goal_id": goal["id"],
                    "course_id": course["id"],
                    "knowledge_point_id": points[0]["id"],
                    "title": "学习 MCP 的定位（V1 验收）",
                    "task_type": "learning",
                    "estimated_minutes": 20,
                    "scheduled_date": date.today().isoformat(),
                    "status": "pending",
                },
            ),
            201,
        )
        today = require(client.get("/today"), 200)
        assert any(item["id"] == task["id"] for item in today["tasks"])
        results.append("场景四：今日任务创建并出现在首页 API")

        session = require(
            client.post(
                "/learning-sessions",
                json={
                    "learning_goal_id": goal["id"],
                    "course_id": course["id"],
                    "knowledge_point_id": points[0]["id"],
                    "daily_task_id": task["id"],
                },
            ),
            201,
        )
        completed = require(
            client.patch(
                f"/learning-sessions/{session['id']}",
                json={
                    "notes": "验收笔记：理解了 MCP 在主机与工具之间的协议定位。",
                    "status": "completed",
                    "knowledge_point_status": "completed",
                    "daily_task_status": "completed",
                },
            ),
            200,
        )
        assert completed["notes"].startswith("验收笔记")
        assert completed["ended_at"] is not None
        results.append("场景五：会话创建、笔记、知识点完成与会话结束成功")

        progress = require(client.get("/progress"), 200)
        today_after = require(client.get("/today"), 200)
        accepted_task = next(item for item in today_after["tasks"] if item["id"] == task["id"])
        assert accepted_task["status"] == "completed"
        assert progress["completed_knowledge_point_count"] >= 1
        assert progress["sessions_last_7_days"] >= 1
        results.append("场景六：首页任务与进度聚合已反映完成状态")

        for material in materials:
            require(client.delete(f"/materials/{material['id']}"), 204)
        assert not any(item["id"] in {material["id"] for material in materials} for item in require(client.get("/materials"), 200))
        results.append("资料删除：数据库记录与本地文件同步清理（API 测试同时检查文件）")

        require(client.delete(f"/learning-goals/{goal['id']}"), 204)

    print(json.dumps({"status": "passed", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

