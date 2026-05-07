#!/usr/bin/env python3
"""
Local test for the /analyze endpoint.

Usage:
    python test_analyze.py                     # uses built-in sample contract
    python test_analyze.py path/to/contract.txt  # uses a text file
"""

import json
import sys
import urllib.request

API_URL = "http://localhost:8000/analyze"

SAMPLE_CONTRACT = """
SOFTWARE LICENSE AGREEMENT

This Software License Agreement ("Agreement") is entered into as of January 1, 2024,
between Acme Corp, a Delaware corporation ("Licensor"), and Beta Inc ("Licensee").

1. GRANT OF LICENSE
Licensor grants Licensee a non-exclusive, non-transferable, worldwide license to use
the Software solely for Licensee's internal business purposes.

2. INTELLECTUAL PROPERTY
All intellectual property rights in the Software remain exclusively with Licensor.
Licensee assigns to Licensor any improvements or modifications made to the Software.

3. CONFIDENTIALITY
Licensee shall keep all technical information about the Software strictly confidential
for a period of five (5) years following termination of this Agreement.

4. INDEMNIFICATION
Licensee shall indemnify, defend, and hold harmless Licensor and its affiliates from
any and all claims, damages, losses, and expenses, including attorneys' fees, arising
out of or related to Licensee's use of the Software, with no cap on the total liability.

5. LIMITATION OF LIABILITY
IN NO EVENT SHALL LICENSOR BE LIABLE FOR ANY INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES. LICENSOR'S TOTAL LIABILITY SHALL NOT EXCEED THE FEES PAID IN THE PRIOR
TWELVE (12) MONTHS.

6. NON-COMPETE
During the term and for two (2) years thereafter, Licensee shall not, directly or
indirectly, develop, market, or sell any product that competes with the Software
anywhere in the world.

7. TERM AND TERMINATION
This Agreement commences on the Effective Date and continues for one (1) year,
automatically renewing for successive one-year terms unless either party provides
fifteen (15) days written notice of non-renewal before the renewal date.

8. GOVERNING LAW
This Agreement shall be governed by the laws of the State of Delaware, without regard
to its conflict of law provisions. Any disputes shall be resolved by binding arbitration
in Wilmington, Delaware.

9. ASSIGNMENT
Licensee may not assign this Agreement without Licensor's prior written consent.
Licensor may assign this Agreement in connection with a merger or acquisition.

10. ENTIRE AGREEMENT
This Agreement constitutes the entire agreement between the parties and supersedes
all prior negotiations, representations, and understandings.
"""


def test(contract_text: str) -> None:
    payload = json.dumps({"text": contract_text}).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"POST {API_URL}")
    print(f"Contract length: {len(contract_text):,} characters\n")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        return
    except Exception as e:
        print(f"Request failed: {e}")
        return

    test_display(result)


def test_upload(path: str) -> None:
    """Send a PDF or DOCX directly to /upload (handles text extraction server-side)."""
    upload_url = API_URL.replace("/analyze", "/upload")
    filename   = path.split("/")[-1]

    with open(path, "rb") as f:
        file_data = f.read()

    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        upload_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    print(f"POST {upload_url}  (file: {filename})")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        return
    except Exception as e:
        print(f"Request failed: {e}")
        return

    analysis = result.get("analysis", result)
    print(f"Contract length: {len(result.get('text', '')):,} characters\n")
    test_display(analysis)


def test_display(result: dict) -> None:
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(result.get("summary", "(none)"))

    risks = result.get("risks", [])
    print(f"\n{'=' * 60}")
    print(f"RISK FLAGS ({len(risks)})")
    print("=" * 60)
    for r in risks:
        level = r.get("risk_level", "?")
        icon  = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(level, "⚪")
        print(f"{icon} [{level}] {r.get('clause', '?')}")
        print(f"   {r.get('reason', '')}")

    clauses = result.get("clauses", [])
    found   = [c for c in clauses if c.get("found")]
    missing = [c for c in clauses if not c.get("found")]

    print(f"\n{'=' * 60}")
    print(f"CLAUSES FOUND ({len(found)}/{len(clauses)})")
    print("=" * 60)
    for c in found:
        snippet = c.get("text", "")[:80].replace("\n", " ")
        print(f"  ✓ {c.get('clause_type', '?')}")
        if snippet:
            print(f"    \"{snippet}...\"")

    print(f"\nMISSING ({len(missing)})")
    for c in missing:
        print(f"  ✗ {c.get('clause_type', '?')}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
        ext  = path.lower().rsplit(".", 1)[-1]
        if ext in ("pdf", "docx"):
            test_upload(path)
            sys.exit(0)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        print(f"Testing with file: {path}")
    else:
        text = SAMPLE_CONTRACT
        print("Testing with built-in sample contract")

    test(text)
