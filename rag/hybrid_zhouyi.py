
import json
import re
import argparse
from pathlib import Path
from rag.runtime_data import knowledge_path

from rag.exact_zhouyi import detect_hexagram, detect_line
from rag.search_zhouyi import search_zhouyi

ROOT = Path(__file__).resolve().parents[1]
CHUNKS_FILE = knowledge_path("data/chunks/zhouyi_index_ready.jsonl")


def normalize(text):
    """统一检索文本格式，保留中文和英文数字。"""
    return re.sub(
        r"[^a-zA-Z0-9\u4e00-\u9fff]",
        "",
        text
    ).lower()


def load_chunks():
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


CHUNKS = load_chunks()
CHUNK_MAP = {item["id"]: item for item in CHUNKS}


def lexical_score(query, text):
    """
    使用中文连续字符匹配作为第一版词法检索。
    这不是BM25，之后可以继续升级。
    """
    q = normalize(query)
    t = normalize(text)

    if not q or not t:
        return 0.0

    # 去掉常见提问开头，减少无关匹配
    for prefix in (
        "为什么", "如何理解", "如何解释",
        "是什么意思", "请解释", "请问"
    ):
        q = q.replace(prefix, "")

    if len(q) < 3:
        return 0.0

    score = 0.0

    # 长短语优先，兼顾OCR断行
    for n in (10, 8, 6, 4, 3):
        if len(q) < n:
            continue

        grams = {
            q[i:i+n]
            for i in range(len(q)-n+1)
        }

        hits = sum(gram in t for gram in grams)
        score += hits * (n ** 2)

    return score


def lexical_search(query, top_k=25):
    ranked = []

    for record in CHUNKS:
        score = lexical_score(query, record["text"])

        if score > 0:
            ranked.append((score, record))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [record for _, record in ranked[:top_k]]


def hybrid_search(query, top_k=5):
    if not query.strip():
        return []

    hexagram = detect_hexagram(query)
    line_name, line_number = detect_line(query)

    # 1. 词法搜索：本地，不消耗API额度
    lexical = lexical_search(query, top_k=30)

    # 2. 语义搜索：复用现有BGE-M3向量集合
    semantic = search_zhouyi(query, top_k=30)

    # 3. Reciprocal Rank Fusion
    scores = {}
    sources = {}

    def add_score(chunk_id, rank, method):
        scores[chunk_id] = (
            scores.get(chunk_id, 0.0)
            + 1.0 / (60 + rank)
        )
        sources.setdefault(chunk_id, set()).add(method)

    for rank, record in enumerate(lexical, 1):
        add_score(record["id"], rank, "lexical")

    for rank, record in enumerate(semantic, 1):
        add_score(record["id"], rank, "semantic")

    # 4. 卦名、爻位加权
    # 不把不确定的边界页直接归入某卦。
    for chunk_id in scores:
        record = CHUNK_MAP.get(chunk_id)

        if record is None:
            continue

        matched_name = record.get("hexagram_name")

        if hexagram is not None:
            target_name = hexagram["name"]

            if matched_name == target_name:
                scores[chunk_id] *= 1.8
            elif matched_name is not None:
                # 明确属于其他卦的片段降低优先级
                scores[chunk_id] *= 0.6

        if line_name:
            # 只有确实包含爻名才加分
            if line_name in record["text"]:
                scores[chunk_id] *= 1.3

    ranked_ids = sorted(
        scores,
        key=lambda chunk_id: scores[chunk_id],
        reverse=True
    )

    output = []

    for chunk_id in ranked_ids[:top_k]:
        record = CHUNK_MAP.get(chunk_id)

        if record is None:
            continue

        output.append({
            **record,
            "hybrid_score": scores[chunk_id],
            "retrieval_methods": sorted(sources[chunk_id])
        })

    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    question = args.question
    hexagram = detect_hexagram(question)
    line_name, _ = detect_line(question)

    print("===== HYBRID ZHOUYI SEARCH =====")
    print("问题:", question)
    print(
        "识别卦名:",
        hexagram["name"] if hexagram else "无明确卦名"
    )
    print("识别爻位:", line_name or "未指定")

    results = hybrid_search(
        question,
        top_k=args.top_k
    )

    for i, item in enumerate(results, 1):
        print("\n" + "=" * 60)
        print("RESULT:", i)
        print("ID:", item["id"])
        print("卦名:", item.get("hexagram_name") or "未核实")
        print("PDF页码:", item["pdf_page"])
        print("边界页:", item["boundary_page"])
        print(
            "检索方式:",
            ", ".join(item["retrieval_methods"])
        )
        print(
            "Hybrid score:",
            round(item["hybrid_score"], 6)
        )
        print("内容:")
        print(item["text"][:800])


if __name__ == "__main__":
    main()
