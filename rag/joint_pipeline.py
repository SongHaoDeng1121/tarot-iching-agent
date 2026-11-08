"""Single-question orchestration for Tarot + I Ching + Fusion.

The adapter is intentionally injected: the existing web_app.py owns how it
calls its Tarot interpreter. This module never imports Streamlit.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

from engines.tarot_draw import make_three_card_spread
from rag.reading_zhouyi import run_reading
from rag.fusion import fuse_readings

ROOT = Path(__file__).resolve().parents[1]
READINGS_DIR = ROOT / "data/readings"


def run_joint_reading(
    question: str,
    tarot_interpreter: Callable[[str, Any], dict],
    *,
    line_values: list[int] | None = None,
    tarot_drawer: Callable[[], Any] = make_three_card_spread,
    fusion_dry_run: bool = False,
    save: bool = True,
) -> dict:
    """Draw Tarot and cast I Ching ONCE; interpretations never reroll.

    tarot_interpreter(question, spread) -> {
      "answer" or "interpretation": str, "sources": list, optional fields...
    }
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty")

    spread = tarot_drawer()
    tarot = tarot_interpreter(question, spread)
    if not isinstance(tarot, dict):
        raise TypeError("tarot_interpreter must return a dict")
    tarot = {**tarot, "spread": spread}

    yijing = run_reading(question, line_values=line_values, dry_run=False)
    fusion = fuse_readings(question, tarot, yijing, dry_run=fusion_dry_run)
    result = {
        "question": question,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tarot": tarot,
        "yijing": yijing,
        "fusion": fusion["answer"],
    }
    if save and not fusion_dry_run:
        READINGS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = READINGS_DIR / f"joint_{stamp}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        result["saved_path"] = str(path)
    return result
