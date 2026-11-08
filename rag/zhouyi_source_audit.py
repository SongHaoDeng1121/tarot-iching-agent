
# rag/zhouyi_source_audit.py

import re


def make_source_record(
    pdf_page,
    hexagram,
    origin,
    text,
    verified=True,
):
    """
    Create one traceable evidence record.

    origin:
        direct   = Hybrid Retrieval hit
        adjacent = Supplementary neighboring page
    """

    return {
        "pdf_page": int(pdf_page),
        "hexagram": hexagram,
        "origin": origin,
        "text": text,
        "verified": bool(verified),
    }


def register_source(registry, record):
    """Register only evidence actually passed to the LLM."""

    page = record["pdf_page"]

    if page < 1:
        raise ValueError("Invalid PDF page")

    if record["origin"] not in ("direct", "adjacent"):
        raise ValueError("Unknown evidence origin")

    if not record["text"].strip():
        return

    # Avoid duplicate records with the same provenance.
    key = (
        page,
        record["hexagram"],
        record["origin"],
    )

    for existing in registry:
        existing_key = (
            existing["pdf_page"],
            existing["hexagram"],
            existing["origin"],
        )
        if existing_key == key:
            return

    registry.append(record)


def audit_page_citations(answer, registry):
    """
    Check whether pages cited by DeepSeek were
    actually supplied as verified evidence.

    This checks page availability only.
    It does not verify the meaning of each quotation.
    """

    cited_pages = {
        int(page)
        for page in re.findall(
            r"PDF\s*第?\s*(\d+)\s*页",
            answer,
            flags=re.IGNORECASE,
        )
    }

    available_pages = {
        item["pdf_page"]
        for item in registry
        if item["verified"]
    }

    missing_pages = sorted(
        cited_pages - available_pages
    )

    return {
        "cited_pages": sorted(cited_pages),
        "available_pages": sorted(available_pages),
        "unsupported_pages": missing_pages,
        "passed": not missing_pages,
    }


def print_source_registry(registry):
    """Display all evidence sources transparently."""

    print("\n===== EVIDENCE SOURCE REGISTRY =====")

    for item in sorted(
        registry,
        key=lambda x: x["pdf_page"],
    ):
        status = (
            "已核实"
            if item["verified"]
            else "未核实"
        )

        print(
            f"PDF {item['pdf_page']} | "
            f"{item['hexagram']} | "
            f"{item['origin']} | "
            f"{status}"
        )


def print_citation_audit(answer, registry):

    report = audit_page_citations(
        answer,
        registry,
    )

    print("\n===== CITATION AUDIT =====")

    print(
        "Cited pages:",
        report["cited_pages"],
    )

    print(
        "Verified evidence pages:",
        report["available_pages"],
    )

    print(
        "Unsupported pages:",
        report["unsupported_pages"],
    )

    print(
        "Page citation check:",
        "PASS" if report["passed"] else "FAIL",
    )

    return report
