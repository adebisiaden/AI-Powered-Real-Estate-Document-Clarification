import { useCallback, useRef, useState } from 'react';
import axios from 'axios';
import { apiUrl } from '../api';
import './FileUploadDropzone.css';

const ACCEPT = '.pdf,.docx';

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function isAllowedFile(file) {
  const name = (file.name || '').toLowerCase();
  return name.endsWith('.pdf') || name.endsWith('.docx');
}

function detailFromAxiosError(err) {
  const status = err.response?.status;
  const d = err.response?.data?.detail;
  if (typeof d === 'string') {
    if (status === 404 && d === 'Not Found') {
      return `${d} (HTTP 404). Run the Phase 2 API from folder contract-review-backend: uvicorn main:app --reload --host 0.0.0.0 --port 8000 (not app.main from the repo root).`;
    }
    return d;
  }
  if (Array.isArray(d) && d[0]?.msg) return d.map((x) => x.msg).join('; ');
  if (status) return `HTTP ${status}: ${err.message || 'Upload failed'}`;
  return err.message || 'Upload failed';
}

export function FileUploadDropzone() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const resetMessages = useCallback(() => {
    setResult(null);
    setError(null);
    setProgress(0);
  }, []);

  const pickFile = useCallback(
    (f) => {
      if (!f || !isAllowedFile(f)) {
        setFile(null);
        setError('Only PDF or DOCX files are allowed.');
        setResult(null);
        return;
      }
      setFile(f);
      setError(null);
      setResult(null);
    },
    [setError, setFile, setResult]
  );

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      const f = e.dataTransfer?.files?.[0];
      pickFile(f);
    },
    [pickFile]
  );

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  }, []);

  const onDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  }, []);

  const onInputChange = useCallback(
    (e) => {
      const f = e.target.files?.[0];
      pickFile(f);
      e.target.value = '';
    },
    [pickFile]
  );

  const upload = async () => {
    if (!file) return;
    resetMessages();
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await axios.post(apiUrl('/upload'), formData, {
        onUploadProgress: (ev) => {
          if (ev.total) setProgress(Math.round((ev.loaded * 100) / ev.total));
          else setProgress(0);
        },
      });
      setResult(data);
      setProgress(100);
    } catch (err) {
      setError(detailFromAxiosError(err));
      setProgress(0);
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="upload-section" aria-label="File upload">
      <h2>Upload contract</h2>
      <p className="upload-hint">PDF or DOCX only</p>

      <div
        className={`dropzone ${dragActive ? 'dropzone--active' : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="dropzone-input"
          onChange={onInputChange}
        />
        <span className="dropzone-text">
          Drag and drop a file here, or click to browse
        </span>
      </div>

      {file && (
        <div className="file-meta">
          <strong>{file.name}</strong>
          <span>{formatBytes(file.size)}</span>
        </div>
      )}

      <button
        type="button"
        className="upload-btn"
        onClick={(e) => {
          e.stopPropagation();
          upload();
        }}
        disabled={!file || uploading}
      >
        {uploading ? 'Uploading…' : 'Upload'}
      </button>

      {uploading && (
        <div className="progress-wrap" aria-live="polite">
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="progress-label">{progress}%</span>
        </div>
      )}

      {result?.status === 'success' && (
        <div className="alert alert--success" role="status">
          <p>
            <strong>Success</strong> — processed {result.filename}
          </p>
          {result.text != null && result.text.length > 0 ? (
            <pre className="extract-preview">{result.text.slice(0, 2000)}</pre>
          ) : (
            <p className="extract-empty">No text could be extracted (file may be image-only).</p>
          )}
          {result.text != null && result.text.length > 2000 && (
            <p className="extract-truncated">Showing first 2000 characters.</p>
          )}
        </div>
      )}

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
