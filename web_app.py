
# web_app.py
# Tarot & Wisdom — Streamlit Web Application
from PIL import Image
import json
import uuid
from datetime import datetime
from pathlib import Path
import re

import streamlit as st

from engines.tarot_draw import make_three_card_spread
from engines.yijing_cast import cast_hexagram, build_cast_result
from engines.yijing_line_rules import format_line_analysis
from rag.reading_zhouyi import run_reading
from rag.fusion import fuse_readings
from rag.followup import answer_followup
from rag.answer import load_cards
from rag.spread import (
    validate_spread,
    prepare_exact_evidence,
    prepare_vector_evidence,
    build_spread_prompt,
    ask_deepseek,
    check_citations,
)

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "data" / "readings"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

ORIENTATION_ZH = {
    "upright": "正位",
    "reversed": "逆位",
}


RETRIEVAL_MODES = {
    "仅原书模式": {
        "top_k": 0,
        "description": "只使用抽中卡牌的原书专属章节，适合研究牌义。",
    },
    "混合检索模式": {
        "top_k": 3,
        "description": "精确章节 + 3条语义补充，适合日常解读。",
    },
    "扩展研究模式": {
        "top_k": 6,
        "description": "精确章节 + 6条语义补充，进行更深入的比较分析。",
    },
}

RESEARCH_INSTRUCTIONS = {
    "仅原书模式": """
请严格围绕三张牌的原书章节进行解释。
区分作者的原文观点与结合牌阵提出的推论。
不要补充未在证据中出现的其他理论或牌义。
""",

    "混合检索模式": """
优先使用专属章节解释每张牌。
材料仅作为补充背景。
重点分析三张牌在不同位置之间的相互关系，
并提供简洁、现实、可执行的反思建议。
""",

    "扩展研究模式": """
请进行更深入的文献式比较分析：

1. 分别讨论三张牌的核心象征及正逆位依据。
2. 分析三张牌之间的共同主题与可能的冲突。
3. 检查相关资料是否提供相关背景。
4. 说明不同解读方向各自在什么条件下成立。
5. 明确区分作者观点、象征推论与现实事实。
6. 指出证据不足、不能确定的结论。
7. 给出综合分析和具有实践意义的反思建议。

不要为了扩大分析而强行引用无关的向量结果。
"""
}

# --------------------------------------------------
# Natural Reading Style
# --------------------------------------------------

NATURAL_READING_STYLE = """
你是一位熟悉塔罗象征学、善于解释经典文献的阅读者。
请像一位知识丰富、表达清晰的塔罗老师一样与用户交流。

【语言风格】

1. 全程使用自然、流畅的中文。
2. 使用完整段落解释，不要把回答写成学术报告。
3. 语言亲切、平实、有思考深度，但不要故作神秘。
4. 尽量使用日常词汇，不要堆砌抽象概念。
5. 可以引用原书思想，但要把它自然地融入叙述。
6. 不要反复使用“原书依据”“结合位置的解释”
   “综合推论”“需要注意的是”等固定标签。
7. 不要机械地重复“这张牌象征……”的句式。
8. 不要为了显得严谨而在每句话后面加入证据编号。
9. 尽量减少列表和表格，用连贯的段落解释。
10. 避免过度肯定用户的心理状态，保持合理的不确定性。

【解读方法】

对于每张牌：

先自然地介绍牌面象征及其在原书中的重要含义。

然后联系用户描述的现实情况，
解释这张牌可能提供什么观察角度。

如果原书存在不同解释方向，
请自然地讨论它们，而不是强行得出唯一结论。

不要随意推断第三方的真实心理，
不要把牌义当作对未来事件的确定性预测。

【牌间关系】

解释三张牌之间的联系时，
不要简单地拼接三种牌义。

要考虑它们如何相互补充、对照或产生张力，
形成有逻辑且容易理解的整体分析。

【文献引用】

你仍然必须依据提供的 EXACT 和 VECTOR 证据。

正文中不要出现以下技术格式：

[EXACT_xxx]
[VECTOR_xxx]
SOURCE_ID
RAG
Embedding
Chunk

请在回答最后单独设置一个简短的
“原书出处”部分，列出实际引用的证据编号和页码，
供程序进行引用验证。

正文以自然、可读的中文为主。
不要大段复制原书。

【输出结构】

允许使用少量中文标题，例如：

现状：某张牌
阻碍：某张牌
建议：某张牌
三张牌带来的启示

但每一节都应该以完整、自然的段落展开。

不要强制使用“一、二、三、四、五”的学术报告格式。

最终目标是让用户感觉自己正在阅读一篇
有深度、可信、有文献基础的塔罗解读，
而不是一份自动生成的研究报告。
"""

# --------------------------------------------------
# Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="Tarot × I Ching",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {
    max-width: 1100px;
    padding-top: 2rem;
}
.card-panel {
    border: 1px solid rgba(128,128,128,0.28);
    border-radius: 14px;
    padding: 18px 12px;
    text-align: center;
    min-height: 155px;
}
.card-position {
    font-size: 13px;
    opacity: 0.7;
    margin-bottom: 12px;
}
.card-name {
    font-size: 19px;
    font-weight: 600;
    margin-bottom: 8px;
}
.card-orientation {
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# State
# --------------------------------------------------

if "spread" not in st.session_state:
    st.session_state.spread = None

if "answer" not in st.session_state:
    st.session_state.answer = None

if "sources" not in st.session_state:
    st.session_state.sources = None

if "reading_id" not in st.session_state:
    st.session_state.reading_id = None


@st.cache_data
def get_knowledge():
    return load_cards()


def save_reading(spread, answer, sources, mode):
    """Save a completed interpretation locally."""
    reading_id = (
        datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        + "_"
        + uuid.uuid4().hex[:8]
    )

    record = {
        "id": reading_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "spread": spread,
        "answer": answer,
        "sources": sources,
        "retrieval_mode": mode,
    }

    destination = HISTORY_DIR / f"{reading_id}.json"

    destination.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return reading_id


def list_readings():
    """List previously saved interpretations."""
    files = sorted(
        HISTORY_DIR.glob("*.json"),
        reverse=True,
    )

    return files


def load_reading(path):
    """Load one saved reading."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def source_registry(exact, semantic):
    """Build a serializable list of references."""
    result = []

    for item in exact:
        result.append({
            "id": item["id"],
            "type": "EXACT",
            "source_id": item.get("source_id"),
            "title": item.get("title"),
            "author": item.get("author"),
            "card": item["name"],
            "position": item["position"],
            "pages": item["pages"],
            "orientation": item.get("orientation"),
            "evidence_chunk_ids": item.get("evidence_chunk_ids", []),
        })

    for item in semantic:
        result.append({
            "id": item["id"],
            "type": "VECTOR",
            "source_id": item.get("source_id"),
            "title": item.get("title"),
            "author": item.get("author"),
            "card": item.get("card_name") or item.get("card_id"),
            "position": item.get("position"),
            "orientation": item.get("orientation_context"),
            "pages": item.get("pages", [item["page"]]),
            "retrieval_methods": item.get("retrieval_methods", []),
        })

    return result



def display_cards(spread, knowledge):
    """
    Display real Rider-Waite tarot images.

    - Upright cards: normal orientation
    - Reversed cards: rotated 180 degrees
    - Three cards remain in their spread positions
    """

    image_dir = ROOT / "assets" / "tarot"

    columns = st.columns(3, gap="medium")

    for col, card in zip(columns, spread["cards"]):

        card_id = card["card_id"]
        orientation = card["orientation"]
        position = card["position"]

        card_name = knowledge[card_id]["name_en"]

        image_path = image_dir / f"{card_id}.jpg"

        with col:
            with st.container(border=True):

                # Position label
                st.markdown(
                    f"#### {position}"
                )

                # Real tarot card artwork
                if image_path.is_file():

                    with Image.open(image_path) as img:
                        card_image = img.convert("RGB")

                    if orientation == "reversed":
                        card_image = card_image.rotate(
                            180,
                            expand=True,
                        )

                    st.image(
                        card_image,
                        width="stretch",
                        alt=card_name,
                    )

                else:
                    st.warning(
                        f"缺少图片：{card_id}"
                    )

                # Card name
                st.markdown(
                    f"**{card_name}**"
                )

                # Orientation
                orientation_zh = ORIENTATION_ZH[
                    orientation
                ]

                if orientation == "reversed":
                    st.caption(
                        f"逆位 · Reversed"
                    )
                else:
                    st.caption(
                        f"正位 · Upright"
                    )



def format_reading_for_display(answer):
    """
    Hide internal RAG citation identifiers from the
    user-facing reading.

    Original answer remains unchanged for validation
    and history storage.
    """

    # 移除模型单独生成的原书出处章节；
    # 正式来源仍由 Streamlit 的文献面板展示
    answer = re.split(
        r"(?m)^#{1,6}\s*(?:五[、.]?\s*)?原书出处\s*$",
        answer,
        maxsplit=1,
    )[0]

    # 移除方括号形式的内部证据编号
    answer = re.sub(
        r"\s*\[(?:EXACT|VECTOR)_[A-Za-z0-9_]+\]",
        "",
        answer,
    )

    # 兼容不带方括号的证据编号
    answer = re.sub(
        r"\b(?:EXACT|VECTOR)_[A-Za-z0-9_]+\b",
        "",
        answer,
    )

    return answer.strip()


def interpret_spread(spread, mode="混合检索模式"):
    """
    Interpret a Tarot spread using Hybrid RAG.

    Supports:
        仅原书模式
        混合检索模式
        扩展研究模式

    All modes use natural Chinese explanations.
    """

    if mode not in RETRIEVAL_MODES:
        raise ValueError(
            f"Unknown retrieval mode: {mode}"
        )

    # 1. 根据模式设置检索数量
    top_k = RETRIEVAL_MODES[mode]["top_k"]

    # 2. 加载牌义知识库
    knowledge = get_knowledge()

    validate_spread(spread, knowledge)

    # 3. 精确章节检索
    exact = prepare_exact_evidence(
        spread,
        knowledge,
    )

    # 4. 向量补充检索
    if top_k > 0:
        semantic = prepare_vector_evidence(
            spread,
            top_k=top_k,
        )
    else:
        semantic = []

    # 5. 构建 RAG Prompt
    prompt = build_spread_prompt(
        spread,
        exact,
        semantic,
    )

    # Ensure the same original user question is explicitly included.
    prompt += ("\n\n===== USER QUESTION =====\n" + str(spread.get("question", "")))

    # 6. 当前检索模式的分析要求
    prompt += (
        "\n\n========== READING MODE ==========\n"
        + f"Mode: {mode}\n"
        + RESEARCH_INSTRUCTIONS[mode]
    )

    # 7. 统一添加自然中文表达要求
    prompt += (
        "\n\n========== WRITING STYLE ==========\n"
        + NATURAL_READING_STYLE
    )

    # 8. DeepSeek 生成解读
    answer = ask_deepseek(prompt)

    if not answer or not answer.strip():
        raise RuntimeError(
            "DeepSeek returned an empty answer."
        )

    # 9. 保留后台引用验证
    invalid, missing_exact = check_citations(
        answer,
        exact,
        semantic,
    )

    # 10. 文献来源
    sources = source_registry(
        exact,
        semantic,
    )

    validation = {
        "unknown_source_ids": invalid,
        "exact_sources_not_cited": missing_exact,
    }

    return answer, sources, validation




# --------------------------------------------------
# Combined Tarot x I Ching application
# --------------------------------------------------

JOINT_PREFIX = "joint_"
STATE_KEY = "joint_record"


def persist_joint_record(record):
    """Save a complete dual-system result; do not overwrite legacy Tarot records."""
    reading_id = (
        JOINT_PREFIX
        + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        + "_"
        + uuid.uuid4().hex[:8]
    )
    record = {**record, "id": reading_id, "created_at": datetime.now().astimezone().isoformat(), "kind": "joint"}
    (HISTORY_DIR / f"{reading_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return record


def combined_history():
    # exclude latest_yijing_cast.json, which is a single-system intermediate record
    return [p for p in sorted(HISTORY_DIR.glob("*.json"), reverse=True)
            if p.name != "latest_yijing_cast.json"]


def render_hexagram_cast(cast):
    left, right = st.columns(2, gap="medium")
    for col, key, title in (
        (left, "original_hexagram", "本卦"),
        (right, "changed_hexagram", "变卦"),
    ):
        info = cast[key]
        with col:
            with st.container(border=True):
                st.markdown(f"#### {title} · 第{info['number']}卦《{info['name']}》 {info.get('unicode', '')}")
                st.caption(f"上{info['upper_trigram']} {info['upper_symbol']} · 下{info['lower_trigram']} {info['lower_symbol']}")
                # Draw from sixth (top) line to first (bottom) line.
                line_text = []
                for position in range(6, 0, -1):
                    v = info["lines_bottom_to_top"][position - 1]
                    mark = "  ← 动爻" if key == "original_hexagram" and position in cast["moving_positions"] else ""
                    line_text.append(f"{position}  {'━━━━━━━' if v else '━━━ ━━━'}{mark}")
                st.code("\n".join(line_text), language=None)
    st.caption("动爻：" + ("、".join(cast["moving_line_labels"]) if cast["moving_line_labels"] else "无动爻"))
    with st.expander("查看本卦的确定性爻位分析"):
        st.text(format_line_analysis(cast, moving_only=True))


def generate_joint(record, mode):
    """Interpret the already displayed Tarot spread and hexagram; never redraw."""
    question = record["question"]
    spread = record["tarot_spread"]
    cast = record["cast"]

    tarot_answer, tarot_sources, tarot_validation = interpret_spread(spread, mode=mode)
    if not tarot_answer.strip():
        raise RuntimeError("塔罗解读返回空内容")

    # IMPORTANT: reuse the six exact line values from the shown cast
    yijing = run_reading(
        question=question,
        line_values=cast["line_values_bottom_to_top"],
        dry_run=False,
    )
    # Detect any accidental changes in the I Ching pipeline.
    if yijing["cast"]["line_values_bottom_to_top"] != cast["line_values_bottom_to_top"]:
        raise RuntimeError("周易解卦结果与页面展示的六爻不一致")

    if not yijing["answer"].strip():
        raise RuntimeError("周易解读返回空内容")

    tarot_payload = {
        "spread": spread,
        "answer": tarot_answer,
        "sources": tarot_sources,
        "validation": tarot_validation,
    }
    yijing_payload = {
        "cast": cast,
        "answer": yijing["answer"],
        "sources": yijing["sources"],
        "citation_audit": yijing["citation_audit"],
    }
    fusion = fuse_readings(question=question, tarot=tarot_payload, yijing=yijing_payload)
    if not fusion["answer"].strip():
        raise RuntimeError("Fusion Agent 返回空内容")

    return {
        **record,
        "tarot": tarot_payload,
        "yijing": yijing_payload,
        "fusion": fusion["answer"],
        "retrieval_mode": mode,
    }


def persist_followup(record, turn):
    """Append a Q/A to this SAME saved joint reading; do not make a new draw."""
    if record.get("kind") != "joint" or not record.get("id"):
        raise ValueError("当前记录还未完成保存，不能写入追问。")

    updated = {**record, "followups": [*(record.get("followups") or []), turn]}
    target = HISTORY_DIR / (str(record["id"]) + ".json")
    if not target.is_file():
        raise FileNotFoundError(f"未找到本次历史记录：{target.name}")

    # Atomic replacement: history stays intact if write is interrupted.
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(target)
    return updated


def render_followups(record):
    """Follow-up chat anchored to this reading, without reroll or new RAG."""
    st.divider()
    st.subheader("4. 继续追问这一次占卜")
    st.caption("沿用同一组塔罗牌与六爻，可继续追问牌义、动爻、两者之间的关系。不会重新抽取。")

    for turn in record.get("followups", []):
        with st.chat_message("user"):
            st.markdown(turn.get("question", ""))
        with st.chat_message("assistant"):
            st.markdown(turn.get("answer", ""))

    # Streamlit forms avoid duplicate model calls on ordinary page reruns.
    with st.form("joint_followup_form", clear_on_submit=True):
        followup = st.text_area(
            "继续问这组牌和卦",
            placeholder="例如：屯卦上六的‘何可长也’，与我的问题具体有什么关系？",
            height=100,
        )
        submitted = st.form_submit_button("发送追问", use_container_width=True)

    if submitted:
        if not followup.strip():
            st.warning("请输入追问内容。")
        else:
            try:
                with st.spinner("正在结合本次牌阵和前面的对话回答..."):
                    turn = answer_followup(record, followup.strip())
                    updated = persist_followup(record, turn)
                st.session_state[STATE_KEY] = updated
                st.rerun()
            except Exception as exc:
                st.error(f"追问失败：{exc}")
                st.caption("原先的牌阵、卦象和已保存对话不会改变。")


def render_results(record):
    if "tarot" not in record or "yijing" not in record:
        return

    st.divider()
    st.subheader("3. 联合解读")
    st.markdown(record["fusion"])
    st.caption("两套经典提供不同的思考角度；解读并非对现实结果的确定预测。")

    st.divider()
    render_followups(record)

    st.subheader("5. 想深入研究？")
    st.caption("以下为完整原书解读和检索出处。不展开也可以直接阅读上面的联合解读。")

    with st.expander("查看塔罗完整解读及文献出处", expanded=False):
        st.markdown(format_reading_for_display(record["tarot"]["answer"]))
        tarot_validation = record["tarot"].get("validation", {})
        if tarot_validation.get("unknown_source_ids"):
            st.warning("塔罗存在未知证据编号：" + str(tarot_validation["unknown_source_ids"]))
        st.markdown("**塔罗文献来源**")
        for src in record["tarot"].get("sources", []):
            book = src.get("title") or src.get("source_id", "")
            author = src.get("author") or ""
            position = src.get("position") or ""
            card = src.get("card") or "通用方法"
            st.write(
                f"{book} · {author} · {position} · {card} · PDF {src.get('pages', [])}"
            )

    with st.expander("查看周易完整解读及文献出处", expanded=False):
        st.markdown(record["yijing"]["answer"])
        audit = record["yijing"].get("citation_audit") or {}
        if audit.get("passed"):
            st.caption("PDF页码引用一致性：PASS（不等于逐字核验）")
        elif audit:
            st.warning("引用审核未通过：" + str(audit.get("unsupported_pages", [])))
        st.markdown("**周易精确证据来源**")
        for src in record["yijing"].get("sources", []):
            st.write(f"{src['type']} · {src['name']} · PDF {src['pages']}")

    st.divider()
    st.subheader("6. 保存与导出")
    dialogue = "\n\n".join(
        f"**追问：** {t.get('question', '')}\n\n**回答：** {t.get('answer', '')}"
        for t in record.get("followups", [])
    )
    concise = (
        f"# 塔罗 × 周易联合解读\n\n问题：{record['question']}\n\n"
        + record["fusion"] + "\n"
        + ("\n## 本次追问对话\n\n" + dialogue + "\n" if dialogue else "")
    )
    full = (
        concise
        + "\n## 塔罗完整解读\n\n" + format_reading_for_display(record["tarot"]["answer"])
        + "\n\n## 周易完整解读\n\n" + record["yijing"]["answer"] + "\n"
    )
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("下载简明解读", data=concise,
                           file_name="joint_reading_brief.md", mime="text/markdown",
                           use_container_width=True)
    with col2:
        st.download_button("下载完整研究记录", data=full,
                           file_name="joint_reading_full.md", mime="text/markdown",
                           use_container_width=True)
    with st.expander("查看完整联合记录 JSON"):
        st.json(record)


if STATE_KEY not in st.session_state:
    st.session_state[STATE_KEY] = None
if "question_input" not in st.session_state:
    st.session_state.question_input = ""

with st.sidebar:
    st.title("Tarot × I Ching")
    st.caption("塔罗 × 周易 · 原书证据辅助解读")
    retrieval_mode = st.radio(
        "塔罗检索模式", list(RETRIEVAL_MODES), index=1,
        help="周易部分始终使用精确章节与动爻检索。",
    )
    st.caption(RETRIEVAL_MODES[retrieval_mode]["description"])
    st.divider()
    st.subheader("历史记录")
    files = combined_history()
    if files:
        selected = st.selectbox("已保存的记录", files, format_func=lambda p: p.stem)
        if st.button("加载记录", use_container_width=True):
            try:
                old = json.loads(selected.read_text(encoding="utf-8"))
                if old.get("kind") == "joint":
                    st.session_state[STATE_KEY] = old
                    st.session_state.question_input = old.get("question", "")
                elif "spread" in old:
                    # Existing legacy single-Tarot record, still readable.
                    st.session_state[STATE_KEY] = {
                        "kind": "legacy_tarot", "question": old["spread"].get("question", ""),
                        "tarot_spread": old["spread"], "tarot": {
                            "answer": old.get("answer", ""), "sources": old.get("sources", [])
                        },
                    }
                    st.session_state.question_input = old["spread"].get("question", "")
                else:
                    st.warning("该文件不是可识别的联合记录或旧版塔罗记录。")
                    st.stop()
                st.rerun()
            except (OSError, KeyError, ValueError, TypeError) as exc:
                st.error(f"读取历史记录失败：{exc}")
    else:
        st.caption("暂无历史记录")
    st.divider()
    st.caption("用于象征性阅读与个人反思，不替代现实证据或专业判断。")

st.title("Tarot × I Ching")
st.markdown("### 一个问题 · 三张塔罗牌 · 六爻起卦 · 双系统联合解读")
st.caption("Tarot：Rachel Pollack《78度智慧》｜周易：杨天才、张善文译注《周易》")
st.divider()
st.subheader("1. 提出问题")
st.text_area(
    "希望通过这次联合解读探讨什么？",
    key="question_input", height=125,
    placeholder="例如：我目前遇到的困难，应该如何调整行动方式？",
)

if st.button("同时抽取塔罗与周易", type="primary", use_container_width=True):
    question = st.session_state.question_input.strip()
    if not question:
        st.warning("请先输入问题。")
    else:
        try:
            spread = make_three_card_spread(question)
            validate_spread(spread, get_knowledge())
            cast = cast_hexagram()
            st.session_state[STATE_KEY] = {
                "kind": "prepared", "question": question,
                "tarot_spread": spread, "cast": cast,
            }
            st.rerun()
        except Exception as exc:
            st.error(f"抽牌或起卦失败：{exc}")

record = st.session_state[STATE_KEY]
if record:
    st.divider()
    st.subheader("2. 本次抽取结果")
    st.info("本次问题：" + record["question"])
    display_cards(record["tarot_spread"], get_knowledge())
    if "cast" in record:
        st.markdown("#### 周易本卦与变卦")
        render_hexagram_cast(record["cast"])

    if record.get("kind") == "legacy_tarot":
        st.subheader("旧版塔罗解读")
        st.markdown(format_reading_for_display(record["tarot"]["answer"]))
        st.caption("这是旧版单塔罗记录，不包含周易或联合分析。")
    elif "fusion" not in record:
        if st.session_state.question_input.strip() != record["question"]:
            st.warning("输入框中的问题已改变；本次解读仍使用抽取时的问题。要更换问题请重新抽取。")
        if st.button("开始双系统解读与 Fusion 综合分析", type="primary", use_container_width=True):
            try:
                with st.spinner("正在分别检索两套文献、生成解读与交叉分析..."):
                    complete = generate_joint(record, retrieval_mode)
                    complete = persist_joint_record(complete)
                st.session_state[STATE_KEY] = complete
                st.rerun()
            except Exception as exc:
                st.error(f"联合解读失败：{exc}")
                st.caption("已抽出的三张牌和六爻仍保留，不会自动重新抽取。")
    else:
        render_results(record)
else:
    st.info("输入问题并点击抽取按钮，同时生成塔罗三张牌和周易六爻。")
