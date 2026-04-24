import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { apiUrl } from '../api';
import './FileUploadDropzone.css';

// eslint-disable-next-line no-new
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

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
      return `${d} (HTTP 404). Run the Phase 2 API from folder contract-review-backend: uvicorn main:app --reload --host 0.0.0.0 --port 8000`;
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
  const [activeTab, setActiveTab]   = useState('summary');
  const [numPages, setNumPages]     = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pdfUrl, setPdfUrl]         = useState(null);
  const pdfContainerRef             = useRef(null);
  const [pdfContainerWidth, setPdfContainerWidth] = useState(0);

  useEffect(() => {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      setPdfUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
      return;
    }
    const url = URL.createObjectURL(file);
    setPdfUrl(url);
    setPageNumber(1);
    setNumPages(null);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!pdfUrl) return;
    const el = pdfContainerRef.current;
    if (!el) return;
    setPdfContainerWidth(el.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) =>
      setPdfContainerWidth(entry.contentRect.width)
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [pdfUrl]);

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
      console.log('Full API response:', data);
      console.log('Risks array:', data?.analysis?.risks);
      setProgress(100);
      setActiveTab('summary');
    } catch (err) {
      setError(detailFromAxiosError(err));
      setProgress(0);
    } finally {
      setUploading(false);
    }
  };

  const risksCount   = result?.analysis?.risks?.length ?? 0;
  const clausesCount = result?.analysis?.clauses?.filter(c => c.found)?.length ?? 0;

  return (
    <div className="split-layout">

      {/* LEFT PANEL */}
      <div className="panel panel--left">
        <div className="panel-inner">
          <h2>Upload Contract</h2>
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
            {uploading ? 'Analyzing…' : 'Upload & Analyze'}
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
              {progress === 100 && (
                <span className="analyzing-label">Analyzing with Gemini...</span>
              )}
            </div>
          )}

          {result?.status === 'success' && (
            <div className="status-complete" role="status">
              ✓ Analysis complete — {result.filename}
            </div>
          )}

          {error && (
            <div className="alert alert--error" role="alert">
              {error}
            </div>
          )}

          {pdfUrl ? (
            <div className="extract-section">
              <h3 className="extract-heading">Contract Preview</h3>
              <div className="pdf-viewer" ref={pdfContainerRef}>
                <Document
                  file={pdfUrl}
                  onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                  loading={<p className="pdf-loading">Loading PDF…</p>}
                  error={<p className="pdf-loading">Could not load PDF preview.</p>}
                >
                  <Page
                    pageNumber={pageNumber}
                    width={pdfContainerWidth || undefined}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                  />
                </Document>
              </div>
              <div className="pdf-nav">
                <button
                  className="pdf-nav-btn"
                  onClick={() => setPageNumber(p => Math.max(1, p - 1))}
                  disabled={pageNumber <= 1}
                >
                  ← Prev
                </button>
                <span className="pdf-page-label">
                  Page {pageNumber} of {numPages ?? '…'}
                </span>
                <button
                  className="pdf-nav-btn"
                  onClick={() => setPageNumber(p => Math.min(numPages ?? p, p + 1))}
                  disabled={pageNumber >= (numPages ?? 1)}
                >
                  Next →
                </button>
              </div>
            </div>
          ) : result?.text ? (
            <div className="extract-section">
              <h3 className="extract-heading">Contract Text</h3>
              <pre className="extract-preview">{result.text}</pre>
            </div>
          ) : null}
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="panel panel--right">
        {result?.status === 'success' ? (
          <>
            <div className="tab-bar">
              <button
                className={`tab-btn ${activeTab === 'summary' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('summary')}
              >
                Summary
              </button>
              <button
                className={`tab-btn ${activeTab === 'risks' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('risks')}
              >
                Risk Flags{risksCount > 0 ? ` (${risksCount})` : ''}
              </button>
              <button
                className={`tab-btn ${activeTab === 'clauses' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('clauses')}
              >
                Identified Clauses{clausesCount > 0 ? ` (${clausesCount})` : ''}
              </button>
            </div>

            <div className="tab-content">
              {activeTab === 'summary' && (
                <div className="analysis-section">
                  {result.analysis?.summary && (
                    <p className="analysis-summary">{result.analysis.summary}</p>
                  )}
                  <div className="metrics-row">
                    <div className="metric-card">
                      <span className="metric-label">Risk Level</span>
                      <span className="metric-value">
                        {(() => {
                          const risks = result.analysis?.risks || [];
                          if (risks.some(r => r.risk_level === 'High'))   return 'High';
                          if (risks.some(r => r.risk_level === 'Medium')) return 'Medium';
                          return 'Low';
                        })()}
                      </span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">Clauses Found</span>
                      <span className="metric-value">{clausesCount}</span>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'risks' && (
                <div className="analysis-section">
                  {risksCount > 0 ? (
                    result.analysis.risks.map((risk, i) => (
                      <div
                        key={i}
                        className={`risk-item risk-item--${(risk.risk_level || 'medium').toLowerCase()}`}
                      >
                        <div className="risk-item-header">
                          <strong>{risk.clause}</strong>
                          <span className={`risk-badge risk-badge--${(risk.risk_level || 'medium').toLowerCase()}`}>
                            {risk.risk_level || 'Medium'}
                          </span>
                        </div>
                        <p>{risk.reason}</p>
                      </div>
                    ))
                  ) : (
                    <p className="empty-state">No risk flags identified.</p>
                  )}
                </div>
              )}

              {activeTab === 'clauses' && (
                <div className="analysis-section">
                  {(() => {
                    const all     = result.analysis.clauses || [];
                    const found   = all.filter(c => c.found);
                    const missing = all.filter(c => !c.found);
                    return (
                      <>
                        {found.length > 0 ? (
                          found.map((clause, i) => (
                            <div key={i} className="clause-item">
                              <strong>{clause.clause_type}</strong>
                              <p className="clause-excerpt">
                                "{(clause.text || '').slice(0, 200)}
                                {(clause.text || '').length > 200 ? '…' : ''}"
                              </p>
                            </div>
                          ))
                        ) : (
                          <p className="empty-state">No clauses identified.</p>
                        )}
                        {missing.length > 0 && (
                          <div className="missing-clauses">
                            <h4 className="missing-heading">Not Found ({missing.length})</h4>
                            <div className="missing-list">
                              {missing.map((clause, i) => (
                                <span key={i} className="missing-tag">{clause.clause_type}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="panel-empty">
            <p>Upload and analyze a contract to see results here.</p>
          </div>
        )}
      </div>

    </div>
  );
}
