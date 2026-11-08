import json
import os
import time
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

INPUT = ROOT / "data/chunks/zhouyi_index_ready.jsonl"
DB_PATH = ROOT / "storage/chroma"

MODEL = "BAAI/bge-m3"
COLLECTION_NAME = "zhouyi_bge_m3_v1"
BATCH_SIZE = 8

api = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
    timeout=60.0,
    max_retries=3,
)

db = chromadb.PersistentClient(path=str(DB_PATH))

collection = db.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

with INPUT.open(encoding="utf-8") as f:
    records = [
        json.loads(line)
        for line in f
        if line.strip()
    ]

print("Collection:", COLLECTION_NAME)
print("Input records:", len(records))
print("Already indexed:", collection.count())

for start in range(0, len(records), BATCH_SIZE):
    batch = records[start:start + BATCH_SIZE]

    ids = [r["id"] for r in batch]

    existing = set(collection.get(ids=ids)["ids"])

    pending = [
        r for r in batch
        if r["id"] not in existing
    ]

    if not pending:
        continue

    texts = [r["text"] for r in pending]

    response = api.embeddings.create(
        model=MODEL,
        input=texts
    )

    vectors = [None] * len(pending)

    for item in response.data:
        vectors[item.index] = item.embedding

    if any(
        vector is None or len(vector) != 1024
        for vector in vectors
    ):
        raise ValueError("Embedding返回结果异常")

    metadatas = []

    for record in pending:
        metadata = {
            "source": record["source"],
            "pdf_page": record["pdf_page"],
            "chunk_index": record["chunk_index"],
            "boundary_page": record["boundary_page"],
            "section_type": record["section_type"],
            "model": MODEL
        }

        # Chroma不接受None作为普通metadata值
        for key in (
            "section_id",
            "hexagram_name",
            "hexagram_number"
        ):
            value = record.get(key)
            if value is not None:
                metadata[key] = value

        metadatas.append(metadata)

    collection.upsert(
        ids=[r["id"] for r in pending],
        documents=texts,
        embeddings=vectors,
        metadatas=metadatas
    )

    print(
        f"Indexed: {collection.count()} / {len(records)}",
        flush=True
    )

    time.sleep(0.5)

print("\n===== COMPLETED =====")
print("Collection:", COLLECTION_NAME)
print("Indexed:", collection.count())
