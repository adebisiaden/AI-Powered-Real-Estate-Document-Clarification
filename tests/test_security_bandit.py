# Security test: runs Bandit static analysis on the backend codebase
# to check for hardcoded secrets and security issues in OUR code only,
# excluding the virtual environment's third-party packages.

import subprocess

def test_no_hardcoded_secrets():
    result = subprocess.run(
        ["bandit", "-r", "contract-review-backend/",
         "--exclude", "contract-review-backend/mlops,contract-review-backend/.venv",
         "-ll", "-q"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Bandit found security issues:\n{result.stdout}"