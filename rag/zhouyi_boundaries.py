"""Resolve precise OCR offsets using structured hints and independent evidence.

The existing section table is provisional. Its page ranges are never used as
whole-page evidence: each endpoint must be corroborated in the actual OCR.
"""
import json
import re
import unicodedata

from engines.hexagram_utils import HEXAGRAM_NAMES
from rag.runtime_data import knowledge_path

TITLE_MARKER = re.compile(r"【\s*题\s*解\s*】")


def canonical_name(name):
    # Established title variant, not a general OCR character replacement.
    return name.replace("遁", "遯")


def title_prefix(title):
    title = unicodedata.normalize("NFKC", title)
    title = title.split("(", 1)[0]
    title = re.sub(r"[\s0-9?？]", "", title)
    return canonical_name(title)


def context_key(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def load_sections():
    return json.loads(knowledge_path("data/structured/zhouyi_sections.json").read_text(encoding="utf-8"))


def resolve_start(pages, entry, *, appendix=False):
    """Validate a unique title immediately before 题解 on the indexed page."""
    name = entry["name"]
    page = entry["start_pdf_page"]
    if type(page) is not int or page not in pages:
        raise ValueError(f"《{name}》结构索引指向缺失的OCR页：{page}")
    text = pages[page]
    lines = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            lines.append((offset, line.rstrip("\r\n")))
        offset += len(line)
    expected = canonical_name(name)
    titles = {expected}
    if appendix and name.endswith("传"):
        titles |= {expected[:-1], "周易" + expected[:-1]}
    contexts = {context_key(line) for line in entry.get("heading_context_ocr", []) if line.strip()}
    candidates = []
    for marker in TITLE_MARKER.finditer(text):
        preceding = [(position, line) for position, line in lines if position < marker.start() and text[position:marker.start()].strip()]
        # Marker must begin its own line; the previous nonblank line is title.
        before = text[:marker.start()]
        if before[before.rfind("\n") + 1:].strip():
            continue
        preceding = [(position, line) for position, line in preceding if position + len(line) <= marker.start()]
        if not preceding:
            continue
        position, line = preceding[-1]
        if text[position + len(line):marker.start()].strip() or len(line.strip()) > 45:
            continue
        normalized = title_prefix(line)
        method = None
        if normalized in titles:
            method = "indexed_page_title_and_tijie"
            if context_key(line) in contexts:
                method += "_context"
        elif not appendix and normalized not in set(HEXAGRAM_NAMES) and context_key(line) in contexts:
            # For an actual misspelling, the *same* recorded OCR title is not
            # enough. Require both repeated target references and its own
            # judgement heading in the bounded introduction. No fuzzy mapping.
            end_page = entry.get("end_pdf_page_inclusive", page + 1)
            following = text[marker.end():] + "\n" + "\n".join(
                # Never borrow corroboration from the shared next-chapter page.
                pages.get(number, "") for number in range(page + 1, min(page + 3, end_page))
            )
            first_line = re.search(r"(?m)^[ \t]*(?:初[六九]|[六九][二三四五]|上[六九])[，,:：]", following)
            introduction = following[:first_line.start()] if first_line else following
            variants = {name, name.replace("遯", "遁")}
            references = sum(len(re.findall(r"《\s*" + re.escape(value) + r"\s*》", introduction)) for value in variants)
            judgement = any(re.search(
                r"(?m)^[ \t]*" + re.escape(value) + r"[^\u3400-\u9fff\n]{0,6}[：:]", introduction
            ) for value in variants)
            if references >= 2 and judgement:
                method = "recorded_ocr_title_tijie_references_and_judgement"
        if method:
            candidates.append({"pdf_page": page, "offset": position, "method": method})
    if len(candidates) != 1:
        raise ValueError(
            f"《{name}》PDF {page} 章首交叉校验失败（候选{len(candidates)}个）；"
            "请检查结构索引、OCR标题和题解，禁止跨章替代。"
        )
    return candidates[0]


def resolve_boundaries(pages, number, sections=None):
    if type(number) is not int or not 1 <= number <= 64:
        raise ValueError("Hexagram number must be 1-64")
    sections = load_sections() if sections is None else sections
    entries = {}
    for entry in sections["hexagrams"]:
        key = entry["number"]
        if type(key) is not int or key in entries or not 1 <= key <= 64:
            raise ValueError("Duplicate or invalid hexagram number in structured index")
        if canonical_name(entry["name"]) != HEXAGRAM_NAMES[key - 1]:
            raise ValueError(f"Structured chapter name/number mismatch: {key}")
        entries[key] = entry
    if number not in entries or (number < 64 and number + 1 not in entries):
        raise ValueError("Required chapter missing from structured index")
    start = resolve_start(pages, entries[number])
    if number < 64:
        endpoint = entries[number + 1]
    else:
        # The final chapter ends at the first corroborated appendix, not EOF.
        appendices = sections.get("appendices", [])
        if not appendices:
            raise ValueError("Hexagram 64 requires a verified appendix boundary")
        endpoint = min(appendices, key=lambda item: item["start_pdf_page"])
    try:
        end = resolve_start(pages, endpoint, appendix=number == 64)
    except ValueError as exc:
        raise ValueError(f"《{entries[number]['name']}》结束边界《{endpoint['name']}》核验失败：{exc}") from exc
    if (end["pdf_page"], end["offset"]) <= (start["pdf_page"], start["offset"]):
        raise ValueError("Non-increasing chapter boundaries")
    if entries[number].get("end_pdf_page_inclusive") != end["pdf_page"]:
        raise ValueError("Structured chapter end page conflicts with the next verified heading")
    return {"start": start, "end_exclusive": end, "end_boundary_name": endpoint["name"]}
