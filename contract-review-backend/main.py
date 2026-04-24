import io
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
from pydantic import BaseModel
from PyPDF2 import PdfReader

import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
from google import genai as genai_sdk
from google.genai import types as genai_types

# ── Config ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if _creds:
    _p = Path(_creds)
    if not _p.is_absolute():
        _p = (BASE_DIR / _p).resolve()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_p)

PROJECT_ID   = os.getenv("GCP_PROJECT_ID")
LOCATION     = os.getenv("GCP_LOCATION", "us-central1")
BUCKET_NAME  = os.getenv("GCS_BUCKET_NAME")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBED_MODEL  = "gemini-embedding-001"

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES   = 20 * 1024 * 1024  # 20 MB
CHUNK_WORDS        = 1500
OVERLAP_WORDS      = 200
TOP_K              = 10

# Vertex AI SDK (embeddings)
vertexai.init(project=PROJECT_ID, location=LOCATION)
_embed_model: TextEmbeddingModel = TextEmbeddingModel.from_pretrained(EMBED_MODEL)

# google-genai client using Vertex AI backend (text generation)
_genai_client = genai_sdk.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# Embeddings loaded once at startup from GCS
_clauses: list[dict] = []
_vectors: Optional[np.ndarray] = None

# All 41 CUAD clause types the prompt checks for
CLAUSE_TYPES = [
    "Parties", "Effective Date", "Expiration Date", "Renewal Term",
    "Notice Period to Terminate Renewal", "Governing Law", "Most Favored Nation",
    "Non-Compete", "Exclusivity", "No-Solicit of Customers", "No-Solicit of Employees",
    "Non-Disparagement", "Limitation of Liability", "Liability Cap", "Liquidated Damages",
    "Warranty Duration", "IP Ownership Assignment", "Joint IP Ownership", "License Grant",
    "IP Restriction", "Audit Rights", "Uncapped Liability", "Cap on Liability",
    "Termination for Convenience", "Change of Control", "Anti-Assignment",
    "Revenue/Profit Sharing", "Price Restriction", "Minimum Commitment",
    "Volume Restriction", "Insurance", "Covenant Not to Sue", "Third Party Beneficiary",
    "Post-Term Obligations", "Indemnification", "Confidentiality",
    "Data Breach Notification", "Dispute Resolution", "Source Code Escrow",
    "Affiliate License Grant", "Affiliate License Restriction",
]

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Contract Review API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup: load CUAD/ACORD embeddings from GCS ──────────────────────────────

@app.on_event("startup")
async def load_embeddings():
    global _clauses, _vectors

    if not BUCKET_NAME:
        print("WARNING: GCS_BUCKET_NAME not set — RAG disabled")
        return

    print("Loading CUAD/ACORD embeddings from GCS...")
    try:
        gcs    = storage.Client(project=PROJECT_ID) if PROJECT_ID else storage.Client()
        bucket = gcs.bucket(BUCKET_NAME)

        # Vectors (.npy) — write to temp file because np.load needs a path
        with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as tmp:
            bucket.blob("embeddings/cuad_acord_vectors.npy").download_to_file(tmp)
            tmp_path = tmp.name
        _vectors = np.load(tmp_path).astype(np.float32)
        os.unlink(tmp_path)

        # Clause metadata (.json)
        raw      = bucket.blob("embeddings/cuad_acord_clauses.json").download_as_bytes()
        _clauses = json.loads(raw)

        print(f"Loaded {len(_clauses):,} clauses  |  vector dim: {_vectors.shape[1]}")
    except Exception as exc:
        print(f"ERROR loading embeddings from GCS: {exc}")
        print("Server will start but /analyze will return 503 until embeddings load.")


# ── Schemas ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    text: str


# ── File helpers (unchanged from Phase 2) ─────────────────────────────────────

def _original_filename(upload: UploadFile) -> str:
    name = (upload.filename or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Filename is required")
    return Path(name).name


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _validate_type(filename: str) -> None:
    ext = _extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: PDF, DOCX. Got: {ext or '(none)'}",
        )


def _extract_text_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        parts  = [p for page in reader.pages if (p := page.extract_text())]
        return "\n".join(parts).strip()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read PDF: {exc!s}") from exc


def _extract_text_docx(content: bytes) -> str:
    try:
        doc   = Document(io.BytesIO(content))
        parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(parts).strip()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read DOCX: {exc!s}") from exc


def _extract_text(content: bytes, filename: str) -> str:
    ext = _extension(filename)
    if ext == ".pdf":
        return _extract_text_pdf(content)
    if ext == ".docx":
        return _extract_text_docx(content)
    raise HTTPException(status_code=400, detail="Unsupported file type")


def _upload_to_gcs(content: bytes, dest_blob: str, content_type: str) -> None:
    if not BUCKET_NAME:
        raise HTTPException(status_code=500, detail="GCS_BUCKET_NAME is not configured")
    try:
        gcs    = storage.Client(project=PROJECT_ID) if PROJECT_ID else storage.Client()
        bucket = gcs.bucket(BUCKET_NAME)
        bucket.blob(dest_blob).upload_from_string(content, content_type=content_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GCS upload failed: {exc!s}") from exc


def _mime_for_filename(filename: str) -> str:
    return (
        "application/pdf"
        if _extension(filename) == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# ── RAG pipeline ───────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + CHUNK_WORDS]))
        i += CHUNK_WORDS - OVERLAP_WORDS
    return chunks


def _embed_chunks(chunks: list[str]) -> np.ndarray:
    inputs  = [TextEmbeddingInput(c, "RETRIEVAL_QUERY") for c in chunks]
    results = _embed_model.get_embeddings(inputs)
    return np.array([r.values for r in results], dtype=np.float32)


def _cosine_sim(query: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    q     = query / (np.linalg.norm(query) + 1e-9)
    norms = np.linalg.norm(corpus, axis=1, keepdims=True) + 1e-9
    return (corpus / norms) @ q


def _retrieve_top_clauses(chunk_vectors: np.ndarray) -> list[dict]:
    # Score every corpus clause against every chunk; keep max score per clause
    all_scores = np.stack([_cosine_sim(v, _vectors) for v in chunk_vectors])
    scores     = np.max(all_scores, axis=0)
    ranked     = np.argsort(scores)[::-1]

    seen_types, top = set(), []
    for idx in ranked:
        clause = _clauses[int(idx)]
        ctype  = clause.get("type", "Unknown")
        if ctype not in seen_types:
            seen_types.add(ctype)
            top.append(clause)
        if len(top) >= TOP_K:
            break
    return top


def _build_prompt(contract_text: str, similar_clauses: list[dict]) -> str:
    examples = "\n\n".join(
        f"Type: {c.get('type', 'Unknown')}\nExample: {c.get('text', '')[:300]}"
        for c in similar_clauses
    )
    clause_types_str = ", ".join(CLAUSE_TYPES)

    return f"""You are a legal contract review assistant trained on expert-annotated legal datasets.

Here are real lawyer-labeled example clauses from our legal dataset for reference:

{examples}

Using these examples as reference, analyze the following contract and return a JSON object with exactly these three keys:

1. "summary": Plain English summary, 5-7 sentences, no legal jargon.

2. "risks": List of risk items, each with:
   - "clause": clause type name
   - "risk_level": exactly "High", "Medium", or "Low"
   - "reason": one sentence explanation
   Flag as High if: uncapped liability, worldwide non-compete over 1 year, unlimited indemnification, auto-renewal with short notice window.
   Flag as Medium if: broad IP assignment, one-sided termination, aggressive payment penalties.
   Flag as Low if: standard governing law, normal confidentiality, typical warranty terms.

3. "clauses": Check for ALL of these clause types and return found status for each: {clause_types_str}
   For each return: {{"clause_type": "...", "text": "exact extracted text or empty string", "found": true or false}}

You MUST identify ALL risks present in the contract. Do not stop after finding one risk. Check every clause type for risk. Return at minimum all High and Medium risk items found.

Return ONLY valid JSON. No markdown. No extra text.

Contract to analyze:
{contract_text}"""


def _run_rag_pipeline(text: str) -> dict:
    if _vectors is None or not _clauses:
        raise HTTPException(status_code=503, detail="Service starting up, retry in 30s")

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Contract text is empty")

    # Step 1 — chunk
    chunks = _chunk_text(text)

    # Step 2 — embed chunks
    try:
        chunk_vectors = _embed_chunks(chunks)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc!s}") from exc

    # Step 3 — retrieve top CUAD/ACORD matches
    similar = _retrieve_top_clauses(chunk_vectors)

    # Step 4 — build prompt
    prompt = _build_prompt(text, similar)

    # Step 5 — call Gemini Pro
    try:
        response = _genai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0),
        )
        raw = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Analysis failed, please retry")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini call failed: {exc!s}") from exc


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "embeddings_loaded": _vectors is not None,
        "clause_count": len(_clauses),
    }


@app.post("/analyze")
async def analyze(data: AnalyzeRequest):
    if not data.text or not data.text.strip():
        raise HTTPException(status_code=400, detail="Contract text is empty")
    return _run_rag_pipeline(data.text)


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = _original_filename(file)
    _validate_type(filename)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    text = _extract_text(content, filename)

    ext       = _extension(filename)
    blob_name = f"uploads/{uuid.uuid4()}{ext}"
    _upload_to_gcs(content, blob_name, _mime_for_filename(filename))

    analysis = _run_rag_pipeline(text)

    return {
        "filename": filename,
        "status":   "success",
        "text":     text,
        "analysis": analysis,
    }
