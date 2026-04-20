# Tests that uploading an empty file is rejected
# with a 400 error and a descriptive error message.

import sys
sys.path.insert(0, "contract-review-backend")
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_empty_file_returns_400():
    response = client.post(
        "/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")}
    )
    assert response.status_code == 400
    assert "Empty file" in response.json()["detail"]