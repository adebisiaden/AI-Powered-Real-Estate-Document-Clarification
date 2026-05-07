// src/components/AnalysisResults.js
import { useState } from 'react';
import './FileUploadDropzone.css';

export default function AnalysisResults({ result }) {
  const [activeTab, setActiveTab] = useState('summary');

  if (!result || result.status !== 'success') {
    return (
      <div className="results-empty">
        <p>Select a document to view its analysis.</p>
      </div>
    );
  }

  const risks        = result.analysis?.risks || [];
  const allClauses   = result.analysis?.clauses || [];
  const foundClauses = allClauses.filter(c => c.found);
  const missing      = allClauses.filter(c => !c.found);
  const risksCount   = risks.length;
  const clausesCount = foundClauses.length;

  const riskLevel = risks.some(r => r.risk_level === 'High')   ? 'High'
                  : risks.some(r => r.risk_level === 'Medium') ? 'Medium'
                  : 'Low';

  return (
    <div className="results-root">
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
          Clauses{clausesCount > 0 ? ` (${clausesCount})` : ''}
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
                <span className="metric-value">{riskLevel}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Risk Flags</span>
                <span className="metric-value">{risksCount}</span>
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
            {risksCount > 0 ? risks.map((risk, i) => (
              <div key={i} className={`risk-item risk-item--${(risk.risk_level || 'medium').toLowerCase()}`}>
                <div className="risk-item-header">
                  <strong>{(risk.clause || '').length > 80 ? (risk.clause || '').slice(0, 80) + '…' : risk.clause}</strong>
                  <span className={`risk-badge risk-badge--${(risk.risk_level || 'medium').toLowerCase()}`}>
                    {risk.risk_level || 'Medium'}
                  </span>
                </div>
                <p>{risk.reason}</p>
              </div>
            )) : (
              <p className="empty-state">No risk flags identified.</p>
            )}
          </div>
        )}

        {activeTab === 'clauses' && (
          <div className="analysis-section">
            {foundClauses.length > 0 ? foundClauses.map((clause, i) => (
              <div key={i} className="clause-item">
                <strong>{clause.clause_type}</strong>
                <p className="clause-excerpt">
                  "{(clause.text || '').slice(0, 200)}{(clause.text || '').length > 200 ? '…' : ''}"
                </p>
              </div>
            )) : (
              <p className="empty-state">No clauses identified.</p>
            )}
            {missing.length > 0 && (
              <div className="missing-clauses">
                <h4 className="missing-heading">Not Found ({missing.length})</h4>
                <div className="missing-list">
                  {missing.map((c, i) => (
                    <span key={i} className="missing-tag">{c.clause_type}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
