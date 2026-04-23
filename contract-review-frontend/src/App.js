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
      <header className="App-header">
        <h1>Contract Review</h1>
        <p className="App-tagline">AI-powered contract analysis</p>

        <FileUploadDropzone />

        <div className="health-row">
          <button type="button" onClick={checkHealth} disabled={loading}>
            {loading ? 'Calling…' : 'Test /health'}
          </button>
          {healthResponse != null && (
            <pre className="health-output">{JSON.stringify(healthResponse, null, 2)}</pre>
          )}
          {error != null && <p className="health-error">{String(error)}</p>}
        </div>
      </header>
    </div>
  );
}

export default App;
