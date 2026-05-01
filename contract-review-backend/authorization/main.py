"""
Residential Lease Analyser
FastAPI backend  |  Claude Sonnet 4.6  |  Firebase Auth (Google)  |  GCS

Privacy model
─────────────
  Guest       → file extracted in memory, analysed, returned, discarded.
                Nothing written to disk or any storage layer.
  Logged-in   → same pipeline, then analysis JSON (not the document) is
                written to GCS under users/{uid}/{record_id}.json.
                File bytes go out of scope immediately after extraction.

Jurisdiction
────────────
  Jurisdiction-agnostic. Where rights vary by location, the analysis
  flags the clause and advises the user to verify locally rather than
  making jurisdiction-specific legal claims.

Environment variables required
──────────────────────────────
  ANTHROPIC_API_KEY
  GOOGLE_APPLICATION_CREDENTIALS   (path to GCP service-account JSON)
  GCS_BUCKET_NAME
  CORS_ORIGINS                     (comma-separated, e.g. http://localhost:3000)
"""

import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
import firebase_admin
from firebase_admin import auth as firebase_auth
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage as gcs
import PyPDF2
import docx


# ── startup ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    yield


app = FastAPI(
    title="Residential Lease Analyser",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

anthropic_client = anthropic.Anthropic()
GCS_BUCKET = os.environ["GCS_BUCKET_NAME"]
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BULK_FILES = 20


# ── auth ──────────────────────────────────────────────────────────────────────

async def optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Returns a decoded Firebase token dict, or None for guests."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return firebase_auth.verify_id_token(authorization.removeprefix("Bearer ").strip())
    except Exception:
        return None


async def require_user(authorization: Optional[str] = Header(None)) -> dict:
    user = await optional_user(authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to save and revisit analyses.",
        )
    return user


# ── text extraction ───────────────────────────────────────────────────────────

def extract_text(file_bytes: bytes, filename: str) -> str:
    fname = filename.lower()
    if fname.endswith(".pdf"):
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif fname.endswith(".docx"):
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported.",
        )


# ── analysis prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a plain-language lease analyst helping members of the general public
understand their residential lease agreements.

Your role is to explain — not to provide legal advice. Where tenant rights vary
by location, flag the issue and tell the reader to verify with a local tenants'
association or legal aid service. Never state that a clause is definitively
illegal; say it "may be unenforceable in some jurisdictions" instead.

Return ONLY valid JSON — no prose, no markdown fences, no extra keys.

Schema:
{
  "summary": "3–4 sentence plain-language overview written for a non-lawyer tenant",
  "overall_risk": "High|Medium|Low",
  "monthly_rent": "extracted rent amount as a string e.g. '$1,850/month', or null",
  "lease_term": "e.g. '12 months fixed', 'month-to-month', or null",
  "clauses": [
    {
      "type": "<clause type from the list below>",
      "found": true|false,
      "excerpt": "short verbatim excerpt from the lease, or null if not found",
      "plain_english": "1–2 sentence plain-language explanation for the tenant",
      "risk": "High|Medium|Low|None",
      "flag": "specific concern the tenant should know about, or null"
    }
  ],
  "tenant_friendly_terms": ["1–5 clauses that are clearly favourable to the tenant"],
  "top_concerns": ["2–5 specific issues the tenant should ask about or try to negotiate"],
  "recommended_action": "Looks reasonable|Review these clauses carefully|Seek advice before signing"
}

Clause types to check (always include all 20 — set found: false if absent):
  1.  Rent amount and due date
  2.  Rent increases
  3.  Security deposit
  4.  Lease term and renewal
  5.  Early termination
  6.  Notice to vacate (tenant)
  7.  Notice to vacate (landlord)
  8.  Subletting and assignment
  9.  Pet policy
  10. Maintenance and repairs
  11. Utilities and inclusions
  12. Landlord entry notice
  13. Guest and occupancy limits
  14. Alterations and modifications
  15. Tenant insurance
  16. Late fees and penalties
  17. Parking and storage
  18. Property use restrictions
  19. Dispute resolution
  20. Automatic renewal

Risk flags to watch for:
- Security deposit that seems unusually high (flag to verify local limits)
- No specified notice period before a rent increase takes effect
- Rent increases with no cap or index reference
- Early termination penalties that appear excessive
- Much shorter notice required from the tenant than from the landlord
- No landlord entry notice period, or very short one
- Clauses that waive tenant rights (note these may be unenforceable)
- Automatic renewal with no advance notice to the tenant
- Tenant made responsible for repairs typically borne by landlords
- No dispute resolution process specified
"""


def analyse_lease(text: str) -> dict:
    """
    Analyse a lease with Claude. Pure function — no I/O side effects.
    Truncates input to 80 000 chars to stay within context limits.
    """
    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Analyse this residential lease and return JSON only:\n\n"
                    + text[:80_000]
                ),
            }
        ],
    )
    raw = message.content[0].text
    cleaned = (
        raw.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    return json.loads(cleaned)


# ── GCS helpers (logged-in path only) ────────────────────────────────────────

def _bucket():
    return gcs.Client().bucket(GCS_BUCKET)


def save_analysis(uid: str, filename: str, analysis: dict) -> str:
    """
    Write analysis JSON to GCS under users/{uid}/{record_id}.json.
    The original document is never stored — only the analysis output.
    Returns the record_id.
    """
    record_id = str(uuid.uuid4())
    payload = {
        "id": record_id,
        "original_filename": filename,
        "status": "complete",
        "analysis": analysis,
    }
    _bucket().blob(f"users/{uid}/{record_id}.json").upload_from_string(
        json.dumps(payload, ensure_ascii=False),
        content_type="application/json",
    )
    return record_id


def save_error(uid: str, filename: str, job_id: str, error: str) -> None:
    payload = {
        "id": job_id,
        "original_filename": filename,
        "status": "error",
        "error": error,
    }
    _bucket().blob(f"users/{uid}/{job_id}.json").upload_from_string(
        json.dumps(payload), content_type="application/json"
    )


def list_analyses(uid: str) -> list[dict]:
    results = []
    for blob in gcs.Client().bucket(GCS_BUCKET).list_blobs(prefix=f"users/{uid}/"):
        try:
            data = json.loads(blob.download_as_text())
            row = {
                "id": data.get("id"),
                "filename": data.get("original_filename"),
                "status": data.get("status", "complete"),
            }
            if data.get("status") == "complete":
                a = data.get("analysis", {})
                row.update({
                    "overall_risk": a.get("overall_risk"),
                    "monthly_rent": a.get("monthly_rent"),
                    "lease_term": a.get("lease_term"),
                    "recommended_action": a.get("recommended_action"),
                })
            results.append(row)
        except Exception:
            pass
    return results


def get_analysis(uid: str, record_id: str) -> dict:
    blob = _bucket().blob(f"users/{uid}/{record_id}.json")
    if not blob.exists():
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return json.loads(blob.download_as_text())


def delete_analysis(uid: str, record_id: str) -> None:
    blob = _bucket().blob(f"users/{uid}/{record_id}.json")
    if blob.exists():
        blob.delete()


# ── file validation ───────────────────────────────────────────────────────────

def _validate(file: UploadFile) -> None:
    if not file.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{file.filename}' is not a PDF or DOCX file.",
        )
    if file.size and file.size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"'{file.filename}' exceeds the 20 MB limit.",
        )


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "residential-lease-analyser"}


# GUEST: analyse in memory, return, discard

@app.post("/analyse/guest")
async def analyse_guest(file: UploadFile = File(...)):
    """
    Instant lease analysis for guests.
    Nothing is stored — file bytes and extracted text are discarded after the response.
    """
    _validate(file)
    file_bytes = await file.read()
    text = extract_text(file_bytes, file.filename)
    analysis = analyse_lease(text)
    return {"analysis": analysis}


# LOGGED-IN: analyse and save analysis JSON to GCS

@app.post("/analyse")
async def analyse_authenticated(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    """
    Lease analysis for signed-in users.
    Analysis JSON is saved to the user's account. The document itself is not stored.
    """
    _validate(file)
    file_bytes = await file.read()
    text = extract_text(file_bytes, file.filename)
    analysis = analyse_lease(text)
    record_id = save_analysis(user["uid"], file.filename, analysis)
    return {"record_id": record_id, "analysis": analysis}


# BULK UPLOAD (logged-in only)

@app.post("/analyse/bulk")
async def analyse_bulk(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: dict = Depends(require_user),
):
    """
    Queue up to 20 leases for background analysis.
    Returns job IDs immediately. Poll GET /status/{job_id} as results come in.
    """
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BULK_FILES} files per batch.",
        )
    jobs = []
    for file in files:
        _validate(file)
        file_bytes = await file.read()
        job_id = str(uuid.uuid4())
        jobs.append({"filename": file.filename, "job_id": job_id})
        background_tasks.add_task(
            _bulk_task, user["uid"], file.filename, file_bytes, job_id
        )
    return {
        "jobs": jobs,
        "message": f"{len(jobs)} lease(s) queued. Poll /status/{{job_id}} for results.",
    }


async def _bulk_task(uid: str, filename: str, file_bytes: bytes, job_id: str) -> None:
    try:
        text = extract_text(file_bytes, filename)
        analysis = analyse_lease(text)
        payload = {
            "id": job_id,
            "original_filename": filename,
            "status": "complete",
            "analysis": analysis,
        }
        _bucket().blob(f"users/{uid}/{job_id}.json").upload_from_string(
            json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )
    except Exception as exc:
        save_error(uid, filename, job_id, str(exc))


@app.get("/status/{job_id}")
async def job_status(job_id: str, user: dict = Depends(require_user)):
    return get_analysis(user["uid"], job_id)


# HISTORY (logged-in only)

@app.get("/history")
async def history(user: dict = Depends(require_user)):
    return {"analyses": list_analyses(user["uid"])}


@app.get("/history/{record_id}")
async def get_record(record_id: str, user: dict = Depends(require_user)):
    return get_analysis(user["uid"], record_id)


@app.delete("/history/{record_id}")
async def delete_record(record_id: str, user: dict = Depends(require_user)):
    delete_analysis(user["uid"], record_id)
    return {"deleted": record_id}
