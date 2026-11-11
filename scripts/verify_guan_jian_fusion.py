"""Exercise the actual web orchestration with the reported cast, without saving real history.

--online invokes Tarot, I Ching and Fusion generation and may incur API costs.
Outputs only provenance/audit metadata, never full book text or credentials.
"""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from unittest.mock import patch

from engines.yijing_cast import build_cast_result
from rag.runtime_data import ROOT


def run(online=False):
    from rag.reading_zhouyi import run_reading
    question = "我目前遇到的困难，应该如何调整行动方式？"
    values = [8, 8, 6, 8, 7, 7]
    if not online:
        result = run_reading(question, line_values=values, dry_run=True, save=False)
        return {"cast": {"original": 20, "changed": 53, "moving": ["六三"]}, "sources": result["sources"], "online": False}
    from streamlit.testing.v1 import AppTest
    spread = {
        "question": question, "spread_name": "Thoughts / Feelings / Actions",
        "cards": [
            {"card_id": "five_of_pentacles", "orientation": "upright", "position": "Thoughts"},
            {"card_id": "king_of_cups", "orientation": "upright", "position": "Feelings"},
            {"card_id": "four_of_pentacles", "orientation": "upright", "position": "Actions"},
        ],
    }
    with tempfile.TemporaryDirectory(prefix="guan-jian-fusion-") as temporary, patch.dict(os.environ, {"APP_RUNTIME_DIR": temporary}):
        app = AppTest.from_file(str(ROOT / "web_app.py"))
        app.session_state["joint_record"] = {
            "kind": "prepared", "question": question,
            "tarot_spread": spread, "cast": build_cast_result(values),
        }
        app.session_state["question_input"] = question
        app.run(timeout=60)
        button = next(button for button in app.button if button.label == "开始双系统解读与 Fusion 综合分析")
        button.click().run(timeout=240)
        if app.exception or app.error:
            raise RuntimeError("Web Fusion reading failed; inspect the local app with the same six line values")
        completed = app.session_state["joint_record"]
        if not completed.get("fusion"):
            raise RuntimeError("Web orchestration did not finish Fusion")
        cast = completed["cast"]
        if cast["line_values_bottom_to_top"] != values:
            raise RuntimeError("Observed cast changed during generation")
        yijing = completed["yijing"]
        tarot = completed["tarot"]
        # Fusion should not create a new page citation outside either supplied
        # source registry. This supplements, rather than replaces, existing audits.
        provided = {page for source in (*tarot["sources"], *yijing["sources"]) for page in source.get("pages", [])}
        cited = {int(page) for page in re.findall(r"PDF\s*第?\s*(\d+)\s*页?", completed["fusion"], re.I)}
        return {
            "online": True, "workflow": "web_app.generate_joint -> Tarot + I Ching -> Fusion",
            "cast": {"original": cast["original_hexagram"]["number"], "changed": cast["changed_hexagram"]["number"], "moving": cast["moving_line_labels"]},
            "tarot_sources": tarot["sources"], "tarot_validation": tarot["validation"],
            "yijing_sources": yijing["sources"], "yijing_citation_audit": yijing["citation_audit"],
            "fusion_characters": len(completed["fusion"]),
            "fusion_cited_pages": sorted(cited), "fusion_unsupported_pages": sorted(cited - provided),
            "startup_errors": len(app.error), "startup_exceptions": len(app.exception),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.online)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.online and (
        result["tarot_validation"]["unknown_source_ids"]
        or result["tarot_validation"]["exact_sources_not_cited"]
        or not result["yijing_citation_audit"]["passed"]
        or result["fusion_unsupported_pages"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
