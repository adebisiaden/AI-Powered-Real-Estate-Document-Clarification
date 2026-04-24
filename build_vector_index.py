#!/usr/bin/env python3
"""
build_vector_index.py

One-time offline script: downloads CUAD + ACORD datasets from HuggingFace,
embeds clause text using the Gemini Embedding API on Vertex AI, and uploads
the resulting index to GCS.

Run ONCE locally before deployment. Does NOT belong in the FastAPI backend.

Usage:
    python build_vector_index.py            # full run
    python build_vector_index.py --dry-run  # first 100 clauses only (for testing)
"""

import argparse
import json
import os
import re
import time
import uuid
from pathlib import Path

import numpy as np
from datasets import load_dataset
from dotenv import load_dotenv
from google.cloud import storage
from tqdm import tqdm
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

# ── Config ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent

# The real .env lives in contract-review-backend/
ENV_FILE = BASE_DIR / "contract-review-backend" / ".env"
load_dotenv(ENV_FILE)

# Resolve GOOGLE_APPLICATION_CREDENTIALS relative to the .env file's directory
_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if _creds:
    _p = Path(_creds)
    if not _p.is_absolute():
        _p = (ENV_FILE.parent / _p).resolve()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_p)

PROJECT_ID  = os.getenv("GCP_PROJECT_ID")
LOCATION    = os.getenv("GCP_LOCATION", "us-central1")
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

EMBED_MODEL      = "gemini-embedding-001"
BATCH_SIZE       = 20
BATCH_DELAY_SECS = 1.0
MIN_CHARS        = 20
MAX_CHARS        = 2000

# Local output files (project root)
OUT_CLAUSES = BASE_DIR / "cuad_acord_clauses.json"
OUT_VECTORS = BASE_DIR / "cuad_acord_vectors.npy"

# Checkpoint files — let the script resume if it crashes mid-way
CKPT_CLAUSES = BASE_DIR / "build_index_ckpt_clauses.json"
CKPT_VECTORS = BASE_DIR / "build_index_ckpt_vectors.npy"

# HuggingFace cache — reuse downloads across runs
HF_CACHE = BASE_DIR / "cuad_hf_cache"


# ── Dataset extraction ─────────────────────────────────────────────────────────

def extract_cuad() -> list[dict]:
    print("Downloading CUAD (theatticusproject/cuad-qa)...")
    ds = load_dataset(
        "theatticusproject/cuad-qa",
        split="train",
        cache_dir=str(HF_CACHE),
        trust_remote_code=True,
    )

    clauses = []
    for row in ds:
        answers = row.get("answers") or {}
        texts = answers.get("text", []) if isinstance(answers, dict) else []
        if not texts:
            continue  # negative example — clause not present in this contract

        clause_type = _cuad_question_to_label(row.get("question", ""))

        for text in texts:
            text = (text or "").strip()
            if text:
                clauses.append({
                    "id":     f"cuad_{uuid.uuid4().hex[:12]}",
                    "text":   text,
                    "type":   clause_type,
                    "source": "CUAD",
                })

    print(f"  → {len(clauses)} clauses extracted from CUAD")
    return clauses


def _cuad_question_to_label(question: str) -> str:
    """Extract the short clause-type name from a CUAD question string."""
    # Questions look like:
    #   Highlight the parts ... related to "Indemnification" that should ...
    m = re.search(r'related to ["\']([^"\']+)["\']', question, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return question.strip() or "Unknown"


def extract_acord() -> list[dict]:
    """
    ACORD uses BEIR format. The clause corpus lives in corpus.jsonl with
    fields: _id, text, title (title = clause category).
    We download that file directly from the HuggingFace dataset repo.
    """
    print("Downloading ACORD corpus (theatticusproject/acord)...")
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError as exc:
        print(f"  WARNING: huggingface_hub not installed — {exc}")
        print("  Skipping ACORD.")
        return []

    # Find corpus.jsonl — it may be in the root or a subdirectory
    try:
        all_files = list(list_repo_files("theatticusproject/acord", repo_type="dataset"))
    except Exception as exc:
        print(f"  WARNING: could not list ACORD repo files — {exc}")
        print("  Skipping ACORD.")
        return []

    # The data is bundled in a ZIP file in the repo
    zip_file = next(
        (f for f in all_files if f.lower().endswith(".zip")),
        None,
    )
    corpus_file = next(
        (f for f in all_files if Path(f).name == "corpus.jsonl"),
        None,
    )

    if not corpus_file and not zip_file:
        print(f"  WARNING: no corpus.jsonl or ZIP found. Files in repo: {all_files}")
        print("  Skipping ACORD.")
        return []

    # Helper to parse a corpus.jsonl file object
    def _parse_corpus(fileobj) -> list[dict]:
        results = []
        for line in fileobj:
            line = line.strip() if isinstance(line, str) else line.decode().strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (row.get("text") or "").strip()
            clause_type = (row.get("title") or row.get("type") or "Unknown").strip()
            if text:
                results.append({
                    "id":     f"acord_{row.get('_id', uuid.uuid4().hex[:12])}",
                    "text":   text,
                    "type":   clause_type,
                    "source": "ACORD",
                })
        return results

    clauses = []

    if corpus_file:
        # corpus.jsonl is directly in the repo
        print(f"  Found corpus at: {corpus_file}")
        try:
            local_path = hf_hub_download(
                repo_id="theatticusproject/acord",
                filename=corpus_file,
                repo_type="dataset",
                cache_dir=str(HF_CACHE),
            )
        except Exception as exc:
            print(f"  WARNING: could not download corpus.jsonl — {exc}")
            print("  Skipping ACORD.")
            return []
        with open(local_path, "r", encoding="utf-8") as f:
            clauses = _parse_corpus(f)

    elif zip_file:
        # corpus.jsonl is inside a ZIP archive
        import zipfile
        print(f"  Found ZIP: {zip_file} — extracting corpus.jsonl...")
        try:
            local_zip = hf_hub_download(
                repo_id="theatticusproject/acord",
                filename=zip_file,
                repo_type="dataset",
                cache_dir=str(HF_CACHE),
            )
        except Exception as exc:
            print(f"  WARNING: could not download ZIP — {exc}")
            print("  Skipping ACORD.")
            return []

        with zipfile.ZipFile(local_zip, "r") as zf:
            # Find corpus.jsonl anywhere inside the ZIP
            inner = next(
                (n for n in zf.namelist() if Path(n).name == "corpus.jsonl"),
                None,
            )
            if not inner:
                print(f"  WARNING: corpus.jsonl not found inside ZIP. Contents: {zf.namelist()[:30]}")
                print("  Skipping ACORD.")
                return []
            print(f"  Parsing {inner} from ZIP...")
            with zf.open(inner) as f:
                clauses = _parse_corpus(f)

    print(f"  → {len(clauses)} clauses extracted from ACORD")
    return clauses


# ── Cleaning ───────────────────────────────────────────────────────────────────

def clean_and_deduplicate(clauses: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in clauses:
        t = c["text"]
        if len(t) < MIN_CHARS or len(t) > MAX_CHARS:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(c)
    return out


# ── Checkpoint helpers ─────────────────────────────────────────────────────────

def save_checkpoint(clauses: list[dict], vectors: list[list[float]]):
    """Atomically persist progress after each batch."""
    with open(CKPT_CLAUSES, "w") as f:
        json.dump(clauses, f)
    np.save(CKPT_VECTORS, np.array(vectors, dtype=np.float32))


def load_checkpoint() -> tuple[list[dict], list[list[float]]]:
    """Return previously embedded clauses + vectors, or empty lists."""
    if CKPT_CLAUSES.exists() and CKPT_VECTORS.exists():
        with open(CKPT_CLAUSES) as f:
            clauses = json.load(f)
        vectors = np.load(CKPT_VECTORS).tolist()
        print(f"Resuming from checkpoint: {len(clauses)} clauses already embedded.")
        return clauses, vectors
    return [], []


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_all(
    clauses: list[dict],
    dry_run: bool = False,
) -> tuple[list[dict], list[list[float]]]:
    """
    Embed every clause using Gemini Embedding API (Vertex AI).
    Skips clauses already in the checkpoint.
    Returns (embedded_clauses, vectors) aligned by index.
    """
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)

    done_clauses, done_vectors = load_checkpoint()
    done_ids = {c["id"] for c in done_clauses}

    remaining = [c for c in clauses if c["id"] not in done_ids]

    if dry_run:
        remaining = remaining[:100]
        print(f"[--dry-run] Limiting to {len(remaining)} clauses.")

    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    error_count = 0

    for batch in tqdm(batches, desc="Embedding", unit="batch"):
        try:
            inputs = [
                TextEmbeddingInput(c["text"], "RETRIEVAL_DOCUMENT")
                for c in batch
            ]
            results = model.get_embeddings(inputs)
            for clause, result in zip(batch, results):
                done_clauses.append(clause)
                done_vectors.append(result.values)
        except Exception as exc:
            print(f"\n  ERROR on batch (id={batch[0]['id']}): {exc}")
            error_count += 1
            time.sleep(2)  # back off before next batch
            continue

        save_checkpoint(done_clauses, done_vectors)
        time.sleep(BATCH_DELAY_SECS)

    if error_count:
        print(f"  {error_count} batch(es) failed and were skipped.")

    return done_clauses, done_vectors


# ── GCS upload ─────────────────────────────────────────────────────────────────

def upload_to_gcs(local_path: Path, gcs_key: str):
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(gcs_key)
    blob.upload_from_filename(str(local_path))
    print(f"  ✓ gs://{BUCKET_NAME}/{gcs_key}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build CUAD + ACORD vector index for the RAG pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process only the first 100 clauses (end-to-end test)",
    )
    args = parser.parse_args()

    if not PROJECT_ID:
        raise SystemExit("ERROR: GCP_PROJECT_ID not set in .env")
    if not BUCKET_NAME:
        raise SystemExit("ERROR: GCS_BUCKET_NAME not set in .env")

    HF_CACHE.mkdir(exist_ok=True)

    # 1. Download + extract
    cuad_clauses  = extract_cuad()
    acord_clauses = extract_acord()

    cuad_count  = len(cuad_clauses)
    acord_count = len(acord_clauses)

    # 2. Combine, deduplicate, filter
    combined = clean_and_deduplicate(cuad_clauses + acord_clauses)
    print(f"\nAfter dedup/filter: {len(combined)} clauses "
          f"(CUAD: {cuad_count}, ACORD: {acord_count})")

    # 3. Embed
    print(f"\nEmbedding with {EMBED_MODEL} on Vertex AI ({LOCATION})...")
    embedded, vectors = embed_all(combined, dry_run=args.dry_run)

    if not embedded:
        raise SystemExit("No clauses were successfully embedded. Exiting.")

    # 4. Save locally
    print("\nSaving local files...")
    with open(OUT_CLAUSES, "w") as f:
        json.dump(embedded, f, indent=2)

    vec_array = np.array(vectors, dtype=np.float32)
    np.save(OUT_VECTORS, vec_array)

    print(f"  {OUT_CLAUSES.name}  — {len(embedded)} clauses")
    print(f"  {OUT_VECTORS.name}  — shape {vec_array.shape}")

    # 5. Upload to GCS
    print("\nUploading to GCS...")
    upload_to_gcs(OUT_CLAUSES, "embeddings/cuad_acord_clauses.json")
    upload_to_gcs(OUT_VECTORS, "embeddings/cuad_acord_vectors.npy")

    # 6. Summary
    print("\n" + "─" * 52)
    print("  BUILD COMPLETE")
    print(f"  CUAD clauses extracted   : {cuad_count:,}")
    print(f"  ACORD clauses extracted  : {acord_count:,}")
    print(f"  After dedup / filter     : {len(combined):,}")
    print(f"  Successfully embedded    : {len(embedded):,}")
    print(f"  Vector dimensions        : {vec_array.shape[1] if vec_array.ndim == 2 else 'n/a'}")
    print(f"  GCS destination          : gs://{BUCKET_NAME}/embeddings/")
    print("─" * 52)

    # Clean up checkpoint files only on a successful full run
    if not args.dry_run:
        CKPT_CLAUSES.unlink(missing_ok=True)
        CKPT_VECTORS.unlink(missing_ok=True)
        print("Checkpoint files removed.")


if __name__ == "__main__":
    main()
