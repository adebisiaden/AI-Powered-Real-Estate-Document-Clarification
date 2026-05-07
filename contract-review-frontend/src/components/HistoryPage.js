// src/components/HistoryPage.js
import { useEffect, useState } from 'react';
import { fetchHistory, fetchRecord, deleteRecord } from '../api';
import AnalysisResults from './AnalysisResults';
import './HistoryPage.css';

export default function HistoryPage({ token }) {
  const [records, setRecords]     = useState([]);
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [error, setError]         = useState(null);

  useEffect(() => {
    fetchHistory(token)
      .then(data => setRecords(data.analyses || []))
      .catch(() => setError('Could not load history.'))
      .finally(() => setLoading(false));
  }, [token]);

  const selectRecord = async (id) => {
    if (selected?.record_id === id) return;
    setLoadingDoc(true);
    try {
      const data = await fetchRecord(id, token);
      setSelected({ ...data, record_id: id });
    } catch {
      setError('Could not load document.');
    } finally {
      setLoadingDoc(false);
    }
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm('Delete this analysis? The next upload of the same file will re-analyse it.')) return;
    try {
      await deleteRecord(id, token);
      setRecords(prev => prev.filter(r => r.record_id !== id));
      if (selected?.record_id === id) setSelected(null);
    } catch {
      setError('Could not delete record.');
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric'
    });
  };

  return (
    <div className="history-layout">
      {/* LEFT — document list */}
      <div className="history-sidebar">
        <div className="history-sidebar-header">
          <h2>Past Analyses</h2>
          <span className="history-count">{records.length} document{records.length !== 1 ? 's' : ''}</span>
        </div>

        {loading && <p className="history-status">Loading…</p>}
        {error   && <p className="history-status history-status--error">{error}</p>}

        {!loading && records.length === 0 && (
          <p className="history-status">No analyses saved yet.</p>
        )}

        <ul className="history-list">
          {records.map((rec) => (
            <li
              key={rec.record_id}
              className={`history-item ${selected?.record_id === rec.record_id ? 'history-item--active' : ''}`}
              onClick={() => selectRecord(rec.record_id)}
            >
              <div className="history-item-row">
                <span className="history-item-name">
                  {rec.filename || 'Untitled'}
                </span>
                <button
                  className="history-delete-btn"
                  onClick={(e) => handleDelete(e, rec.record_id)}
                  title="Delete analysis"
                >
                  &times;
                </button>
              </div>
              <span className="history-item-date">{formatDate(rec.created_at)}</span>
              {rec.risk_level && (
                <span className={`history-risk-badge history-risk-badge--${rec.risk_level.toLowerCase()}`}>
                  {rec.risk_level}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* RIGHT — results panel */}
      <div className="history-results">
        {loadingDoc ? (
          <div className="history-results-loading">
            <span className="App-loading-dot" />
            <span className="App-loading-dot" />
            <span className="App-loading-dot" />
          </div>
        ) : selected ? (
          <AnalysisResults result={{ status: 'success', ...selected }} />
        ) : (
          <div className="results-empty">
            <p>Select a document on the left to view its analysis.</p>
          </div>
        )}
      </div>
    </div>
  );
}
