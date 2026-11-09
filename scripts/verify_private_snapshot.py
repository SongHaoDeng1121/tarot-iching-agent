"""Exercise full private snapshot restoration and RAG without printing source text.

GitHub transport is simulated from a local archive; --online calls existing
embedding query and DeepSeek APIs. It never uploads the knowledge snapshot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch


def verify(snapshot, online=False):
    archive = Path(snapshot).resolve()
    payload = archive.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    from rag.private_bundle import restore_private_bundle
    with tempfile.TemporaryDirectory(prefix="tarot-snapshot-e2e-") as temporary:
        environment = {
            "KNOWLEDGE_GITHUB_REPOSITORY": "fixture/private-data",
            "KNOWLEDGE_GITHUB_REF": "a" * 40,
            "KNOWLEDGE_GITHUB_PATH": "snapshots/test.tar.gz",
            "KNOWLEDGE_GITHUB_TOKEN": "github_pat_SYNTHETIC_TEST_ONLY",
            "KNOWLEDGE_BUNDLE_URL": "", "KNOWLEDGE_BUNDLE_SHA256": digest,
            "KNOWLEDGE_CACHE_DIR": temporary,
            "APP_RUNTIME_DIR": str(Path(temporary) / "runtime"),
        }
        metadata = MagicMock()
        metadata.__enter__.return_value = metadata
        metadata.status_code = 200
        metadata.json.return_value = {"private": True}
        download = MagicMock()
        download.__enter__.return_value = download
        download.status_code = 200
        download.iter_content.return_value = [payload]
        with patch.dict(os.environ, environment):
            with patch("requests.get", side_effect=[metadata, download]) as get:
                root = restore_private_bundle()
                downloads = get.call_count
            with patch("requests.get", side_effect=AssertionError("cached restart must not download")):
                cached = restore_private_bundle()
            from rag.knowledge_check import check_knowledge
            ready = check_knowledge()
            if not ready["ready"]:
                raise ValueError("Restored knowledge failed readiness")
            # Import RAG only after restore has established the private root.
            from engines.tarot_draw import make_three_card_spread
            from engines.yijing_cast import cast_hexagram
            from rag.answer import load_cards
            from rag.spread import prepare_exact_evidence, prepare_vector_evidence, build_spread_prompt, ask_deepseek, check_citations
            from rag.tarot_sources import greer_exact_evidence
            drawn = make_three_card_spread("恢复后的抽牌测试")
            cast = cast_hexagram()
            spread = {
                "question": "我可以如何反思自己的想法、感受与行动？",
                "spread_name": "Thoughts / Feelings / Actions",
                "cards": [
                    {"card_id": "the_magician", "orientation": "reversed", "position": "Thoughts"},
                    {"card_id": "queen_of_pentacles", "orientation": "upright", "position": "Feelings"},
                    {"card_id": "ten_of_pentacles", "orientation": "reversed", "position": "Actions"},
                ],
            }
            evidence = prepare_exact_evidence(spread, load_cards())
            greer = greer_exact_evidence("the_magician", "reversed")
            summary = {
                "transport": "simulated_private_github_download",
                "snapshot_bytes": len(payload), "sha256": digest,
                "download_requests": downloads, "cached_restart": root == cached,
                "readiness": ready,
                "drawn_unique_cards": len({item["card_id"] for item in drawn["cards"]}),
                "cast_lines": len(cast["line_values_bottom_to_top"]),
                "pollack_exact_count": sum(item["source_id"] == "pollack_78_degrees" for item in evidence),
                "greer_exact_count": sum(item["source_id"] == "greer_tarot_reversals" for item in evidence),
                "greer_magician_reversed_pages": greer["pages"],
                "source_references": [{"id": item["id"], "pages": item["pages"]} for item in evidence],
                "online": online,
            }
            if online:
                semantic = prepare_vector_evidence(spread, top_k=2)
                from rag.hybrid_zhouyi import hybrid_search
                zhouyi = hybrid_search("为什么讼卦九二不克讼？", top_k=3)
                answer = ask_deepseek(build_spread_prompt(spread, evidence, semantic))
                invalid, missing = check_citations(answer, evidence, semantic)
                summary.update({
                    "tarot_hybrid_results": len(semantic),
                    "tarot_hybrid_sources": sorted({item["source_id"] for item in semantic}),
                    "zhouyi_top": {key: zhouyi[0].get(key) for key in ("id", "hexagram_name", "pdf_page")},
                    "deepseek_answer_chars": len(answer),
                    "unknown_citations": invalid, "uncited_exact": missing,
                    "generation_citation_audit_passed": not invalid and not missing,
                })
            from streamlit.testing.v1 import AppTest
            os.environ["APP_ACCESS_PASSWORD"] = "SYNTHETIC-ACCESS-PASSWORD-FOR-TEST"
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "cloud_app.py"))
            app.session_state["_authorized"] = True
            app.run(timeout=60)
            summary["startup_exceptions"] = len(app.exception)
            summary["startup_errors"] = len(app.error)
            summary["startup_question_inputs"] = len(app.text_area)
            if app.exception or app.error:
                raise ValueError("Restored Streamlit startup failed")
            summary["end_to_end_passed"] = summary.get("generation_citation_audit_passed", True)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    result = verify(args.snapshot, online=args.online)
    if not result["end_to_end_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
