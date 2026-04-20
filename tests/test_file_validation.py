# Tests that the API only accepts .pdf and .docx files,
# and rejects all other file types with a 400 error.

import pytest
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, "contract-review-backend")
from main import app

client = TestClient(app)

@pytest.mark.parametrize("filename,expected_status", [
    ("contract.pdf",  422),  # passes type check, fails parsing
    ("contract.docx", 422),  # passes type check, fails parsing
    ("contract.txt",  400),
    ("contract.png",  400),
    ("contract.exe",  400),
    ("contract.csv",  400),
])
def test_file_type_validation(filename, expected_status):
    fake_content = b"fake content"
    response = client.post(
        "/upload",
        files={"file": (filename, fake_content, "application/octet-stream")}
    )
    assert response.status_code == expected_status