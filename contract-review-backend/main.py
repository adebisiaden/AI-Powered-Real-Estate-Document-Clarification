import io
import json
import os
import uuid
from pathlib import Path

from google import genai
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
from pydantic import BaseModel
from PyPDF2 import PdfReader

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if _creds:
    _p = Path(_creds)
    if not _p.is_absolute():
        _p = (BASE_DIR / _p).resolve()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_p)

# ----------------------------
# Gemini setup (via Vertex AI)
# ----------------------------
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Contract Review API", version="0.4.0")

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


# ----------------------------
# Schemas
# ----------------------------
class AnalyzeRequest(BaseModel):
    text: str


# ----------------------------
# Helpers
# ----------------------------
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
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts).strip()
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read PDF: {e!s}",
        ) from e


def _extract_text_docx(content: bytes) -> str:
    try:
        doc = Document(io.BytesIO(content))
        parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(parts).strip()
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read DOCX: {e!s}",
        ) from e


def _extract_text(content: bytes, filename: str) -> str:
    ext = _extension(filename)
    if ext == ".pdf":
        return _extract_text_pdf(content)
    if ext == ".docx":
        return _extract_text_docx(content)
    raise HTTPException(status_code=400, detail="Unsupported file type")


def _upload_to_gcs(content: bytes, dest_blob_name: str, content_type: str) -> None:
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        raise HTTPException(
            status_code=500,
            detail="GCS_BUCKET_NAME is not configured",
        )
    project = os.getenv("GCP_PROJECT_ID")
    try:
        gcs_client = storage.Client(project=project) if project else storage.Client()
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(dest_blob_name)
        blob.upload_from_string(content, content_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cloud Storage upload failed: {e!s}",
        ) from e


def _mime_for_filename(filename: str) -> str:
    ext = _extension(filename)
    if ext == ".pdf":
        return "application/pdf"
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


CUAD_CLAUSE_TYPES = [
    "Effective Date", "Expiration Date", "Renewal Term", "Notice Period to Terminate Renewal",
    "Governing Law", "Most Favored Nation", "Non-Compete", "Exclusivity",
    "No-Solicit of Customers", "No-Solicit of Employees", "Non-Disparagement",
    "Limitation of Liability", "Cap on Liability", "Liquidated Damages",
    "Uncapped Liability", "Indemnification", "Insurance", "Warranty Duration",
    "IP Ownership Assignment", "Joint IP Ownership", "License Grant",
    "Non-Transferable License", "Affiliate License Grant", "Affiliate License Revoke",
    "Irrevocable or Perpetual License", "Source Code Escrow", "Post-Termination Services",
    "Audit Rights", "Minimum Commitment", "Volume Restriction", "Price Restrictions",
    "Anti-Assignment", "Change of Control", "Termination for Convenience",
    "ROFR/ROFO/ROFN", "Competitive Restriction Exception", "Third Party Beneficiary",
    "Revenue/Profit Sharing", "Parties", "Agreement Date", "Document Name"
]

def _analyze_with_gemini(text: str) -> dict:
    clause_list = "\n".join(f"- {c}" for c in CUAD_CLAUSE_TYPES)
    prompt = f"""
    You are a legal contract analysis assistant trained on the CUAD dataset 
    (Contract Understanding Atticus Dataset), a benchmark legal dataset of 
    500+ contracts annotated by expert lawyers.

    Analyze the following contract using CUAD's 41 expert-labeled clause categories:
    {clause_list}

    Return a JSON object with exactly these three keys:

    1. "clauses": list of objects with "type" (from the CUAD categories above) 
       and "excerpt" (relevant quote, max 200 chars)
    2. "risks": list of objects with "issue" (short title) and 
       "explanation" (plain English, 1-2 sentences)
    3. "summary": 2-3 sentence plain English overview of the contract 
       and its most important terms

    Return ONLY valid JSON, no markdown, no extra text.

    Contract text:
    {text[:12000]}
    """
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
        )
        clean = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(clean)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini analysis failed: {e!s}",
        ) from e


# ----------------------------
# Endpoints
# ----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


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
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    text = _extract_text(content, filename)

    ext = _extension(filename)
    blob_name = f"uploads/{uuid.uuid4()}{ext}"
    _upload_to_gcs(content, blob_name, _mime_for_filename(filename))

    analysis = _analyze_with_gemini(text)

    return {
        "filename": filename,
        "text": text,
        "analysis": analysis,
        "status": "success",
    }


@app.post("/analyze")
async def analyze(data: AnalyzeRequest):
    analysis = _analyze_with_gemini(data.text)
    return {"analysis": analysis}