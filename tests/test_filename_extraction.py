# Unit test: verifies that _original_filename() correctly extracts
# the filename from an upload, and raises a 400 error when
# no filename is provided.


import sys
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

sys.path.insert(0, "contract-review-backend")

from main import _original_filename

def test_extracts_filename_correctly():
    mock_upload = MagicMock()
    mock_upload.filename = "contract.pdf"
    result = _original_filename(mock_upload)
    assert result == "contract.pdf"

def test_raises_error_when_filename_missing():
    mock_upload = MagicMock()
    mock_upload.filename = ""
    with pytest.raises(HTTPException) as exc_info:
        _original_filename(mock_upload)
    assert exc_info.value.status_code == 400