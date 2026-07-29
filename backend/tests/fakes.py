from hashlib import sha256

import numpy as np

from app.services.embedding.base import EmbeddingError, FloatMatrix
from app.services.llm.base import LLMUsage, StructuredLLMResult


class FakeEmbedder:
    model_name = "fake/bge-m3"
    model_revision = "test"
    normalized = True

    def __init__(self, dimension: int = 16):
        self._dimension = dimension
        self.calls = 0

    @property
    def dimension(self) -> int:
        return self._dimension

    def _vector(self, text: str) -> np.ndarray:
        if not text.strip():
            raise EmbeddingError("不能对空文本生成 Embedding。")
        vector = np.zeros(self.dimension, dtype=np.float32)
        compact = "".join(text.lower().split())
        for index, character in enumerate(compact):
            digest = sha256(f"{index % 3}:{character}".encode("utf-8")).digest()
            vector[int.from_bytes(digest[:2], "little") % self.dimension] += 1.0
        norm = np.linalg.norm(vector)
        if norm:
            vector /= norm
        return vector

    def embed_documents(self, texts: list[str]) -> FloatMatrix:
        self.calls += 1
        return np.stack([self._vector(text) for text in texts]).astype(np.float32)

    def embed_query(self, query: str) -> FloatMatrix:
        self.calls += 1
        return self._vector(query).reshape(1, -1).astype(np.float32)


class FakeLearningLLM:
    model_name = "fake-learning-llm"

    def __init__(self):
        self.calls = 0
        self.temperatures: list[float | None] = []

    def generate_structured(
        self, *, messages, schema, temperature=None, max_output_tokens=None
    ):
        self.calls += 1
        self.temperatures.append(temperature)
        if schema.__name__ == "GeneratedActivity":
            value = schema.model_validate(
                {
                    "title": "MCP 可靠练习",
                    "description": "仅基于本地资料生成",
                    "questions": [
                        {
                            "question_type": "single_choice",
                            "stem": "MCP 工具调用由哪一方主动发起？",
                            "options": [
                                {"id": "A", "text": "模型"},
                                {"id": "B", "text": "资源文件"},
                                {"id": "C", "text": "传输层"},
                            ],
                            "correct_answer": ["A"],
                            "reference_answer": None,
                            "grading_rubric": None,
                            "explanation": "资料说明工具由模型主动调用。",
                            "difficulty": "easy",
                            "points": 2,
                            "cited_source_ids": ["S1"],
                        },
                        {
                            "question_type": "multiple_choice",
                            "stem": "资料明确列出的 MCP 核心原语有哪些？",
                            "options": [
                                {"id": "A", "text": "Tools"},
                                {"id": "B", "text": "Resources"},
                                {"id": "C", "text": "Prompts"},
                                {"id": "D", "text": "电子邮件"},
                            ],
                            "correct_answer": ["A", "B", "C"],
                            "reference_answer": None,
                            "grading_rubric": None,
                            "explanation": "资料列出 Tools、Resources 和 Prompts。",
                            "difficulty": "medium",
                            "points": 3,
                            "cited_source_ids": ["S1"],
                        },
                        {
                            "question_type": "true_false",
                            "stem": "MCP Resources 是应用控制的上下文数据。",
                            "options": None,
                            "correct_answer": [True],
                            "reference_answer": None,
                            "grading_rubric": None,
                            "explanation": "资料将 Resources 定义为应用控制的上下文数据。",
                            "difficulty": "easy",
                            "points": 2,
                            "cited_source_ids": ["S1"],
                        },
                        {
                            "question_type": "short_answer",
                            "stem": "简述 Tools 与 Resources 的控制方向差异。",
                            "options": None,
                            "correct_answer": None,
                            "reference_answer": "Tools 由模型主动调用，Resources 由应用控制并提供上下文。",
                            "grading_rubric": [
                                {
                                    "criterion": "工具控制方向",
                                    "points": 2,
                                    "required_concepts": ["模型主动调用"],
                                },
                                {
                                    "criterion": "资源控制方向",
                                    "points": 2,
                                    "required_concepts": ["应用控制", "上下文"],
                                },
                            ],
                            "explanation": "两者的关键差异是控制方向。",
                            "difficulty": "medium",
                            "points": 4,
                            "cited_source_ids": ["S1"],
                        },
                    ],
                }
            )
        elif schema.__name__ == "ShortAnswerGrade":
            content = messages[-1]["content"]
            text = content.split("<untrusted_user_answer>\n", 1)[-1].split(
                "\n</untrusted_user_answer>", 1
            )[0]
            full = "模型主动" in text and "应用控制" in text
            if full:
                matched = ["R1", "R2"]
                missing = []
                points = 4
                feedback = "两项控制方向均说明准确。"
            else:
                matched = []
                missing = ["R1", "R2"]
                points = 0
                feedback = "尚未说明两项控制方向。"
            value = schema.model_validate(
                {
                    "earned_points": points,
                    "matched_items": matched,
                    "missing_items": missing,
                    "feedback": feedback,
                    "confidence": 0.95,
                    "answer_supported": full,
                }
            )
        else:
            raise AssertionError(f"unexpected schema {schema.__name__}")
        return StructuredLLMResult(
            value=value,
            usage=LLMUsage(input_tokens=100, output_tokens=50),
            model=self.model_name,
            latency_ms=5,
        )
