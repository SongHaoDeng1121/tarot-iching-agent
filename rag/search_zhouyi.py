
import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI
from rag.runtime_data import chroma_path

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL = "BAAI/bge-m3"
COLLECTION_NAME = "zhouyi_bge_m3_v1"

api = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
    timeout=60.0,
    max_retries=3,
)

db = chromadb.PersistentClient(
    path=str(chroma_path())
)

collection = db.get_collection(
    name=COLLECTION_NAME
)


def search_zhouyi(query: str, top_k: int = 5):
    """Search the Zhouyi collection using BGE-M3 embeddings."""

    if not query.strip():
        return []

    count = collection.count()

    if count == 0:
        return []

    response = api.embeddings.create(
        model=MODEL,
        input=query,
    )

    vector = response.data[0].embedding

    results = collection.query(
        query_embeddings=[vector],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )

    output = []

    for i, chunk_id in enumerate(results["ids"][0]):
        output.append({
            "id": chunk_id,
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })

    return output


if __name__ == "__main__":
    question = input("请输入《周易》问题：").strip()

    results = search_zhouyi(question, top_k=5)

    print("\n===== SEARCH RESULTS =====")

    for i, item in enumerate(results, 1):
        metadata = item["metadata"]

        print(f"\n--- RESULT {i} ---")
        print("ID:", item["id"])
        print("卦名:", metadata.get("hexagram_name", "未核实"))
        print("PDF页码:", metadata.get("pdf_page"))
        print("边界页:", metadata.get("boundary_page"))
        print("Cosine distance:", round(item["distance"], 4))
        print("内容:")
        print(item["text"][:600])
