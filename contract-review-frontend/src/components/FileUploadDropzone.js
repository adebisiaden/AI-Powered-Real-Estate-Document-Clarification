import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { analyseFile } from '../api';
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

// token is null for guests, Firebase ID token string for signed-in users
export function FileUploadDropzone({ token }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('summary');
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pdfUrl, setPdfUrl] = useState(null);
  const pdfContainerRef = useRef(null);
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
  }, []);

  const pickFile = useCallback((f) => {
    if (!f || !isAllowedFile(f)) {
      setFile(null);
      setError('Only PDF or DOCX files are allowed.');
      setResult(null);
      return;
    }
    setFile(f);
    setError(null);
    setResult(null);
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    pickFile(e.dataTransfer?.files?.[0]);
  }, [pickFile]);

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

  const onInputChange = useCallback((e) => {
    pickFile(e.target.files?.[0]);
    e.target.value = '';
  }, [pickFile]);

  const upload = async () => {
    if (!file) return;
    resetMessages();
    setUploading(true);
    try {
      // analyseFile picks /analyse/guest (no token) or /analyse (with token)
      const data = await analyseFile(file, token);
      setResult(data);
      setActiveTab('summary');
    } catch (err) {
      setError(err.message || 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  // New backend shape: analysis.clauses[] each has { found, type, risk, flag, excerpt, plain_english }
  const analysis      = result?.analysis ?? {};
  const clauses       = analysis.clauses ?? [];
  const foundClauses  = clauses.filter(c => c.found);
  const missingClauses = clauses.filter(c => !c.found);
  const highRiskItems = clauses.filter(c => c.found && c.risk === 'High');
  const medRiskItems  = clauses.filter(c => c.found && c.risk === 'Medium');
  const flaggedItems  = clauses.filter(c => c.found && c.flag);
  const isComplete    = !!result;

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

          {/* Guest notice */}
          {!token && (
            <p style={{
              fontSize: '0.78rem',
              color: '#92400e',
              background: '#fffbeb',
              border: '1px solid #fde68a',
              borderRadius: '6px',
              padding: '0.5rem 0.75rem',
              margin: '0.5rem 0 0',
            }}>
              👤 Guest mode — analysis won't be saved to an account.
            </p>
          )}

          <button
            type="button"
            className="upload-btn"
            onClick={(e) => { e.stopPropagation(); upload(); }}
            disabled={!file || uploading}
          >
            {uploading ? 'Analyzing…' : 'Upload & Analyze'}
          </button>

          {uploading && (
            <div className="progress-wrap" aria-live="polite">
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: '100%', animation: 'pulse 1.5s infinite' }} />
              </div>
              <span className="analyzing-label">Analyzing with Claude AI…</span>
            </div>
          )}

          {isComplete && (
            <div className="status-complete" role="status">
              ✓ Analysis complete — {file?.name}
              {token && result?.record_id && (
                <span style={{ display: 'block', fontSize: '0.75rem', color: '#6b7280', marginTop: '2px' }}>
                  Saved to your account
                </span>
              )}
            </div>
          )}

          {error && (
            <div className="alert alert--error" role="alert">{error}</div>
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
                <button className="pdf-nav-btn" onClick={() => setPageNumber(p => Math.max(1, p - 1))} disabled={pageNumber <= 1}>
                  ← Prev
                </button>
                <span className="pdf-page-label">Page {pageNumber} of {numPages ?? '…'}</span>
                <button className="pdf-nav-btn" onClick={() => setPageNumber(p => Math.min(numPages ?? p, p + 1))} disabled={pageNumber >= (numPages ?? 1)}>
                  Next →
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="panel panel--right">
        {isComplete ? (
          <>
            <div className="tab-bar">
              <button className={`tab-btn ${activeTab === 'summary'  ? 'tab-btn--active' : ''}`} onClick={() => setActiveTab('summary')}>Summary</button>
              <button className={`tab-btn ${activeTab === 'risks'    ? 'tab-btn--active' : ''}`} onClick={() => setActiveTab('risks')}>
                Risk Flags{flaggedItems.length > 0 ? ` (${flaggedItems.length})` : ''}
              </button>
              <button className={`tab-btn ${activeTab === 'clauses'  ? 'tab-btn--active' : ''}`} onClick={() => setActiveTab('clauses')}>
                Clauses{foundClauses.length > 0 ? ` (${foundClauses.length})` : ''}
              </button>
            </div>

            <div className="tab-content">

              {/* ── SUMMARY TAB ── */}
              {activeTab === 'summary' && (
                <div className="analysis-section">
                  {analysis.summary && (
                    <p className="analysis-summary">{analysis.summary}</p>
                  )}
                  <div className="metrics-row">
                    <div className="metric-card">
                      <span className="metric-label">Overall Risk</span>
                      <span className={`metric-value risk-${(analysis.overall_risk || 'low').toLowerCase()}`}>
                        {analysis.overall_risk || '—'}
                      </span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">Monthly Rent</span>
                      <span className="metric-value">{analysis.monthly_rent || '—'}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">Lease Term</span>
                      <span className="metric-value">{analysis.lease_term || '—'}</span>
                    </div>
                    <div className="metric-card">
                      <span className="metric-label">Clauses Found</span>
                      <span className="metric-value">{foundClauses.length}</span>
                    </div>
                  </div>

                  {analysis.recommended_action && (
                    <div style={{
                      marginTop: '1rem',
                      padding: '0.75rem 1rem',
                      borderRadius: '8px',
                      background: analysis.recommended_action === 'Looks reasonable' ? '#f0fdf4' :
                                  analysis.recommended_action === 'Seek advice before signing' ? '#fef2f2' : '#fffbeb',
                      border: `1px solid ${analysis.recommended_action === 'Looks reasonable' ? '#bbf7d0' :
                               analysis.recommended_action === 'Seek advice before signing' ? '#fecaca' : '#fde68a'}`,
                      fontSize: '0.875rem',
                      fontWeight: 600,
                    }}>
                      📋 {analysis.recommended_action}
                    </div>
                  )}

                  {analysis.tenant_friendly_terms?.length > 0 && (
                    <div style={{ marginTop: '1rem' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>✅ Tenant-Friendly Terms</h4>
                      <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#374151' }}>
                        {analysis.tenant_friendly_terms.map((t, i) => <li key={i}>{t}</li>)}
                      </ul>
                    </div>
                  )}

                  {analysis.top_concerns?.length > 0 && (
                    <div style={{ marginTop: '1rem' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>⚠️ Top Concerns</h4>
                      <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#374151' }}>
                        {analysis.top_concerns.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* ── RISKS TAB ── */}
              {activeTab === 'risks' && (
                <div className="analysis-section">
                  {flaggedItems.length > 0 ? (
                    flaggedItems.map((clause, i) => (
                      <div key={i} className={`risk-item risk-item--${(clause.risk || 'medium').toLowerCase()}`}>
                        <div className="risk-item-header">
                          <strong>{clause.type}</strong>
                          <span className={`risk-badge risk-badge--${(clause.risk || 'medium').toLowerCase()}`}>
                            {clause.risk || 'Medium'}
                          </span>
                        </div>
                        {clause.excerpt && (
                          <p style={{ fontSize: '0.8rem', color: '#6b7280', fontStyle: 'italic', margin: '0.25rem 0' }}>
                            "{clause.excerpt}"
                          </p>
                        )}
                        <p>{clause.flag}</p>
                      </div>
                    ))
                  ) : (
                    <p className="empty-state">No risk flags identified.</p>
                  )}
                </div>
              )}

              {/* ── CLAUSES TAB ── */}
              {activeTab === 'clauses' && (
                <div className="analysis-section">
                  {foundClauses.length > 0 ? (
                    foundClauses.map((clause, i) => (
                      <div key={i} className="clause-item">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <strong>{clause.type}</strong>
                          {clause.risk && clause.risk !== 'None' && (
                            <span className={`risk-badge risk-badge--${clause.risk.toLowerCase()}`}>
                              {clause.risk}
                            </span>
                          )}
                        </div>
                        <p style={{ fontSize: '0.85rem', color: '#374151', margin: '0.35rem 0 0' }}>
                          {clause.plain_english}
                        </p>
                        {clause.excerpt && (
                          <p className="clause-excerpt">
                            "{clause.excerpt.slice(0, 200)}{clause.excerpt.length > 200 ? '…' : ''}"
                          </p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="empty-state">No clauses identified.</p>
                  )}

                  {missingClauses.length > 0 && (
                    <div className="missing-clauses">
                      <h4 className="missing-heading">Not Found ({missingClauses.length})</h4>
                      <div className="missing-list">
                        {missingClauses.map((clause, i) => (
                          <span key={i} className="missing-tag">{clause.type}</span>
                        ))}
                      </div>
                    </div>
                  )}
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
