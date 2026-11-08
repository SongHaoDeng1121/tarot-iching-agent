
# rag/search.py

from rag.hybrid_tarot import search_multi_source


def search(query, top_k=5):
    return search_multi_source(query, top_k=top_k)


if __name__ == "__main__":
    question = input("请输入塔罗问题：").strip()

    if not question:
        raise SystemExit("问题不能为空")

    results = search(question)

    for i, item in enumerate(results, 1):
        print("\n" + "=" * 50)
        print(f"RESULT {i}")
        print("ID:", item["id"])
        print("PDF page:", item["metadata"]["pdf_page"])
        print("Cosine distance:", round(item["distance"], 4))
        print("Content:")
        print(item["text"][:900])
