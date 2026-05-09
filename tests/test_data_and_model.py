# Tests that validate data quality and model output structure
import sys
import json
import sys
sys.path.insert(0, "contract-review-backend")
from unittest.mock import patch, MagicMock
sys.path.insert(0, "contract-review-backend")
from main import (
    _extract_text_pdf, _extract_text_docx, _chunk_text,
    _merge_results, _cosine_sim
)
import numpy as np
import pytest

# ── Data Tests ────────────────────────────────────────────────────────────

def test_extracted_text_is_string():
    """Text extraction returns a string type"""
    with open("tests/fixtures/sample_contract.pdf", "rb") as f:
        content = f.read()
    result = _extract_text_pdf(content)
    assert isinstance(result, str)

def test_extracted_text_is_nonempty():
    """Text extraction from a real PDF returns non-empty content"""
    with open("tests/fixtures/sample_contract.pdf", "rb") as f:
        content = f.read()
    result = _extract_text_pdf(content)
    assert len(result.strip()) > 0

def test_chunk_text_produces_list():
    """Chunking returns a list of strings"""
    text = "word " * 5000
    chunks = _chunk_text(text)
    assert isinstance(chunks, list)
    assert all(isinstance(c, str) for c in chunks)

def test_chunk_text_covers_full_document():
    """All words appear in at least one chunk"""
    text = "alpha beta gamma delta epsilon " * 100
    chunks = _chunk_text(text)
    combined = " ".join(chunks)
    for word in ["alpha", "beta", "gamma", "delta", "epsilon"]:
        assert word in combined

def test_chunk_text_empty_input():
    """Empty input returns empty list"""
    assert _chunk_text("") == []

# ── Model Output Tests ─────────────────────────────────────────────────────

def test_merge_results_risk_deduplication():
    """Merge keeps highest risk level when same clause appears in multiple chunks"""
    results = [
        {"risks": [{"clause": "Indemnification", "risk_level": "Low", "reason": "x"}], "clauses": []},
        {"risks": [{"clause": "Indemnification", "risk_level": "High", "reason": "y"}], "clauses": []},
    ]
    merged = _merge_results(results)
    indemnification = next(r for r in merged["risks"] if r["clause"] == "Indemnification")
    assert indemnification["risk_level"] == "High"

def test_merge_results_clause_found_wins():
    """If any chunk finds a clause, merged result marks it as found"""
    results = [
        {"risks": [], "clauses": [{"clause_type": "Governing Law", "text": "", "found": False}]},
        {"risks": [], "clauses": [{"clause_type": "Governing Law", "text": "governed by NY law", "found": True}]},
    ]
    merged = _merge_results(results)
    governing = next(c for c in merged["clauses"] if c["clause_type"] == "Governing Law")
    assert governing["found"] is True

def test_cosine_sim_identical_vectors():
    """Cosine similarity of a vector with itself should be ~1.0"""
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    corpus = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    scores = _cosine_sim(v, corpus)
    assert abs(scores[0] - 1.0) < 1e-5

def test_cosine_sim_orthogonal_vectors():
    """Cosine similarity of orthogonal vectors should be ~0"""
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    corpus = np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
    scores = _cosine_sim(v, corpus)
    assert abs(scores[0]) < 1e-5