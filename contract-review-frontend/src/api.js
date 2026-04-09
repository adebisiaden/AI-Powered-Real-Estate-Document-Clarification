/**
 * API paths for axios. In local dev, use same-origin URLs so src/setupProxy.js
 * can forward them to FastAPI (including multipart /upload).
 *
 * Set REACT_APP_API_BASE_URL when the frontend is served without that proxy
 * (e.g. production static host + API on another URL).
 */
export function apiUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  const fromEnv = (process.env.REACT_APP_API_BASE_URL || '')
    .trim()
    .replace(/\/$/, '');
  if (fromEnv) {
    return `${fromEnv}${p}`;
  }
  return p;
}
