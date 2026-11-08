# Adding a Tarot reference book

## Current reusable entry points

Book ingestion is configured under `configs/books/`. The Greer integration is the reference implementation:

```bash
.venv/bin/python -m rag.ingest_book \
  --config configs/books/greer_reversals.yaml \
  --stage extract

.venv/bin/python -m rag.ingest_book \
  --config configs/books/greer_reversals.yaml \
  --stage structure

.venv/bin/python -m rag.ingest_book \
  --config configs/books/greer_reversals.yaml \
  --stage chunk

.venv/bin/python -m rag.ingest_book \
  --config configs/books/greer_reversals.yaml \
  --stage index
```

The last command reports the number of chunks and approximate token volume, then pauses. Add `--allow-paid-api` only after reviewing that estimate and deciding to call the configured remote embedding service.

`--stage all` runs every local phase in order and applies the same paid-API gate before indexing.

## Review before indexing

Inspect these outputs in order:

1. `data/extracted/<source>_pages.jsonl`: every PDF page, extraction method, printed page mapping, and warnings.
2. `data/structured/<source>_sections.json`: heading offsets and exclusive card boundaries.
3. `reports/rag/<source>_boundaries.md`: all 78 card transitions and low-confidence items.
4. `data/chunks/<source>_chunks.jsonl`: deterministic IDs, source/card/orientation metadata, content hashes, and page ranges.

Do not index if a card has a missing upright or reversed boundary. The ingestion command intentionally stops in that state.

## Register or disable a source

Runtime sources are defined in `configs/tarot_sources.yaml`. A source can be disabled by setting `enabled: false`; no vector data must be deleted.

For a temporary Pollack-only regression run:

```bash
TAROT_SOURCE_REGISTRY=configs/tarot_sources_pollack_only.yaml \
  .venv/bin/python -m rag.search
```

This is also the rollback procedure for the Greer integration. The existing Pollack and I Ching collections remain intact.

## Add a future book

1. Add a new YAML file in `configs/books/` with a unique `source_id`, new Chroma collection, source metadata, output paths, page calibration, and chunk limits.
2. Reuse the canonical 78-card catalog in `rag/tarot_catalog.py`.
3. If the book uses a different structure, add a parser strategy in `rag/ingest_book.py`; do not copy the ingestion script.
4. Run extraction and structure detection first, visually inspect uncertain headings, then run chunking.
5. Add the source to `configs/tarot_sources.yaml` only after its independent collection and evaluation pass.
6. Run `python -m unittest discover -s tests -v` and the retrieval evaluation before enabling the source in the web application.

## Resume and verification

Indexing uses stable chunk IDs and content hashes. Re-running the index skips unchanged records and upserts changed content. Successful and failed batches are appended to the configured index log.

Verify counts without changing data:

```bash
.venv/bin/python - <<'PY'
import chromadb
db = chromadb.PersistentClient(path="storage/chroma")
for collection in db.list_collections():
    print(collection.name, collection.count())
PY
```

Run the Greer retrieval evaluation with vectors:

```bash
.venv/bin/python -m rag.evaluate_tarot --online
```

The evaluation writes both JSON and Markdown reports under `reports/rag/`.

## Copyright and repository hygiene

Raw PDFs, extracted Greer page text, chunks, the local Chroma store, secrets, and generated readings are ignored by `.gitignore`. Do not publish those artifacts. The answer layer should display source metadata and short paraphrases, not full book passages.
