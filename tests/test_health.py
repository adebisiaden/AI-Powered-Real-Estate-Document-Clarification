# Tests that the /health endpoint is reachable and
# returns a status of "ok" — a basic smoke test for the API.

import sys
sys.path.insert(0, "contract-review-backend")
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"