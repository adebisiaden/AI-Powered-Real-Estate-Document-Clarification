# Tests that uploading a file over the 20MB limit
# is rejected with a 413 error.

import sys
sys.path.insert(0, "contract-review-backend")
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_file_over_20mb_returns_413():
    big_content = b"x" * (21 * 1024 * 1024)  # 21MB
    response = client.post(
        "/upload",
        files={"file": ("big.pdf", big_content, "application/pdf")}
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()