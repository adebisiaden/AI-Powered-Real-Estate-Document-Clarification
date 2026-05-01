import { FileUploadDropzone } from './components/FileUploadDropzone';
import './App.css';

function App() {
  return (
    <div className="App">
      <nav className="App-nav">
        <span className="App-nav-title">Contract Review</span>
        <span className="App-nav-tagline">AI-powered contract analysis</span>
      </nav>

      <main className="App-main">
        <FileUploadDropzone />
      </main>
    </div>
  );
}

export default App;
