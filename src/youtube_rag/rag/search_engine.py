from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from ..core import config
from ..core.models import AnswerResult, RetrievedSource, build_context_block
from .llm_client import LLMChatClient

_G_MIN_SCORE: float | None = None
DEFAULT_COLLECTION_NAME = "youtube_transcript_chunks"

ANSWER_SYSTEM_PROMPT = (
    "你是“政经鲁社长频道解读助手”。你的任务是基于该频道的检索内容，"
    "总结鲁社长在节目中的分析、判断和态度。\n"
    "这些检索内容默认都来自鲁社长频道，因此除非上下文明确表明是在引用、转述或描述他人观点，"
    "否则应视为鲁社长本人的表达、分析框架或态度线索。\n"
    "当用户问“鲁社长如何评价某人/某事”时，允许你综合多个检索片段，归纳鲁社长的整体看法；"
    "不要求必须找到一句完全直接、完整的原话才可以回答。\n"
    "但你仍然只能依据检索上下文作答，禁止引入上下文外事实，禁止编造。\n"
    "如果证据太弱，无法形成稳定判断，才输出：信息不足，无法从已检索内容确定。\n"
    "表达风格要接近鲁社长的直播总结：直白、结论先行、逻辑清楚、少空话。\n"
    "允许使用拟人口吻，但不要假装你本人就是鲁社长，不要编造个人经历。\n"
    "输出必须结构化，便于读者快速理解。"
)


def get_collection(collection_name: str = DEFAULT_COLLECTION_NAME) -> Any:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    import chromadb

    chroma_path = Path(config.CHROMA_DB_DIR)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_path))
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=config.LOCAL_EMBEDDING_MODEL)

    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def retrieve_sources(
    collection: Any,
    query: str,
    top_k: int,
    min_score: float | None,
) -> list[RetrievedSource]:
    query_result = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    documents = query_result.get("documents", [[]])[0]
    metadatas = query_result.get("metadatas", [[]])[0]
    distances = query_result.get("distances", [[]])[0] if query_result.get("distances") else []

    sources: list[RetrievedSource] = []

    for idx, chunk_text in enumerate(documents):
        metadata = metadatas[idx] if idx < len(metadatas) else {}
        distance = distances[idx] if idx < len(distances) else None

        score = None
        if distance is not None:
            score = 1.0 - float(distance)
            if min_score is not None and score < min_score:
                continue

        video_id = str(metadata.get("video_id", ""))
        start_sec = float(metadata.get("start_sec", 0.0))
        sources.append(
            RetrievedSource(
                video_id=video_id,
                title=str(metadata.get("title", "")),
                start_sec=start_sec,
                end_sec=float(metadata.get("end_sec", start_sec)),
                chunk_text=str(chunk_text),
                youtube_url=str(metadata.get("youtube_url", "")),
                timestamp_url=f"https://www.youtube.com/watch?v={video_id}&t={int(start_sec)}s",
                score=score,
            )
        )

    return sources


def build_user_prompt(query: str, context_block: str) -> str:
    return (
        "【理解规则】\n"
        "1) 检索上下文默认代表鲁社长频道内容本身。\n"
        "2) 如果用户问“鲁社长如何评价X”，应优先总结鲁社长在多个片段中体现出的总体态度与判断。\n"
        "3) 可以做跨片段归纳，但必须有来源支撑；不能脱离文本自由发挥。\n"
        "4) 只有在上下文确实没有足够线索形成总体评价时，才输出：信息不足，无法从已检索内容确定。\n\n"
        "请基于“政经鲁社长频道”的检索上下文回答问题。\n"
        "口吻要求：像鲁社长做直播复盘，结论清楚、语言自然、有判断力。\n"
        "但必须克制，不夸张，不煽动。\n\n"
        "【输出格式（必须严格遵守）】\n"
        "## 一句话总判断\n"
        "- 用1句话先讲结论。\n\n"
        "## 要点总结\n"
        "- 3~5条，每条尽量短句，读者一眼看懂。\n\n"
        "## 展开分析\n"
        "- 按逻辑分点解释。\n"
        "- 每一点后面标注对应来源，如 [Source 1]。\n\n"
        "## 依据来源\n"
        "- 列出你真正使用过的 Source 编号，并说明它支撑了哪条结论。\n\n"
        "【硬性约束】\n"
        "1) 只能使用检索上下文，不得补充外部知识。\n"
        "2) 不得编造人物、时间、数字、事件。\n"
        "3) 若无法确定，必须原样输出：信息不足，无法从已检索内容确定。\n\n"
        f"用户问题：{query}\n\n"
        f"检索上下文：\n{context_block}"
    )


def ask_question(query: str, top_k: int = 5) -> dict[str, object]:
    collection = get_collection()
    sources = retrieve_sources(collection=collection, query=query, top_k=top_k, min_score=_G_MIN_SCORE)
    if not sources:
        return AnswerResult(answer_text="信息不足，无法从已检索内容确定", sources=[]).to_dict()

    provider = config.LLM_PROVIDER.lower()
    llm_client = LLMChatClient(provider=provider)
    logging.info("LLM provider=%s model=%s", provider, llm_client.active_model())

    answer_text = llm_client.generate(
        system_prompt=ANSWER_SYSTEM_PROMPT,
        user_prompt=build_user_prompt(query=query, context_block=build_context_block(sources)),
        temperature=0.2,
    )
    return AnswerResult(answer_text=answer_text, sources=sources).to_dict()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query indexed transcript chunks and generate grounded answer")
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    global _G_MIN_SCORE
    _G_MIN_SCORE = args.min_score

    result = ask_question(query=args.query, top_k=args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
