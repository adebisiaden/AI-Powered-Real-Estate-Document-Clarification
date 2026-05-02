// src/App.js
import { useEffect, useState } from 'react';
import { useAuth } from './contexts/AuthContext';
import { FileUploadDropzone } from './components/FileUploadDropzone';
import LoginPage from './components/LoginPage';
import UserMenu from './components/UserMenu';
import './App.css';

function App() {
  const { user, token, loading } = useAuth();
  const [guestMode, setGuestMode] = useState(false);

  // Listen for the "Continue as Guest" event fired by LoginPage
  useEffect(() => {
    const handler = () => setGuestMode(true);
    document.addEventListener('lease:continue-as-guest', handler);
    return () => document.removeEventListener('lease:continue-as-guest', handler);
  }, []);

  // If the guest signs in mid-session, drop out of guest mode
  useEffect(() => {
    if (user) setGuestMode(false);
  }, [user]);

  // ── Loading splash ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="App-loading">
        <span className="App-loading-dot" />
        <span className="App-loading-dot" />
        <span className="App-loading-dot" />
      </div>
    );
  }

  // ── Login screen ────────────────────────────────────────────────────────────
  if (!user && !guestMode) {
    return <LoginPage />;
  }

  // ── Main app ────────────────────────────────────────────────────────────────
  return (
    <div className="App">
      <nav className="App-nav">
        <div className="App-nav-left">
          <span className="App-nav-title">Contract Review</span>
          <span className="App-nav-tagline">AI-powered contract analysis</span>
        </div>

        <div className="App-nav-right">
          {user ? (
            <UserMenu />
          ) : (
            <>
              <span className="App-nav-guest-label">Guest mode</span>
              <button
                className="App-nav-signin-btn"
                onClick={() => setGuestMode(false)}
              >
                Sign in to save
              </button>
            </>
          )}
        </div>
      </nav>

      <main className="App-main">
        {/* token is null for guests — api.js routes to /analyse/guest automatically */}
        <FileUploadDropzone token={token} />
      </main>
    </div>
  );
}

export default App;
