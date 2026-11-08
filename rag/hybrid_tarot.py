"""Multi-source exact, lexical, BM25, and vector Tarot retrieval."""

from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from rag.tarot_sources import load_source_chunks, load_source_registry
from rag.runtime_data import chroma_path

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MODEL = "BAAI/bge-m3"


def tokenize(text: str) -> list[str]:
    latin = re.findall(r"[a-z0-9]+", text.lower())
    chinese_runs = re.findall(r"[\u3400-\u9fff]+", text)
    chinese = [
        run[index:index + 2]
        for run in chinese_runs
        for index in range(max(1, len(run) - 1))
    ]
    return latin + chinese


def bm25_scores(query: str, documents: list[str]) -> list[float]:
    if not documents:
        return []
    tokenized = [tokenize(document) for document in documents]
    query_tokens = tokenize(query)
    average_length = sum(len(tokens) for tokens in tokenized) / max(len(tokenized), 1)
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
    scores: list[float] = []
    k1, b = 1.5, 0.75
    for tokens in tokenized:
        frequencies = Counter(tokens)
        score = 0.0
        for term in query_tokens:
            df = document_frequency.get(term, 0)
            if not df:
                continue
            inverse = math.log(1 + (len(tokenized) - df + 0.5) / (df + 0.5))
            frequency = frequencies.get(term, 0)
            denominator = frequency + k1 * (
                1 - b + b * len(tokens) / max(average_length, 1)
            )
            score += inverse * frequency * (k1 + 1) / max(denominator, 1e-9)
        scores.append(score)
    return scores


def embed_query(query: str) -> list[float]:
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is missing from the project environment")
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.siliconflow.cn/v1",
        timeout=60.0,
        max_retries=3,
    )
    response = client.embeddings.create(model=MODEL, input=query)
    vector = response.data[0].embedding
    if len(vector) != 1024:
        raise ValueError(f"Unexpected embedding dimension: {len(vector)}")
    return vector


def _local_candidates(
    source: dict[str, Any], card_id: str
) -> list[dict[str, Any]]:
    chunks = load_source_chunks(source["chunks_path"])
    if source["source_id"] == "greer_tarot_reversals":
        direct = [item for item in chunks if item.get("card_id") == card_id]
        general = [item for item in chunks if not item.get("card_id")]
        return direct + general
    return chunks


def _canonical_item(
    source: dict[str, Any], chunk: dict[str, Any], method: str, raw_score: float
) -> dict[str, Any]:
    chunk_id = chunk.get("chunk_id") or chunk.get("id")
    page_start = chunk.get("pdf_page_start", chunk.get("pdf_page"))
    page_end = chunk.get("pdf_page_end", page_start)
    return {
        "key": f"{source['source_id']}:{chunk_id}",
        "chunk_id": chunk_id,
        "source_id": source["source_id"],
        "title": source["title"],
        "author": source["author"],
        "text": chunk["text"],
        "card_id": chunk.get("card_id"),
        "card_name": chunk.get("card_name"),
        "orientation_context": chunk.get("orientation_context", "general"),
        "section_title": chunk.get("section_title"),
        "pdf_page_start": page_start,
        "pdf_page_end": page_end,
        "method": method,
        "raw_score": raw_score,
    }


def _local_rankings(
    query: str, card_name: str, card_id: str, orientation: str
) -> dict[str, list[dict[str, Any]]]:
    rankings: dict[str, list[dict[str, Any]]] = {"exact_phrase": [], "bm25": []}
    for source in load_source_registry():
        candidates = _local_candidates(source, card_id)
        phrase = card_name.lower()
        exact = [
            _canonical_item(source, item, "exact_phrase", 1.0)
            for item in candidates
            if phrase in item["text"].lower()
        ]
        exact.sort(
            key=lambda item: (
                item.get("card_id") == card_id,
                item.get("orientation_context") == orientation,
            ),
            reverse=True,
        )
        rankings["exact_phrase"].extend(exact[:8])
        scores = bm25_scores(query, [item["text"] for item in candidates])
        ranked = sorted(
            zip(candidates, scores), key=lambda pair: pair[1], reverse=True
        )
        rankings["bm25"].extend(
            _canonical_item(source, item, "bm25", score)
            for item, score in ranked[:8]
            if score > 0
        )
    return rankings


def _vector_ranking(
    query_vector: list[float], card_id: str, per_collection: int = 6
) -> list[dict[str, Any]]:
    db = chromadb.PersistentClient(path=str(chroma_path()))
    available = {collection.name for collection in db.list_collections()}
    output: list[dict[str, Any]] = []
    for source in load_source_registry():
        collection_name = source.get("collection")
        if not collection_name or collection_name not in available:
            continue
        collection = db.get_collection(collection_name)
        valid_chunk_ids: set[str] | None = None
        if source["source_id"] == "greer_tarot_reversals":
            valid_chunk_ids = {
                item["chunk_id"] for item in load_source_chunks(source["chunks_path"])
            }
        kwargs: dict[str, Any] = {}
        if source["source_id"] == "greer_tarot_reversals" and card_id:
            kwargs["where"] = {"card_id": card_id}
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=min(per_collection, collection.count()),
            include=["documents", "metadatas", "distances"],
            **kwargs,
        )
        for index, chunk_id in enumerate(results["ids"][0]):
            if valid_chunk_ids is not None and chunk_id not in valid_chunk_ids:
                continue
            metadata = results["metadatas"][0][index] or {}
            chunk = {
                "chunk_id": chunk_id,
                "text": results["documents"][0][index],
                **metadata,
            }
            distance = float(results["distances"][0][index])
            item = _canonical_item(source, chunk, "vector", 1.0 - distance)
            item["distance"] = distance
            output.append(item)
    return sorted(output, key=lambda item: item.get("distance", 99.0))


def reciprocal_rank_fusion(
    rankings: dict[str, list[dict[str, Any]]],
    card_id: str,
    orientation: str,
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: defaultdict[str, float] = defaultdict(float)
    methods: defaultdict[str, set[str]] = defaultdict(set)
    items: dict[str, dict[str, Any]] = {}
    for method, ranking in rankings.items():
        seen: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            key = item["key"]
            if key in seen:
                continue
            seen.add(key)
            scores[key] += 1.0 / (k + rank)
            methods[key].add(method)
            items[key] = item
    for key, item in items.items():
        if item.get("card_id") == card_id:
            scores[key] *= 2.4
        if item.get("orientation_context") == orientation:
            scores[key] *= 1.35
        if item.get("orientation_context") == "general":
            scores[key] *= 0.92
    ranked = sorted(items.values(), key=lambda item: scores[item["key"]], reverse=True)
    for item in ranked:
        item["rrf_score"] = scores[item["key"]]
        item["retrieval_methods"] = sorted(methods[item["key"]])
    return ranked


def _balanced_top(ranked: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    if top_k <= 0:
        return []
    selected: list[dict[str, Any]] = ranked[:1]
    for source in load_source_registry():
        candidate = next(
            (item for item in ranked if item["source_id"] == source["source_id"]),
            None,
        )
        if candidate and candidate not in selected and len(selected) < top_k:
            selected.append(candidate)
    for item in ranked:
        if len(selected) >= top_k:
            break
        if item not in selected:
            selected.append(item)
    return selected


def retrieve_for_card(
    question: str,
    card_id: str,
    card_name: str,
    orientation: str,
    position: str,
    top_k: int = 3,
    include_vectors: bool = True,
) -> list[dict[str, Any]]:
    query = (
        f"{question}\nCard: {card_name}. Orientation: {orientation}. "
        f"Spread position: {position}. Tarot interpretation and symbolism."
    )
    rankings = _local_rankings(query, card_name, card_id, orientation)
    if include_vectors:
        rankings["vector"] = _vector_ranking(embed_query(query), card_id)
    fused = reciprocal_rank_fusion(rankings, card_id, orientation)
    selected = _balanced_top(fused, top_k)
    output: list[dict[str, Any]] = []
    for item in selected:
        output.append({
            "id": f"VECTOR_{item['source_id'].upper()}_{item['chunk_id']}",
            "source_id": item["source_id"],
            "title": item["title"],
            "author": item["author"],
            "card_id": item.get("card_id"),
            "card_name": item.get("card_name"),
            "orientation_context": item.get("orientation_context"),
            "position": position,
            "page": item["pdf_page_start"],
            "pages": list(range(item["pdf_page_start"], item["pdf_page_end"] + 1)),
            "text": item["text"][:1800],
            "distance": item.get("distance"),
            "score": item["rrf_score"],
            "retrieval_methods": item["retrieval_methods"],
        })
    return output


def search_multi_source(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Compatibility search when no selected card metadata is available."""
    vector = embed_query(query)
    ranking = _vector_ranking(vector, card_id="", per_collection=max(top_k, 5))
    return [
        {
            "id": item["chunk_id"],
            "text": item["text"],
            "metadata": {
                "source_id": item["source_id"],
                "title": item["title"],
                "author": item["author"],
                "pdf_page": item["pdf_page_start"],
                "pdf_page_end": item["pdf_page_end"],
                "card_id": item.get("card_id"),
                "orientation_context": item.get("orientation_context"),
            },
            "distance": item.get("distance", 1.0),
        }
        for item in ranking[:top_k]
    ]
