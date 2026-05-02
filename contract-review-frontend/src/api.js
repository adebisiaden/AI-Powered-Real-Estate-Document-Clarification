// src/api.js
// Attaches the Firebase ID token (if present) to every request.
// Guest requests go to /analyse/guest — no token needed.
// Authenticated requests go to /analyse, /history, etc.

const BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

function authHeaders(token) {
  return token
    ? { Authorization: `Bearer ${token}` }
    : {};
}

// ── Analyse ────────────────────────────────────────────────────────────────

/**
 * Guest upload — nothing stored server-side.
 */
export async function analyseGuest(file) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE_URL}/analyse/guest`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Analysis failed.");
  }
  return res.json(); // { analysis: { … } }
}

/**
 * Authenticated upload — analysis JSON saved to user's account.
 */
export async function analyseAuthenticated(file, token) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE_URL}/analyse`, {
    method: "POST",
    headers: authHeaders(token),
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Analysis failed.");
  }
  return res.json(); // { record_id, analysis: { … } }
}

/**
 * Smart wrapper — picks the right endpoint based on whether a token exists.
 */
export async function analyseFile(file, token) {
  return token
    ? analyseAuthenticated(file, token)
    : analyseGuest(file);
}

// ── Bulk ───────────────────────────────────────────────────────────────────

export async function analyseBulk(files, token) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));

  const res = await fetch(`${BASE_URL}/analyse/bulk`, {
    method: "POST",
    headers: authHeaders(token),
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Bulk analysis failed.");
  }
  return res.json(); // { jobs: [{ filename, job_id }], message }
}

export async function pollJobStatus(jobId, token) {
  const res = await fetch(`${BASE_URL}/status/${jobId}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error("Could not fetch job status.");
  return res.json();
}

// ── History ────────────────────────────────────────────────────────────────

export async function fetchHistory(token) {
  const res = await fetch(`${BASE_URL}/history`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error("Could not load history.");
  return res.json(); // { analyses: [ … ] }
}

export async function fetchRecord(recordId, token) {
  const res = await fetch(`${BASE_URL}/history/${recordId}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error("Record not found.");
  return res.json();
}

export async function deleteRecord(recordId, token) {
  const res = await fetch(`${BASE_URL}/history/${recordId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error("Could not delete record.");
  return res.json();
}
