
# rag/build_index.py

import os
import json
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL = "BAAI/bge-m3"
INPUT = ROOT / "data/chunks/tarot_chunks.jsonl"

client = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
    timeout=60.0,
    max_retries=3,
)

db = chromadb.PersistentClient(
    path=str(ROOT / "storage/chroma")
)

# 使用新集合，避免与之前未完成的索引混淆
collection = db.get_or_create_collection(
    name="tarot_bge_m3_v1",
    metadata={"hnsw:space": "cosine"},
)

with INPUT.open("r", encoding="utf-8") as f:
    records = [
        json.loads(line)
        for line in f
        if line.strip()
    ]

print("Total chunks:", len(records))
print("Existing indexed:", collection.count())

BATCH_SIZE = 8

for start in range(0, len(records), BATCH_SIZE):
    batch = records[start:start + BATCH_SIZE]

    # 避免重复向量化已成功保存的片段
    existing = set(
        collection.get(
            ids=[r["id"] for r in batch]
        )["ids"]
    )
    pending = [r for r in batch if r["id"] not in existing]

    if not pending:
        continue

    texts = [r["text"] for r in pending]

    response = client.embeddings.create(
        model=MODEL,
        input=texts,
    )

    # 按 API 返回的 index 对齐输入文本
    vectors = [None] * len(pending)
    for item in response.data:
        vectors[item.index] = item.embedding

    if any(v is None or len(v) != 1024 for v in vectors):
        raise ValueError("Embedding response is incomplete")

    collection.upsert(
        ids=[r["id"] for r in pending],
        documents=texts,
        embeddings=vectors,
        metadatas=[
            {
                "source": r["source"],
                "pdf_page": r["pdf_page"],
                "model": MODEL,
            }
            for r in pending
        ],
    )

    print(
        f"Indexed: {collection.count()} / {len(records)}",
        flush=True
    )

    # 降低触发免费接口速率限制的概率
    time.sleep(0.5)

print("=" * 45)
print("INDEX COMPLETED")
print("Total indexed:", collection.count())
print("Embedding model:", MODEL)
print("=" * 45)
