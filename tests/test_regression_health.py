# Regression test: re-runs the health check after any code change
# to ensure the API hasn't been silently broken by a teammate's push.
# This is the first test that should run in CI/CD.


import sys
sys.path.insert(0, "contract-review-backend")

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_health_still_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"