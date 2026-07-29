"""Evaluate V4 generation, grading, and wrong-answer behavior through HTTP."""

from argparse import ArgumentParser
import json
import os
from pathlib import Path
import subprocess
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx

from acceptance_v3 import ALEMBIC, BACKEND, live_backend, require
from acceptance_v4 import create_learning_context, upload_fixtures


ROOT = Path(__file__).resolve().parents[1]
GENERATION_DATASET = ROOT / "evals" / "activity_generation_dataset.json"
GRADING_DATASET = ROOT / "evals" / "grading_dataset.json"


def answer_key_valid(question: dict) -> bool:
    kind = question["question_type"]
    answer = question["correct_answer"]
    options = question["options"] or []
    option_ids = {item["id"] for item in options}
    if kind == "single_choice":
        return bool(answer) and len(answer) == 1 and answer[0] in option_ids
    if kind == "multiple_choice":
        return (
            bool(answer)
            and len(answer) >= 2
            and len(answer) < len(options)
            and set(answer).issubset(option_ids)
        )
    if kind == "true_false":
        return (
            bool(answer)
            and len(answer) == 1
            and type(answer[0]) is bool
        )
    return bool(question["reference_answer"])


def rubric_valid(question: dict) -> bool:
    if question["question_type"] != "short_answer":
        return True
    rubric = question["grading_rubric"] or []
    return (
        bool(rubric)
        and all(
            item["criterion"]
            and item["required_concepts"]
            and item["points"] > 0
            for item in rubric
        )
        and abs(sum(item["points"] for item in rubric) - question["points"]) < 1e-6
    )


def normalized_stem(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def correct_answer_payload(question: dict) -> dict:
    if question["question_type"] == "short_answer":
        return {
            "question_id": question["id"],
            "answer_text": question["reference_answer"],
        }
    return {
        "question_id": question["id"],
        "answer": question["correct_answer"],
    }


def evaluate(base_url: str) -> dict:
    generation_cases = json.loads(GENERATION_DATASET.read_text(encoding="utf-8"))
    grading_cases = json.loads(GRADING_DATASET.read_text(encoding="utf-8"))
    generation_results = []
    grading_results = []
    objective_predictions: list[bool] = []
    wrong_creation_checks: list[bool] = []
    wrong_dedup_checks: list[bool] = []
    review_resolution_checks: list[bool] = []
    with httpx.Client(base_url=base_url, timeout=600) as client:
        status_data = require(client.get("/rag/status"), 200)
        if not status_data["llm_configured"]:
            raise RuntimeError("LLM 尚未配置，不能执行真实 V4 评测")
        materials = upload_fixtures(client)
        material_by_name = {
            item["original_filename"]: item for item in materials
        }
        course, point = create_learning_context(client)
        generated_drafts: list[dict] = []
        for case in generation_cases:
            selected = [material_by_name[name]["id"] for name in case["materials"]]
            started = perf_counter()
            response = client.post(
                "/learning-activities/generate",
                json={
                    "title": case["title"],
                    "course_id": course["id"],
                    "knowledge_point_id": point["id"],
                    "material_ids": selected,
                    "question_types": case["question_types"],
                    "question_count": case["question_count"],
                    "difficulty": case["difficulty"],
                    "request_id": f"v4-eval-generation-{case['id']}",
                },
            )
            latency_ms = round((perf_counter() - started) * 1000, 2)
            if response.status_code != 201:
                generation_results.append(
                    {
                        "id": case["id"],
                        "valid_schema": False,
                        "http_status": response.status_code,
                        "latency_ms": latency_ms,
                    }
                )
                continue
            draft = response.json()
            generated_drafts.append(draft)
            questions = draft["questions"]
            normalized = [normalized_stem(item["stem"]) for item in questions]
            objective_answers = [
                item["correct_answer"]
                for item in questions
                if item["question_type"] != "short_answer"
            ]
            injection_resistant = True
            if case.get("contains_prompt_injection_fixture"):
                injection_resistant = not (
                    objective_answers
                    and all(answer == ["A"] for answer in objective_answers)
                )
            generation_results.append(
                {
                    "id": case["id"],
                    "valid_schema": True,
                    "source_valid": all(
                        source["material_id"] in selected
                        for question in questions
                        for source in question["sources"]
                    ),
                    "answer_key_valid": all(
                        answer_key_valid(question) for question in questions
                    ),
                    "rubric_valid": all(
                        rubric_valid(question) for question in questions
                    ),
                    "duplicate_count": len(normalized) - len(set(normalized)),
                    "count_complete": len(questions) == case["question_count"],
                    "prompt_injection_resistant": injection_resistant,
                    "latency_ms": latency_ms,
                }
            )
        if not generated_drafts:
            raise RuntimeError("所有题目生成评测均失败")

        draft = next(
            (
                item
                for item in generated_drafts
                if any(
                    question["question_type"] == "short_answer"
                    for question in item["questions"]
                )
            ),
            generated_drafts[0],
        )
        published = require(
            client.post(f"/learning-activities/{draft['id']}/publish"), 200
        )
        snapshot = {question["id"]: question for question in draft["questions"]}
        attempt = require(
            client.post(
                f"/learning-activities/{published['id']}/attempts", json={}
            ),
            201,
        )
        full_result = require(
            client.post(
                f"/quiz-attempts/{attempt['id']}/submit",
                json={
                    "request_id": "v4-eval-objective-correct",
                    "answers": [
                        correct_answer_payload(snapshot[item["id"]])
                        for item in attempt["questions"]
                    ],
                },
            ),
            200,
        )
        for answer in full_result["answers"]:
            if answer["question_type"] != "short_answer":
                objective_predictions.append(answer["is_correct"] is True)

        objective_question = next(
            item
            for item in attempt["questions"]
            if item["question_type"] != "short_answer"
        )
        original = snapshot[objective_question["id"]]
        if objective_question["question_type"] == "true_false":
            wrong_value = [not original["correct_answer"][0]]
        else:
            correct_ids = set(original["correct_answer"])
            wrong_value = [
                next(
                    option["id"]
                    for option in original["options"]
                    if option["id"] not in correct_ids
                )
            ]
        wrong_attempt = require(
            client.post(
                f"/learning-activities/{published['id']}/attempts", json={}
            ),
            201,
        )
        wrong_answers = []
        for item in wrong_attempt["questions"]:
            if item["id"] == objective_question["id"]:
                wrong_answers.append(
                    {"question_id": item["id"], "answer": wrong_value}
                )
            else:
                wrong_answers.append(correct_answer_payload(snapshot[item["id"]]))
        wrong_result = require(
            client.post(
                f"/quiz-attempts/{wrong_attempt['id']}/submit",
                json={
                    "request_id": "v4-eval-objective-wrong",
                    "answers": wrong_answers,
                },
            ),
            200,
        )
        wrong_grade = next(
            answer
            for answer in wrong_result["answers"]
            if answer["question_id"] == objective_question["id"]
        )
        objective_predictions.append(wrong_grade["is_correct"] is False)
        wrong_page = require(client.get("/wrong-answers"), 200)
        matching = [
            item
            for item in wrong_page["items"]
            if item["attempt_id"] == wrong_attempt["id"]
            and item["question_id"] == objective_question["id"]
        ]
        wrong_creation_checks.append(len(matching) == 1)
        wrong_page_replay = require(client.get("/wrong-answers"), 200)
        matching_replay = [
            item
            for item in wrong_page_replay["items"]
            if item["attempt_id"] == wrong_attempt["id"]
            and item["question_id"] == objective_question["id"]
        ]
        wrong_dedup_checks.append(len(matching_replay) == 1)
        if matching:
            review = require(
                client.post(
                    "/wrong-answers/review",
                    json={
                        "wrong_answer_ids": [matching[0]["id"]],
                        "request_id": "v4-eval-review",
                    },
                ),
                201,
            )
            review_payload = correct_answer_payload(original)
            review_payload["question_id"] = review["questions"][0]["id"]
            require(
                client.post(
                    f"/quiz-attempts/{review['id']}/submit",
                    json={
                        "request_id": "v4-eval-review-submit",
                        "answers": [review_payload],
                    },
                ),
                200,
            )
            reviewed = require(
                client.get(f"/wrong-answers/{matching[0]['id']}"), 200
            )
            review_resolution_checks.append(
                reviewed["status"] == "resolved"
                and reviewed["review_count"] == 1
            )

        short_question = next(
            question
            for question in draft["questions"]
            if question["question_type"] == "short_answer"
        )
        rubric_criteria = {
            item["criterion"] for item in short_question["grading_rubric"]
        }
        for case in grading_cases:
            grading_attempt = require(
                client.post(
                    f"/learning-activities/{published['id']}/attempts", json={}
                ),
                201,
            )
            answers = []
            for item in grading_attempt["questions"]:
                question = snapshot[item["id"]]
                if item["id"] != short_question["id"]:
                    answers.append(correct_answer_payload(question))
                    continue
                strategy = case["answer_strategy"]
                if strategy == "use_generated_reference_answer":
                    answer_text = short_question["reference_answer"]
                elif strategy == "empty":
                    answer_text = ""
                else:
                    answer_text = strategy.removeprefix("literal:")
                answers.append(
                    {"question_id": item["id"], "answer_text": answer_text}
                )
            started = perf_counter()
            response = client.post(
                f"/quiz-attempts/{grading_attempt['id']}/submit",
                json={
                    "request_id": f"v4-eval-grade-{case['id']}",
                    "answers": answers,
                },
            )
            latency_ms = round((perf_counter() - started) * 1000, 2)
            if response.status_code != 200:
                grading_results.append(
                    {
                        "id": case["id"],
                        "valid_grade": False,
                        "latency_ms": latency_ms,
                    }
                )
                continue
            result = response.json()
            grade = next(
                answer
                for answer in result["answers"]
                if answer["question_id"] == short_question["id"]
            )
            ratio = (
                grade["earned_points"] / grade["max_points"]
                if grade["earned_points"] is not None
                else None
            )
            expected_kind = case["expected_matched_items"]
            matched = set(grade["matched_rubric_items"] or [])
            expected_match = (
                matched == rubric_criteria
                if expected_kind == "all"
                else not matched
            )
            grading_results.append(
                {
                    "id": case["id"],
                    "valid_grade": grade["grading_status"] == "completed",
                    "score_ratio": ratio,
                    "within_tolerance": (
                        ratio is not None
                        and case["expected_min_ratio"]
                        <= ratio
                        <= case["expected_max_ratio"]
                    ),
                    "score_error": (
                        0.0
                        if ratio is not None
                        and case["expected_min_ratio"]
                        <= ratio
                        <= case["expected_max_ratio"]
                        else (
                            min(
                                abs((ratio or 0.0) - case["expected_min_ratio"]),
                                abs((ratio or 0.0) - case["expected_max_ratio"]),
                            )
                        )
                    ),
                    "rubric_match": expected_match,
                    "latency_ms": latency_ms,
                }
            )

    valid_generations = [
        item for item in generation_results if item["valid_schema"]
    ]
    valid_grades = [item for item in grading_results if item["valid_grade"]]
    duplicate_total = sum(
        item.get("duplicate_count", 0) for item in valid_generations
    )
    question_total = sum(
        generation_cases[index]["question_count"]
        for index, item in enumerate(generation_results)
        if item["valid_schema"]
    )
    score_errors = [item["score_error"] for item in valid_grades]
    metrics = {
        "schema_validity_rate": len(valid_generations) / len(generation_results),
        "question_source_validity_rate": mean(
            float(item["source_valid"]) for item in valid_generations
        ),
        "answer_key_validity_rate": mean(
            float(item["answer_key_valid"]) for item in valid_generations
        ),
        "rubric_validity_rate": mean(
            float(item["rubric_valid"]) for item in valid_generations
        ),
        "duplicate_question_rate": duplicate_total / max(question_total, 1),
        "requested_count_completion_rate": mean(
            float(item["count_complete"]) for item in valid_generations
        ),
        "prompt_injection_resistance_rate": mean(
            float(item["prompt_injection_resistant"])
            for item in valid_generations
        ),
        "generation_failure_rate": 1
        - len(valid_generations) / len(generation_results),
        "average_generation_latency_ms": mean(
            item["latency_ms"] for item in generation_results
        ),
        "objective_grading_accuracy": mean(
            float(item) for item in objective_predictions
        ),
        "short_answer_score_mae": mean(score_errors)
        if score_errors
        else 0.0,
        "short_answer_within_tolerance_rate": mean(
            float(item["within_tolerance"]) for item in valid_grades
        ),
        "rubric_match_accuracy": mean(
            float(item["rubric_match"]) for item in valid_grades
        ),
        "invalid_grade_rate": 1
        - len(valid_grades) / len(grading_results),
        "grading_failure_rate": 1
        - len(valid_grades) / len(grading_results),
        "average_grading_latency_ms": mean(
            item["latency_ms"] for item in grading_results
        ),
        "wrong_answer_creation_accuracy": mean(
            float(item) for item in wrong_creation_checks
        ),
        "wrong_answer_deduplication_rate": mean(
            float(item) for item in wrong_dedup_checks
        ),
        "review_resolution_accuracy": mean(
            float(item) for item in review_resolution_checks
        ),
    }
    return {
        "status": "completed",
        "scope_note": (
            "小型人工可核验数据集仅用于 V4 回归，不代表通用教学质量或普适评分准确率。"
        ),
        "metrics": metrics,
        "generation_cases": generation_results,
        "grading_cases": grading_results,
    }


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--port", type=int, default=8015)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.isolated:
        with TemporaryDirectory(
            prefix="personal-learning-v4-evaluation-",
            ignore_cleanup_errors=True,
        ) as temp:
            temp_dir = Path(temp)
            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": (
                        f"sqlite:///{(temp_dir / 'evaluation.sqlite3').as_posix()}"
                    ),
                    "UPLOAD_DIR": str(temp_dir / "uploads"),
                    "FAISS_INDEX_PATH": str(temp_dir / "materials.faiss"),
                    "FAISS_MANIFEST_PATH": str(
                        temp_dir / "materials.faiss.manifest.json"
                    ),
                    "EMBEDDING_MODEL_NAME": "BAAI/bge-m3",
                    "EMBEDDING_MODEL_REVISION": "local-cache",
                    "EMBEDDING_LOCAL_FILES_ONLY": "true",
                    "EMBEDDING_DEVICE": "cpu",
                    "EMBEDDING_NORMALIZE": "true",
                    "APP_VERSION": "4.0.0",
                }
            )
            subprocess.run(
                [str(ALEMBIC), "upgrade", "head"],
                cwd=BACKEND,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            with live_backend(
                port=args.port,
                environment=environment,
                log_path=temp_dir / "backend.log",
            ) as base_url:
                report = evaluate(base_url)
    else:
        report = evaluate(args.base_url)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
