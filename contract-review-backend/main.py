import hashlib
import io
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.cloud import storage
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
from PyPDF2 import PdfReader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

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

PROJECT_ID        = os.getenv("GCP_PROJECT_ID")
LOCATION          = os.getenv("GCP_LOCATION", "us-central1")
BUCKET_NAME       = os.getenv("GCS_BUCKET_NAME")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBED_MODEL       = "gemini-embedding-001"
FIREBASE_PROJECT  = os.getenv("FIREBASE_PROJECT_ID", "contract-review-1e807")

_auth_request = google_requests.Request()

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
_gemini_cache_name: Optional[str] = None

# ── Response schema (structured output) ────────────────────────────────────────
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause":     {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["High", "Medium", "Low"]},
                    "reason":     {"type": "string"},
                },
                "required": ["clause", "risk_level", "reason"],
            },
        },
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_type": {"type": "string"},
                    "text":        {"type": "string"},
                    "found":       {"type": "boolean"},
                },
                "required": ["clause_type", "text", "found"],
            },
        },
    },
    "required": ["summary", "risks", "clauses"],
}

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

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Audit logger — emits one JSON line per security-relevant event
logging.basicConfig(level=logging.INFO, format="%(message)s")
_audit = logging.getLogger("audit")

def _log(event: str, **kwargs):
    _audit.info(json.dumps({"event": event, "ts": datetime.now(timezone.utc).isoformat(), **kwargs}))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://contract-review-frontend-phi.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup: load CUAD/ACORD embeddings from GCS ──────────────────────────────

@app.on_event("startup")
async def check_bucket_security():
    if not BUCKET_NAME:
        return
    try:
        gcs    = storage.Client(project=PROJECT_ID) if PROJECT_ID else storage.Client()
        bucket = gcs.bucket(BUCKET_NAME)
        bucket.reload()
        if not bucket.iam_configuration.uniform_bucket_level_access_enabled:
            print(f"SECURITY WARNING: Uniform bucket-level access is OFF on gs://{BUCKET_NAME}")
            print(f"  Fix: gcloud storage buckets update gs://{BUCKET_NAME} --uniform-bucket-level-access")
        else:
            print(f"[security] Uniform bucket-level access: OK")
        if bucket.iam_configuration.public_access_prevention != "enforced":
            print(f"SECURITY WARNING: Public access prevention is not enforced on gs://{BUCKET_NAME}")
            print(f"  Fix: gcloud storage buckets update gs://{BUCKET_NAME} --public-access-prevention=enforced")
        else:
            print(f"[security] Public access prevention: OK")
    except Exception as exc:
        print(f"Could not verify bucket security settings: {exc}")


@app.on_event("startup")
async def load_embeddings():
    global _clauses, _vectors, _gemini_cache_name

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
        return

    # Build Gemini context cache with all CUAD/ACORD examples (one per clause type)
    try:
        by_type: dict = {}
        for c in _clauses:
            t = c.get("type", "Unknown")
            if t not in by_type:
                by_type[t] = c

        examples_text = "\n\n".join(
            f"Type: {c.get('type','Unknown')}\nExample: {c.get('text','')[:400]}"
            for c in by_type.values()
        )
        clause_types_str = ", ".join(CLAUSE_TYPES)

        cached_system = f"""You are a legal contract review assistant trained on expert-annotated legal datasets (CUAD/ACORD).

Here are lawyer-labeled example clauses from our dataset for reference:

{examples_text}

When given a contract, analyze it and identify:

1. A plain-English summary (5-7 sentences, no jargon).

2. All risk items — each with a clause name, risk_level (High/Medium/Low), and one-sentence reason.
   Flag as High if: uncapped liability, worldwide non-compete over 1 year, unlimited indemnification, auto-renewal with short notice window.
   Flag as Medium if: broad IP assignment, one-sided termination, aggressive payment penalties.
   Flag as Low if: standard governing law, normal confidentiality, typical warranty terms.
   You MUST find ALL risks. Do not stop after the first.

3. Status for ALL of these clause types — {clause_types_str}
   For each: whether it was found, and the exact extracted text (or empty string).
"""

        cache = _genai_client.caches.create(
            model=GEMINI_MODEL,
            config=genai_types.CreateCachedContentConfig(
                contents=[genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=cached_system)],
                )],
                ttl="3600s",
                display_name="cuad-acord-system-prompt",
            ),
        )
        _gemini_cache_name = cache.name
        print(f"Gemini context cache created: {_gemini_cache_name}")
    except Exception as exc:
        print(f"Context caching unavailable (will use standard RAG): {exc}")
        _gemini_cache_name = None


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
    query  = np.nan_to_num(query.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    corpus = np.nan_to_num(corpus.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)

    q_norm  = np.linalg.norm(query)
    c_norms = np.linalg.norm(corpus, axis=1)

    if q_norm == 0:
        return np.zeros(corpus.shape[0], dtype=np.float32)

    safe_c_norms = np.where(c_norms == 0, 1e-9, c_norms)
    return (corpus @ query) / (safe_c_norms * q_norm)


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
    """Fallback prompt used when context cache is unavailable."""
    examples = "\n\n".join(
        f"Type: {c.get('type', 'Unknown')}\nExample: {c.get('text', '')[:300]}"
        for c in similar_clauses
    )
    clause_types_str = ", ".join(CLAUSE_TYPES)

    return f"""You are a legal contract review assistant trained on expert-annotated legal datasets.

Here are real lawyer-labeled example clauses from our legal dataset for reference:

{examples}

Analyze the following contract. Provide a plain-English summary (5-7 sentences), identify all risks (clause, risk_level of High/Medium/Low, reason), and check for these clause types: {clause_types_str}

Flag as High if: uncapped liability, worldwide non-compete over 1 year, unlimited indemnification, auto-renewal with short notice window.
Flag as Medium if: broad IP assignment, one-sided termination, aggressive payment penalties.
Flag as Low if: standard governing law, normal confidentiality, typical warranty terms.
You MUST identify ALL risks. Do not stop after the first.

Contract to analyze:
{contract_text}"""


import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)

def _call_gemini(contract_text: str, similar_clauses: list[dict]) -> dict:
    if _gemini_cache_name:
        # Context cache has all examples — just send the contract text
        prompt = f"Analyze this contract:\n\n{contract_text}"
        config = genai_types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            cached_content=_gemini_cache_name,
        )
    else:
        prompt = _build_prompt(contract_text, similar_clauses)
        config = genai_types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        )
    try:
        response = _genai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini call failed: {e}")
        return {"clauses": [], "risks": [], "summary": ""}


def _merge_results(results: list[dict]) -> dict:
    # Merge risks — deduplicate by clause name, keep highest risk level
    risk_map = {}
    risk_order = {"High": 3, "Medium": 2, "Low": 1}
    for r in results:
        for risk in r.get("risks", []):
            clause = risk.get("clause", "")
            level = risk.get("risk_level", "Low")
            if clause not in risk_map or risk_order.get(level, 0) > risk_order.get(risk_map[clause]["risk_level"], 0):
                risk_map[clause] = risk
    merged_risks = list(risk_map.values())

    # Merge clauses — if any chunk found a clause, mark it found
    clause_map = {}
    for r in results:
        for clause in r.get("clauses", []):
            ctype = clause.get("clause_type", "")
            if ctype not in clause_map or clause.get("found") and not clause_map[ctype].get("found"):
                clause_map[ctype] = clause
    merged_clauses = list(clause_map.values())

    # Use the first non-empty summary
    summary = next(
        (r["summary"] for r in results if r.get("summary")),
        "No summary available"
    )

    return {
        "summary": summary,
        "risks": merged_risks,
        "clauses": merged_clauses,
    }


MAX_GEMINI_CHARS = 900_000  # ~225k tokens, well within Gemini 2.5 Flash's 1M limit


def _run_rag_pipeline(text: str) -> dict:
    import time
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Contract text is empty")

    t0 = time.time()

    if _gemini_cache_name:
        # Context cache holds all CUAD/ACORD examples — skip embedding entirely
        result = _call_gemini(text[:MAX_GEMINI_CHARS], [])
        print(f"[TIMING] Gemini call with context cache: {time.time() - t0:.2f}s")
        return result

    # Fallback: dynamic RAG (embed → retrieve → generate)
    if _vectors is None or not _clauses:
        raise HTTPException(status_code=503, detail="Service starting up, retry in 30s")

    sample = text[:CHUNK_WORDS * 6]
    try:
        sample_vector = _embed_chunks([sample])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc!s}") from exc
    similar = _retrieve_top_clauses(sample_vector)
    result  = _call_gemini(text[:MAX_GEMINI_CHARS], similar)
    print(f"[TIMING] RAG pipeline (no cache): {time.time() - t0:.2f}s")
    return result


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _verify_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:]
    try:
        payload = google_id_token.verify_firebase_token(
            token, _auth_request, audience=FIREBASE_PROJECT
        )
        return payload["sub"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


# ── GCS history storage ─────────────────────────────────────────────────────────

def _gcs_client():
    return storage.Client(project=PROJECT_ID) if PROJECT_ID else storage.Client()


def _file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _cache_blob(user_id: str, file_hash: str) -> str:
    return f"users/{user_id}/cache/{file_hash}.json"


def _get_cached(user_id: str, file_hash: str) -> Optional[dict]:
    try:
        bucket = _gcs_client().bucket(BUCKET_NAME)
        ref    = json.loads(bucket.blob(_cache_blob(user_id, file_hash)).download_as_bytes())
        record = json.loads(bucket.blob(f"users/{user_id}/analyses/{ref['record_id']}.json").download_as_bytes())
        return record
    except Exception:
        return None


def _save_analysis(user_id: str, filename: str, file_hash: str, analysis: dict) -> tuple:
    record_id = str(uuid.uuid4())
    record = {
        "record_id":  record_id,
        "user_id":    user_id,
        "filename":   filename,
        "file_hash":  file_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis":   analysis,
    }
    bucket = _gcs_client().bucket(BUCKET_NAME)
    bucket.blob(f"users/{user_id}/analyses/{record_id}.json").upload_from_string(
        json.dumps(record), content_type="application/json"
    )
    bucket.blob(_cache_blob(user_id, file_hash)).upload_from_string(
        json.dumps({"record_id": record_id}), content_type="application/json"
    )
    return record_id, record


def _list_analyses(user_id: str) -> list:
    blobs = _gcs_client().bucket(BUCKET_NAME).list_blobs(
        prefix=f"users/{user_id}/analyses/"
    )
    results = []
    for blob in blobs:
        try:
            data  = json.loads(blob.download_as_bytes())
            risks = data.get("analysis", {}).get("risks", [])
            level = (
                "High"   if any(r.get("risk_level") == "High"   for r in risks) else
                "Medium" if any(r.get("risk_level") == "Medium" for r in risks) else
                "Low"
            )
            results.append({
                "record_id":  data["record_id"],
                "filename":   data["filename"],
                "created_at": data["created_at"],
                "risk_level": level,
            })
        except Exception:
            continue
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results


def _get_analysis(user_id: str, record_id: str) -> dict:
    blob_name = f"users/{user_id}/analyses/{record_id}.json"
    try:
        return json.loads(
            _gcs_client().bucket(BUCKET_NAME).blob(blob_name).download_as_bytes()
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Record not found")


def _delete_analysis(user_id: str, record_id: str) -> None:
    blob_name = f"users/{user_id}/analyses/{record_id}.json"
    try:
        bucket = _gcs_client().bucket(BUCKET_NAME)
        blob   = bucket.blob(blob_name)
        # Read record first to get file_hash for cache invalidation
        try:
            record    = json.loads(blob.download_as_bytes())
            file_hash = record.get("file_hash")
            if file_hash:
                bucket.blob(_cache_blob(user_id, file_hash)).delete()
        except Exception:
            pass
        blob.delete()
    except Exception:
        raise HTTPException(status_code=404, detail="Record not found")


# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse(msg: str) -> str:
    return f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"

def _sse_result(data: dict) -> str:
    return f"data: {json.dumps({'type': 'done', **data})}\n\n"

def _sse_error(msg: str) -> str:
    return f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"


async def _bg_save(user_id: str, filename: str, file_hash: str, record_id: str, analysis: dict):
    def _do():
        record = {
            "record_id":  record_id,
            "user_id":    user_id,
            "filename":   filename,
            "file_hash":  file_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "analysis":   analysis,
        }
        try:
            bucket = _gcs_client().bucket(BUCKET_NAME)
            bucket.blob(f"users/{user_id}/analyses/{record_id}.json").upload_from_string(
                json.dumps(record), content_type="application/json"
            )
            bucket.blob(_cache_blob(user_id, file_hash)).upload_from_string(
                json.dumps({"record_id": record_id}), content_type="application/json"
            )
        except Exception as e:
            print(f"Background save failed: {e}")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _do)


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


@app.post("/analyse/guest")
@limiter.limit("5/minute;20/hour")
async def analyse_guest(request: Request, file: UploadFile = File(...)):
    filename = _original_filename(file)
    _validate_type(filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max: {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    ip = request.client.host if request.client else "unknown"
    _log("analyse_start", actor="guest", ip=ip, filename=filename, size=len(content))
    t0       = time.time()
    text     = _extract_text(content, filename)
    analysis = _run_rag_pipeline(text)
    _log("analyse_complete", actor="guest", ip=ip, filename=filename, duration_ms=int((time.time()-t0)*1000))
    return {"filename": filename, "status": "success", "analysis": analysis}


@app.post("/analyse/guest/stream")
@limiter.limit("5/minute;20/hour")
async def analyse_guest_stream(request: Request, file: UploadFile = File(...)):
    filename = _original_filename(file)
    _validate_type(filename)
    content  = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max: {MAX_UPLOAD_BYTES // (1024*1024)} MB")

    async def generate():
        loop = asyncio.get_running_loop()
        try:
            yield _sse("Reading document…")
            text = await loop.run_in_executor(_executor, lambda: _extract_text(content, filename))

            if _gemini_cache_name:
                yield _sse("Analysing with AI…")
                analysis = await loop.run_in_executor(
                    _executor, lambda: _call_gemini(text[:MAX_GEMINI_CHARS], [])
                )
            else:
                yield _sse("Finding relevant clauses…")
                def _rag():
                    vec = _embed_chunks([text[:CHUNK_WORDS * 6]])
                    return _retrieve_top_clauses(vec)
                similar = await loop.run_in_executor(_executor, _rag)
                yield _sse("Analysing with AI…")
                analysis = await loop.run_in_executor(
                    _executor, lambda: _call_gemini(text[:MAX_GEMINI_CHARS], similar)
                )

            yield _sse_result({"filename": filename, "status": "success", "analysis": analysis})

        except HTTPException as e:
            yield _sse_error(e.detail)
        except Exception as e:
            yield _sse_error(str(e))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/analyse")
async def analyse_authenticated(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    user_id  = _verify_token(authorization)
    filename = _original_filename(file)
    _validate_type(filename)
    content  = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max: {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    file_hash = _file_hash(content)
    cached    = _get_cached(user_id, file_hash)
    if cached:
        return {
            "record_id": cached["record_id"],
            "filename":  cached["filename"],
            "status":    "success",
            "analysis":  cached["analysis"],
            "cached":    True,
        }

    _log("analyse_start", actor=user_id, filename=filename, size=len(content))
    t0        = time.time()
    text      = _extract_text(content, filename)
    analysis  = _run_rag_pipeline(text)
    record_id, _ = _save_analysis(user_id, filename, file_hash, analysis)
    _log("analyse_complete", actor=user_id, filename=filename, record_id=record_id, duration_ms=int((time.time()-t0)*1000))
    return {"record_id": record_id, "filename": filename, "status": "success", "analysis": analysis}


@app.post("/analyse/stream")
async def analyse_stream(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    user_id  = _verify_token(authorization)
    filename = _original_filename(file)
    _validate_type(filename)
    content  = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max: {MAX_UPLOAD_BYTES // (1024*1024)} MB")

    async def generate():
        loop = asyncio.get_running_loop()
        try:
            yield _sse("Reading document…")
            file_hash = _file_hash(content)
            cached    = await loop.run_in_executor(_executor, lambda: _get_cached(user_id, file_hash))
            if cached:
                yield _sse_result({
                    "record_id": cached["record_id"],
                    "filename":  cached["filename"],
                    "status":    "success",
                    "analysis":  cached["analysis"],
                    "cached":    True,
                })
                return

            text = await loop.run_in_executor(_executor, lambda: _extract_text(content, filename))

            if _gemini_cache_name:
                yield _sse("Analysing with AI…")
                analysis = await loop.run_in_executor(
                    _executor, lambda: _call_gemini(text[:MAX_GEMINI_CHARS], [])
                )
            else:
                yield _sse("Finding relevant clauses…")
                def _rag():
                    vec = _embed_chunks([text[:CHUNK_WORDS * 6]])
                    return _retrieve_top_clauses(vec)
                similar = await loop.run_in_executor(_executor, _rag)
                yield _sse("Analysing with AI…")
                analysis = await loop.run_in_executor(
                    _executor, lambda: _call_gemini(text[:MAX_GEMINI_CHARS], similar)
                )

            record_id = str(uuid.uuid4())
            asyncio.create_task(_bg_save(user_id, filename, file_hash, record_id, analysis))
            yield _sse_result({
                "record_id": record_id,
                "filename":  filename,
                "status":    "success",
                "analysis":  analysis,
            })

        except HTTPException as e:
            yield _sse_error(e.detail)
        except Exception as e:
            yield _sse_error(str(e))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/history")
async def get_history(authorization: Optional[str] = Header(None)):
    user_id = _verify_token(authorization)
    _log("history_list", actor=user_id)
    return {"analyses": _list_analyses(user_id)}


@app.get("/history/{record_id}")
async def get_record(record_id: str, authorization: Optional[str] = Header(None)):
    user_id = _verify_token(authorization)
    _log("history_get", actor=user_id, record_id=record_id)
    return _get_analysis(user_id, record_id)


@app.delete("/history/{record_id}")
async def delete_record(record_id: str, authorization: Optional[str] = Header(None)):
    user_id = _verify_token(authorization)
    _delete_analysis(user_id, record_id)
    _log("history_delete", actor=user_id, record_id=record_id)
    return {"status": "deleted"}
