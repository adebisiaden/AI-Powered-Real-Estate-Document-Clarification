# AI-Powered Real Estate Document Clarification

An intelligent contract review tool that analyzes legal documents using a RAG (Retrieval-Augmented Generation) pipeline built on the CUAD and ACORD legal datasets. Upload a PDF or DOCX contract and get a plain-English summary, risk flags, and an identified clause breakdown — powered by Google Gemini on Vertex AI.

---

## Live App

| Service | URL |
|---|---|
| **Frontend (Vercel)** | https://contract-review-frontend-phi.vercel.app |
| **Backend API (Cloud Run)** | https://contract-review-api-243703291596.us-central1.run.app |
| **API Health Check** | https://contract-review-api-243703291596.us-central1.run.app/health |
| **API Docs (Swagger)** | https://contract-review-api-243703291596.us-central1.run.app/docs |

---

## What It Does

1. **Upload** a PDF or DOCX contract (up to 20 MB)
2. **Extract** text from the document server-side
3. **Embed** the contract text into chunks using `gemini-embedding-001` via Vertex AI
4. **Retrieve** the most relevant clauses from a pre-built vector index of 10,928 CUAD + ACORD legal clauses
5. **Analyze** with `gemini-2.5-flash` (temperature=0) using the retrieved clauses as RAG context
6. **Display** results in a split-panel UI:
   - **Summary** — plain-English overview with overall risk level and clause count
   - **Risk Flags** — High / Medium / Low risk items with explanations
   - **Identified Clauses** — all 41 CUAD clause types checked, found clauses with extracted text, missing clauses listed

---

## Tech Stack

### Backend
- **FastAPI** — REST API with `/upload`, `/analyze`, `/health` endpoints
- **Vertex AI** — `gemini-embedding-001` for document embeddings
- **Google Gemini** (`gemini-2.5-flash`) — contract analysis via `google-genai` SDK
- **Google Cloud Storage** — stores uploaded contracts and the prebuilt vector index
- **RAG Pipeline** — CUAD + ACORD legal datasets (10,928 clauses, 3072-dim vectors), cosine similarity retrieval, top-10 context injection
- **PyPDF2 / python-docx** — text extraction from PDF and DOCX files

### Frontend
- **React 19** — split-panel UI with tab navigation
- **react-pdf** — in-browser PDF preview with page navigation
- **Axios** — API communication
- **Vercel** — static hosting with production build

### Infrastructure
- **Cloud Run** — containerized FastAPI backend (2Gi memory, 0–3 instances, 300s timeout)
- **Artifact Registry** — Docker image storage
- **GCS Bucket** — `mlops-491304-artifacts` (embeddings + uploaded files)

---

## Project Structure

```
AI-Powered-Real-Estate-Document-Clarification/
├── contract-review-backend/
│   ├── main.py                  # FastAPI app + RAG pipeline
│   ├── requirements.txt
│   ├── test_analyze.py          # Local CLI test script
│   └── .env                     # GCP credentials (gitignored)
├── contract-review-frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FileUploadDropzone.js   # Main UI component
│   │   │   └── FileUploadDropzone.css
│   │   ├── App.js
│   │   ├── api.js               # API URL helper (supports REACT_APP_API_BASE_URL)
│   │   └── setupProxy.js        # Dev proxy to FastAPI
│   └── .env.production          # Production API URL (points to Cloud Run)
├── tests/
│   ├── fixtures/
│   │   └── sample_contract.pdf
│   ├── test_empty_file.py
│   ├── test_file_size_limit.py
│   ├── test_file_validation.py
│   ├── test_filename_extraction.py
│   ├── test_health.py
│   ├── test_mime_type.py
│   ├── test_regression_health.py
│   ├── test_security_bandit.py
│   └── test_upload_response_schema.py
├── build_vector_index.py        # One-time script to build CUAD/ACORD vector index
├── Dockerfile
└── README.md
```

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- A GCP project with Vertex AI and GCS enabled
- A GCP service account key with Vertex AI + GCS permissions

### 1. Backend

```bash
cd contract-review-backend

# Create and activate virtual environment
python -m venv mlops
source mlops/bin/activate          # Windows: mlops\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file inside `contract-review-backend/` (never commit this):
```
GOOGLE_APPLICATION_CREDENTIALS=../your-service-account-key.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
GCS_BUCKET_NAME=your-gcs-bucket
GEMINI_MODEL=gemini-2.5-flash
```

```bash
# Start the API
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API available at `http://localhost:8000` — Swagger docs at `http://localhost:8000/docs`

### 2. Frontend

```bash
cd contract-review-frontend
npm install
npm start
```

Opens at `http://localhost:3000`. The dev proxy in `setupProxy.js` automatically forwards `/upload`, `/analyze`, and `/health` to the local FastAPI server.

### 3. CLI Test Script

```bash
cd contract-review-backend

# Test with built-in sample contract
python test_analyze.py

# Test with a real PDF or DOCX file
python test_analyze.py path/to/contract.pdf
```

---

## Running Tests

```bash
# From the project root
pytest tests/ -v
```

16 tests, all passing:

| Test | What It Covers |
|---|---|
| `test_health` | `/health` endpoint smoke test |
| `test_regression_health` | Regression check — health still returns ok after changes |
| `test_empty_file` | Empty file upload rejected with 400 |
| `test_file_size_limit` | File over 20 MB rejected with 413 |
| `test_file_validation` | Only `.pdf`/`.docx` accepted; `.txt`, `.png`, `.exe`, `.csv` rejected |
| `test_filename_extraction` | Unit test for `_original_filename()` helper |
| `test_mime_type` | Unit test for `_mime_for_filename()` helper |
| `test_security_bandit` | Bandit static analysis — no hardcoded secrets in source |
| `test_upload_response_schema` | Successful upload returns `filename`, `text`, `status` keys |

---

## Deploying

### Backend — Google Cloud Run

```bash
# From the project root (requires Dockerfile)
gcloud run deploy contract-review-api \
  --source . \
  --region us-central1 \
  --memory 2Gi \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=your-project,GCP_LOCATION=us-central1,GCS_BUCKET_NAME=your-bucket,GEMINI_MODEL=gemini-2.5-flash" \
  --project your-project-id
```

### Frontend — Vercel

```bash
cd contract-review-frontend

# Point to your Cloud Run backend
echo "REACT_APP_API_BASE_URL=https://your-cloud-run-url.run.app" > .env.production

npm install -g vercel
vercel --yes    # preview deploy
vercel --prod   # promote to production
```

---

## Building the Vector Index (one-time setup)

The CUAD + ACORD vector index must be built once and uploaded to GCS before the backend can serve analysis requests.

```bash
# Install build dependencies
pip install -r requirements_offline.txt

# Dry run — processes first 100 clauses only
python build_vector_index.py --dry-run

# Full build — embeds all 10,928 clauses (~30–60 min)
python build_vector_index.py
```

Uploads `cuad_acord_vectors.npy` and `cuad_acord_clauses.json` to `gs://your-bucket/embeddings/`.

---

## API Reference

### `GET /health`
```json
{ "status": "ok", "embeddings_loaded": true, "clause_count": 10928 }
```

### `POST /upload`
Multipart form upload of a PDF or DOCX file.

**Response:**
```json
{
  "filename": "contract.pdf",
  "status": "success",
  "text": "full extracted text...",
  "analysis": {
    "summary": "Plain-English summary of the contract...",
    "risks": [
      { "clause": "Indemnification", "risk_level": "High", "reason": "Unlimited indemnification with no monetary cap." }
    ],
    "clauses": [
      { "clause_type": "Governing Law", "text": "This agreement is governed by...", "found": true },
      { "clause_type": "Audit Rights", "text": "", "found": false }
    ]
  }
}
```

### `POST /analyze`
Send pre-extracted text directly for analysis.

**Body:** `{ "text": "contract text here" }`
**Response:** Same `analysis` object as above.

---

## Git Branches

| Branch | Purpose |
|---|---|
| `main` | Stable base |
| `FastAPI/RAG` | Backend RAG pipeline + Gemini integration |
| `UI` | Frontend split-panel layout and PDF viewer |
| `deployment/testcases` | Deployment config + all 16 tests passing |
| `CUAD/ACORD` | Vector index build script |

---

## Team

MLOps Group Project — Spring Module 2

---

## Future Work

- **Authentication & User Accounts** — Firebase Authentication with Google login. Guest users get in-memory processing (no storage). Logged-in users get private encrypted GCS storage with per-user folder isolation.

- **Accuracy Evaluation** — Benchmark clause extraction against CUAD's expert-labeled ground truth across all 510 contracts and report precision/recall per clause type.

- **Bulk Contract Analysis** — Upload and analyze multiple contracts simultaneously via a queue system, generating a comparative risk report across an entire contract portfolio.
