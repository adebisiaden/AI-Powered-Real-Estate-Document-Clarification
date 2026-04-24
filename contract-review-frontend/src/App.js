import { useState } from 'react';
import axios from 'axios';
import { apiUrl } from './api';
import { FileUploadDropzone } from './components/FileUploadDropzone';
import './App.css';

function App() {
  const [healthResponse, setHealthResponse] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const checkHealth = async () => {
    setLoading(true);
    setError(null);
    setHealthResponse(null);
    try {
      const { data } = await axios.get(apiUrl('/health'));
      setHealthResponse(data);
    } catch (e) {
      setError(e.response?.data?.detail ?? e.message ?? 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <nav className="App-nav">
        <span className="App-nav-title">Contract Review</span>
        <span className="App-nav-tagline">AI-powered contract analysis</span>
        <div className="App-nav-health">
          <button type="button" onClick={checkHealth} disabled={loading} className="health-btn">
            {loading ? 'Calling…' : 'Test /health'}
          </button>
          {healthResponse != null && (
            <pre className="health-output">{JSON.stringify(healthResponse, null, 2)}</pre>
          )}
          {error != null && <span className="health-error">{String(error)}</span>}
        </div>
      </nav>

      <main className="App-main">
        <FileUploadDropzone />
      </main>
    </div>
  );
}

export default App;
