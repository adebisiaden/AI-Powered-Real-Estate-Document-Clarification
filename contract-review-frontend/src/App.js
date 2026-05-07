// src/App.js
import { useEffect, useState } from 'react';
import { useAuth } from './contexts/AuthContext';
import { FileUploadDropzone } from './components/FileUploadDropzone';
import LoginPage from './components/LoginPage';
import UserMenu from './components/UserMenu';
import HistoryPage from './components/HistoryPage';
import './App.css';

function App() {
  const { user, token, loading } = useAuth();
  const [guestMode, setGuestMode] = useState(false);
  const [page, setPage] = useState('upload');

  useEffect(() => {
    const handler = () => setGuestMode(true);
    document.addEventListener('lease:continue-as-guest', handler);
    return () => document.removeEventListener('lease:continue-as-guest', handler);
  }, []);

  useEffect(() => {
    if (user) setGuestMode(false);
  }, [user]);

  // Reset to upload page if user signs out
  useEffect(() => {
    if (!user && !guestMode) setPage('upload');
  }, [user, guestMode]);

  if (loading) {
    return (
      <div className="App-loading">
        <span className="App-loading-dot" />
        <span className="App-loading-dot" />
        <span className="App-loading-dot" />
      </div>
    );
  }

  if (!user && !guestMode) {
    return <LoginPage />;
  }

  return (
    <div className="App">
      <nav className="App-nav">
        <div className="App-nav-left">
          <img src="/logo-icon-only.png" alt="LegalEyes" className="App-nav-logo" />
          <div className="App-nav-brand">
            <span className="App-nav-title"><strong>LEGAL</strong>EYES</span>
            <span className="App-nav-tagline">AI-Powered Contract Review</span>
          </div>
        </div>

        {user && (
          <div className="App-nav-center">
            <button
              className={`App-nav-tab ${page === 'upload' ? 'App-nav-tab--active' : ''}`}
              onClick={() => setPage('upload')}
            >
              Analyse
            </button>
            <button
              className={`App-nav-tab ${page === 'history' ? 'App-nav-tab--active' : ''}`}
              onClick={() => setPage('history')}
            >
              History
            </button>
          </div>
        )}

        <div className="App-nav-right">
          {user ? (
            <UserMenu />
          ) : (
            <>
              <span className="App-nav-guest-badge">Guest mode</span>
              <button
                className="App-nav-signin-btn"
                onClick={() => setGuestMode(false)}
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </nav>

      <main className="App-main">
        {page === 'upload' && <FileUploadDropzone token={token} />}
        {page === 'history' && user && <HistoryPage token={token} />}
      </main>
    </div>
  );
}

export default App;
