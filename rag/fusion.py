"""Combine independent Tarot and I Ching interpretations; never reroll either."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

SYSTEM_PROMPT = """你是一位熟悉塔罗与《周易》经典的中文解读者。你正在给一个普通读者解释两次已经完成的象征性解读，而不是写研究论文或咨询报告。

目标：让读者读完后能明白：这两套解读分别提醒了什么、对眼前的问题有哪些值得思考的角度。写得自然、明白、连贯，有细节，但不要堆砌术语。

【真实性与边界】
- 塔罗牌、正逆位、卦象、动爻都已经确定，绝对不能重抽或改动。
- 分别尊重两套原书及独立解读，不混用来源，不把一种传统硬套在另一种上。
- 只能引用提供的独立报告中确实出现且有依据的材料；不要自造页码、引文、牌义、爻辞。
- 有不同甚至相反的启示时，用平实的语言解释差别，不必强行调和。
- 不据占卜断言未来、他人真实想法或任何实际事件必然发生。

【语言和篇幅——非常重要】
- 以读者提出的具体问题为中心，不复述完整两份独立报告。
- 正文以自然的中文段落为主，每段约100到180字，衔接流畅。
- 全文目标约550至850个汉字，复杂问题可适当增加，但避免超过1000字。
- 最多使用两个短标题，例如“放在一起看”和“接下来可以怎么做”；也可以完全不用标题。
- 不要使用项目符号、编号、表格、对照清单、三栏结论，尤其禁止把“共同点/不同点/矛盾”拆成一串小点。
- 不要依次重复“塔罗告诉你……周易告诉你……”的固定句式，也不要逐张重讲三张牌、逐条重讲六爻。
- 先用一两句直接回应用户关心的问题，再把两套结果自然穿插起来，重点抓住一两个真正重要的关联或张力。
- 建议只聚焦一到两个具体、可实行的行动思路，解释为什么，不要罗列七八条建议。
- 少用“象征性框架”“多维度”“结构性张力”“综合洞见”等抽象说法；遇到术语随手解释成人话。
- 不要对用户心理或处境进行未经证实的诊断，不要装作知道对方没说出的事情。
- 文献出处可在相关句末简短保留确有依据的PDF页码，不要将技术编号放入正文。
- 最后一两句自然提醒这是帮助反思的读法，而不是确定的预测；不要反复免责声明。
"""

def _interpretation(payload: dict[str, Any], key: str) -> str:
    if not isinstance(payload, dict):
        raise TypeError(f"{key} must be a dict")
    content = payload.get("interpretation") or payload.get("answer")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{key} requires a nonempty interpretation or answer string")
    return content.strip()


def build_fusion_prompt(question: str, tarot: dict[str, Any], yijing: dict[str, Any]) -> str:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question cannot be empty")
    tarot_text = _interpretation(tarot, "tarot")
    yijing_text = _interpretation(yijing, "yijing")
    # Truncate interpretation only, keeping structural inputs as separate JSON.
    tarot_record = {"spread": tarot.get("spread"), "sources": tarot.get("sources", [])}
    yijing_record = {"cast": yijing.get("cast"), "sources": yijing.get("sources", [])}
    return (
        f"用户原始问题：\n{question.strip()}\n\n"
        "===== TAROT：抽牌结果与来源 =====\n"
        + json.dumps(tarot_record, ensure_ascii=False, default=str)[:10000]
        + "\n\n===== TAROT：独立解读 =====\n"
        + tarot_text[:16000]
        + "\n\n===== YIJING：起卦结果与来源 =====\n"
        + json.dumps(yijing_record, ensure_ascii=False, default=str)[:10000]
        + "\n\n===== YIJING：独立解读 =====\n"
        + yijing_text[:16000]
        + "\n\n请对照分析两者，不得补造原书材料。"
    )


def fuse_readings(
    question: str,
    tarot: dict[str, Any],
    yijing: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Return output suitable for CLI, Streamlit and a saved JSON reading."""
    prompt = build_fusion_prompt(question, tarot, yijing)
    result = {"question": question, "answer": "", "prompt": prompt,
              "tarot": tarot, "yijing": yijing}
    if dry_run:
        return result
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY missing in project .env")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com",
                    timeout=120.0, max_retries=2)
    response = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": prompt}],
    )
    result["answer"] = response.choices[0].message.content or ""
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Fuse an existing Tarot and I Ching reading")
    parser.add_argument("--tarot-file", required=True, type=Path)
    parser.add_argument("--yijing-file", required=True, type=Path)
    parser.add_argument("--question", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tarot = json.loads(args.tarot_file.read_text(encoding="utf-8"))
    yijing = json.loads(args.yijing_file.read_text(encoding="utf-8"))
    question = args.question or yijing.get("question") or tarot.get("question")
    if not question:
        parser.error("Provide --question or a reading JSON with a question")
    result = fuse_readings(question, tarot, yijing, dry_run=args.dry_run)
    print("===== FUSION PROMPT =====" if args.dry_run else "===== FUSION READING =====")
    print(result["prompt"][:5000] if args.dry_run else result["answer"])


if __name__ == "__main__":
    main()
