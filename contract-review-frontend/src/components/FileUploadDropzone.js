import { useCallback, useEffect, useRef, useState } from 'react'; // eslint-disable-line no-unused-vars
import { jsPDF } from 'jspdf';
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


export function FileUploadDropzone({ token }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPhase, setUploadPhase] = useState('idle'); // 'idle'|'uploading'|'analyzing'|'done'
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab]   = useState('summary');
  const [numPages, setNumPages]     = useState(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pdfUrl, setPdfUrl]         = useState(null);
  const pdfContainerRef             = useRef(null);
  const [pdfContainerWidth, setPdfContainerWidth] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');

  const ANIM_STEPS = [
    'Uploading…',
    'Reading document…',
    'Finding relevant clauses…',
    'Analysing with AI…',
    'Reading contract clauses…',
    'Assessing legal risks…',
    'Writing summary…',
    'Almost done…',
  ];

  useEffect(() => {
    if (!uploading) { setStatusMsg(''); return; }
    let i = 0;
    setStatusMsg(ANIM_STEPS[0]);
    const timer = setInterval(() => {
      i = Math.min(i + 1, ANIM_STEPS.length - 1);
      setStatusMsg(ANIM_STEPS[i]);
    }, 5000);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploading]);

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
    setStatusMsg('');
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
      setUploadPhase('idle');
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
    setUploadPhase('uploading');
    const formData = new FormData();
    formData.append('file', file);

    const endpoint = token ? apiUrl('/analyse/stream') : apiUrl('/analyse/guest/stream');
    const headers  = token ? { Authorization: `Bearer ${token}` } : {};

    try {
      const res = await fetch(endpoint, { method: 'POST', headers, body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let done = false;
      while (!done) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = JSON.parse(line.slice(6));
          if (data.type === 'status') {
            setUploadPhase('analyzing');
            setStatusMsg(data.message);
          } else if (data.type === 'done') {
            setUploadPhase('done');
            setResult(data);
            setActiveTab('summary');
            reader.cancel().catch(() => {});
            done = true;
            break;
          } else if (data.type === 'error') {
            throw new Error(data.message);
          }
        }
      }
    } catch (err) {
      setError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const risksCount   = result?.analysis?.risks?.length ?? 0;
  const clausesCount = result?.analysis?.clauses?.filter(c => c.found)?.length ?? 0;

  const downloadPDF = () => {
    const doc = new jsPDF({ unit: 'pt', format: 'a4' });
    const margin = 50;
    const pageW = doc.internal.pageSize.getWidth();
    const maxW  = pageW - margin * 2;
    let y = margin;

    const addPage = () => { doc.addPage(); y = margin; };

    const checkY = (needed = 20) => { if (y + needed > doc.internal.pageSize.getHeight() - margin) addPage(); };

    const h2 = (text) => {
      checkY(24);
      doc.setFont('helvetica', 'bold').setFontSize(13).setTextColor(0);
      doc.text(text, margin, y);
      y += 8;
      doc.setDrawColor(180).setLineWidth(0.5).line(margin, y, pageW - margin, y);
      y += 14;
    };
    const body = (text, indent = 0) => {
      doc.setFont('helvetica', 'normal').setFontSize(10).setTextColor(30);
      const lines = doc.splitTextToSize(text, maxW - indent);
      lines.forEach(line => { checkY(14); doc.text(line, margin + indent, y); y += 14; });
    };
    const spacer = (n = 12) => { y += n; };

    // Header
    doc.setFont('helvetica', 'bold').setFontSize(22).setTextColor(0);
    doc.text('Lease Lens', margin, y);
    y += 20;
    doc.setFont('helvetica', 'normal').setFontSize(10).setTextColor(100);
    doc.text('Contract Analysis Report', margin, y);
    y += 10;
    doc.text(`File: ${result.filename || file?.name || ''}`, margin, y);
    y += 10;
    doc.text(`Date: ${new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}`, margin, y);
    y += 6;
    doc.setDrawColor(60).setLineWidth(1).line(margin, y, pageW - margin, y);
    y += 24;

    // Summary
    h2('Summary');
    if (result.analysis?.summary) body(result.analysis.summary);
    spacer();

    const risks = result.analysis?.risks || [];
    const allClauses = result.analysis?.clauses || [];
    const foundClauses = allClauses.filter(c => c.found);
    const missingClauses = allClauses.filter(c => !c.found);

    const riskLevel = risks.some(r => r.risk_level === 'High') ? 'High'
      : risks.some(r => r.risk_level === 'Medium') ? 'Medium' : 'Low';

    body(`Risk Level: ${riskLevel}   |   Risk Flags: ${risks.length}   |   Clauses Found: ${foundClauses.length}`);
    spacer(20);

    // Risk Flags
    h2(`Risk Flags (${risks.length})`);
    if (risks.length === 0) {
      body('No risk flags identified.');
    } else {
      risks.forEach((risk, i) => {
        checkY(40);
        doc.setFont('helvetica', 'bold').setFontSize(10).setTextColor(0);
        doc.text(`${i + 1}. ${risk.clause}`, margin, y);
        doc.setFont('helvetica', 'bold').setFontSize(9).setTextColor(
          risk.risk_level === 'High' ? 180 : risk.risk_level === 'Medium' ? 140 : 80,
          risk.risk_level === 'High' ? 30 : risk.risk_level === 'Medium' ? 100 : 120,
          30
        );
        doc.text(`[${risk.risk_level || 'Medium'}]`, pageW - margin - 50, y, { align: 'right' });
        y += 14;
        body(risk.reason, 12);
        spacer(6);
      });
    }
    spacer(8);

    // Identified Clauses
    h2(`Identified Clauses (${foundClauses.length})`);
    if (foundClauses.length === 0) {
      body('No clauses identified.');
    } else {
      foundClauses.forEach((clause, i) => {
        checkY(40);
        doc.setFont('helvetica', 'bold').setFontSize(10).setTextColor(0);
        doc.text(`${i + 1}. ${clause.clause_type}`, margin, y);
        y += 14;
        if (clause.text) body(`"${clause.text.slice(0, 300)}${clause.text.length > 300 ? '…' : ''}"`, 12);
        spacer(6);
      });
    }

    if (missingClauses.length > 0) {
      spacer(8);
      h2(`Not Found (${missingClauses.length})`);
      body(missingClauses.map(c => c.clause_type).join(', '));
    }

    doc.save(`lease-lens-report-${(result.filename || 'analysis').replace(/\.[^.]+$/, '')}.pdf`);
  };

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
            {uploadPhase === 'uploading' ? 'Uploading…'
              : uploadPhase === 'analyzing' ? 'Analyzing…'
              : uploadPhase === 'done' ? 'Uploaded ✓'
              : 'Upload & Analyze'}
          </button>

          {(uploadPhase === 'analyzing' || uploadPhase === 'done') && !result?.status && (
            <div className="upload-uploaded-label" role="status">✓ Uploaded</div>
          )}

          {result?.status === 'success' && (
            <div className="status-complete" role="status">
              ✓ Analysis complete — {result.filename}
            </div>
          )}

          {result?.status === 'success' && (
            <button className="download-btn" onClick={downloadPDF}>
              Download Report (PDF)
            </button>
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
        ) : uploadPhase === 'analyzing' ? (
          <div className="panel-analyzing" aria-live="polite">
            <span className="panel-analyzing-msg">{statusMsg}</span>
            <div className="panel-analyzing-bar">
              <div className="panel-analyzing-bar-fill" />
            </div>
            <div className="panel-analyzing-dots">
              <span /><span /><span />
            </div>
          </div>
        ) : (
          <div className="panel-empty">
            <p>Upload and analyze a contract to see results here.</p>
          </div>
        )}
      </div>

    </div>
  );
}
