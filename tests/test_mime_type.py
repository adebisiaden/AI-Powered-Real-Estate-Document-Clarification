# Unit test: verifies that the _mime_for_filename() helper function
# returns the correct MIME type for pdf and docx files independently
# of any endpoint or upload logic.


import sys
sys.path.insert(0, "contract-review-backend")

from main import _mime_for_filename

def test_pdf_mime_type():
    result = _mime_for_filename("contract.pdf")
    assert result == "application/pdf"

def test_docx_mime_type():
    result = _mime_for_filename("contract.docx")
    assert result == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"