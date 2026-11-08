
# rag/reading_zhouyi.py
# I Ching Casting -> Exact RAG -> DeepSeek -> Citation Audit
from engines.yijing_line_rules import format_line_analysis
import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from engines.yijing_cast import (
    cast_hexagram,
    build_cast_result,
    print_cast,
)

from rag.zhouyi_exact import (
    retrieve_cast_evidence,
    format_segments,
)

from rag.answer_zhouyi import SYSTEM_PROMPT

from rag.zhouyi_source_audit import (
    make_source_record,
    register_source,
    audit_page_citations,
)


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

READINGS_DIR = ROOT / "data/readings"
LATEST_FILE = READINGS_DIR / "latest_yijing_cast.json"

SOURCE_NAME = "杨天才、张善文译注《周易》"


# --------------------------------------------------
# 1. Build the reading instructions
# --------------------------------------------------

def build_reading_question(question, cast):
    """
    Build a reading prompt using the deterministic
    result of the six-line casting engine.
    """

    original = cast["original_hexagram"]
    changed = cast["changed_hexagram"]

    moving = cast["moving_line_labels"]

    moving_text = (
        "、".join(moving)
        if moving
        else "无动爻"
    )

    if cast["has_changes"]:
        changed_description = (
            f"变卦为第{changed['number']}卦"
            f"《{changed['name']}》。"
        )
    else:
        changed_description = (
            "本次没有动爻，因此不另设变卦解读。"
        )

    return f"""
用户的问题：
{question}

以下卦象已经由Python计算完成。
不得自行重新起卦、修改动爻或变卦。

【本卦】
第{original['number']}卦《{original['name']}》
上卦：{original['upper_trigram']}
下卦：{original['lower_trigram']}

【动爻】
{moving_text}

【变化】
{changed_description}

请完成以下任务：

1. 根据本卦的题解、卦辞及经传，
   解释本卦所代表的基本情境。

2. 如果存在动爻，
   重点解释本卦相应爻辞，
   包括字词、译文、《象传》及原书评析。

3. 说明动爻的结构：
   - 阴阳
   - 爻位
   - 得中或不得中
   - 当位或失位
   - 有应或无应
   注意区分这些概念。

4. 如果存在变卦，
   使用提供的变卦原书资料，
   解释从本卦到变卦的象征性变化。

5. 比较本卦、动爻与变卦，
   不要只分别介绍它们。

6. 最后联系用户的现实问题，
   提出可以反思的行动方向。

7. 这是传统象征系统中的解读，
   不是对现实未来的确定预测。

【文献规范】

- 必须区分经文、《易传》、译注和综合分析。
- 只能引用下面实际提供的文献材料。
- 引用时使用：[《周易》，PDF第XX页]。
- 不得引用未提供的PDF页码。
- 如果资料不充分，应当说明。
- 不得将OCR错字自动当成确定的原文字形。
- 不要因为变卦的出现而断言现实结果必然如此。

用自然、完整的中文回答。
""".strip()


# --------------------------------------------------
# 2. Evidence preparation
# --------------------------------------------------

def build_exact_evidence(cast):
    """
    Retrieve exact chapter and moving-line evidence.

    Returns:
        evidence_text
        source_registry
        evidence_summary

    If an essential passage cannot be located,
    fail explicitly instead of using unrelated
    semantic results as a replacement.
    """

    items = retrieve_cast_evidence(cast)

    required_types = {"original_hexagram"}

    if cast["has_changes"]:
        required_types.add("moving_line")
        required_types.add("changed_hexagram")

    actual_types = {
        item["type"]
        for item in items
    }

    missing = required_types - actual_types

    if missing:
        raise RuntimeError(
            "Required evidence missing: "
            + ", ".join(sorted(missing))
        )

    expected_moving_count = len(
        cast["moving_line_labels"]
    )

    actual_moving_count = sum(
        item["type"] == "moving_line"
        for item in items
    )

    if actual_moving_count != expected_moving_count:
        raise RuntimeError(
            "Moving-line evidence count mismatch: "
            f"expected {expected_moving_count}, "
            f"found {actual_moving_count}"
        )

    registry = []
    blocks = []
    summary = []

    for index, item in enumerate(items, 1):
        segments = item.get("segments", [])

        if not segments:
            raise RuntimeError(
                f"Empty evidence: {item['name']}"
            )

        # Every source page is from a chapter-bounded
        # exact retrieval, not an arbitrary similarity hit.
        for segment in segments:
            register_source(
                registry,
                make_source_record(
                    pdf_page=segment["pdf_page"],
                    hexagram=item["name"],
                    origin="direct",
                    text=segment["text"],
                    verified=True,
                ),
            )

        page_numbers = sorted({
            int(segment["pdf_page"])
            for segment in segments
        })

        summary.append({
            "type": item["type"],
            "name": item["name"],
            "pages": page_numbers,
        })

        blocks.append(
            f"[精确证据 {index}]\n"
            f"证据类型：{item['type']}\n"
            f"目标：{item['name']}\n"
            f"来源：{SOURCE_NAME}\n"
            f"PDF页码：{page_numbers}\n"
            f"检索方式：已定位章节范围内的精确提取\n"
            f"正文：\n"
            f"{format_segments(segments)}"
        )

    return (
        "\n\n".join(blocks),
        registry,
        summary,
    )


# --------------------------------------------------
# 3. Prompt construction
# --------------------------------------------------

def build_full_prompt(question, cast, evidence):
    reading_question = build_reading_question(
        question,
        cast,
    )

    return (
        f"{reading_question}\n\n"
        "===== 已检索的文献证据 =====\n\n"
        f"{evidence}\n\n"
        "===== 最终要求 =====\n"
        "只依据以上文献证据解释具体经文、"
        "卦辞及爻辞。\n"
        "不得根据一般知识补充未经检索的原文。\n"
        "请为文献性事实标注实际PDF页码。"
    )


# --------------------------------------------------
# 4. DeepSeek generation
# --------------------------------------------------

def ask_deepseek(prompt):
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is missing from .env"
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=120.0,
        max_retries=2,
    )

    response = client.chat.completions.create(
        model=os.getenv(
            "DEEPSEEK_MODEL",
            "deepseek-chat",
        ),
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    return (
        response.choices[0].message.content
        or ""
    )


# --------------------------------------------------
# 5. Save reading records
# --------------------------------------------------

def save_reading_record(result):
    READINGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "created_at": datetime.now().astimezone().isoformat(),
        **result,
    }

    LATEST_FILE.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# --------------------------------------------------
# 6. End-to-end reading
# --------------------------------------------------

def run_reading(
    question,
    line_values=None,
    dry_run=False,
    save=True,
):
    """
    Exact RAG reading pipeline.

    Does not run broad hybrid_search().

    Uses only:
      - original hexagram chapter
      - required moving line passages
      - changed hexagram chapter
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError(
            "Question cannot be empty"
        )

    # A. Casting
    if line_values is None:
        cast = cast_hexagram()
    else:
        cast = build_cast_result(
            line_values
        )

    # B. Exact evidence
    evidence, registry, summary = (
        build_exact_evidence(cast)
    )

    # C. Build final prompt
    prompt = build_full_prompt(
        question,
        cast,
        evidence,
    )

    answer = ""
    citation_report = None

    # D. Call DeepSeek only for actual generation
    if not dry_run:
        answer = ask_deepseek(prompt)

        citation_report = audit_page_citations(
            answer,
            registry,
        )

    result = {
        "question": question,
        "cast": cast,
        "answer": answer,
        "sources": summary,
        "citation_audit": citation_report,
        "prompt": prompt,
    }

    # Save only completed readings.
    # Dry-run does not overwrite the latest answer.
    if not dry_run and save:
        save_reading_record(result)

    return result


# --------------------------------------------------
# 7. CLI
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "I Ching casting and exact-document reading"
        )
    )

    parser.add_argument(
        "--question",
        "-q",
        default=None,
    )

    parser.add_argument(
        "--lines",
        default=None,
        help=(
            "Six line values from bottom to top, "
            "e.g. 7,8,8,8,7,6"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    question = args.question

    if question is None:
        question = input(
            "请输入你的周易占问："
        ).strip()

    values = None

    if args.lines is not None:
        try:
            values = [
                int(x.strip())
                for x in args.lines.split(",")
            ]
        except ValueError:
            parser.error(
                "--lines requires six integers"
            )

    result = run_reading(
        question=question,
        line_values=values,
        dry_run=args.dry_run,
    )

    print_cast(result["cast"])

    print("\n===== EXACT EVIDENCE SOURCES =====")

    for item in result["sources"]:
        print(
            f"{item['type']} | "
            f"{item['name']} | "
            f"PDF {item['pages']}"
        )

    if args.dry_run:
        print("\n===== EVIDENCE PREVIEW =====")
        print(result["prompt"][:16000])

    else:
        print("\n===== ZHOUYI READING =====")
        print(result["answer"])

        audit = result["citation_audit"]

        print("\n===== CITATION AUDIT =====")

        print(
            "Cited pages:",
            audit["cited_pages"],
        )

        print(
            "Verified evidence pages:",
            audit["available_pages"],
        )

        print(
            "Unsupported pages:",
            audit["unsupported_pages"],
        )

        print(
            "Page citation check:",
            "PASS" if audit["passed"] else "FAIL",
        )

        print(
            "\nReading saved to:",
            LATEST_FILE,
        )


if __name__ == "__main__":
    main()
