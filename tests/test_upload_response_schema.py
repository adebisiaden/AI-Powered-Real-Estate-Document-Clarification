# Functional test: verifies that a successful upload returns a response
# with the correct keys (filename, text, status) — testing business intent,
# not just that the endpoint exists.


import sys
import os
from unittest.mock import patch
from dotenv import load_dotenv

sys.path.insert(0, "contract-review-backend")
load_dotenv("contract-review-backend/.env")

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

MOCK_ANALYSIS = {"summary": "Test summary.", "risks": [], "clauses": []}

def test_upload_response_has_correct_keys():
    with patch("main._upload_to_gcs", return_value=None), \
         patch("main._run_rag_pipeline", return_value=MOCK_ANALYSIS):
        with open("tests/fixtures/sample_contract.pdf", "rb") as f:
            response = client.post(
                "/upload",
                files={"file": ("sample_contract.pdf", f, "application/pdf")}
            )
    assert response.status_code == 200
    body = response.json()
    assert "filename" in body
    assert "text" in body
    assert "status" in body
    assert body["status"] == "success"
    assert body["filename"] == "sample_contract.pdf"