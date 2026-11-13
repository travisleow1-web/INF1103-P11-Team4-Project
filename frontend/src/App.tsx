import { useState } from 'react';
import './App.css';

// 1. Define TypeScript types for your data structures
interface TaskResult {
  id: number;
  input: string;
  output: string;
  timestamp: string;
}

export default function App() {
  // 2. TypeScript state management
  const [inputText, setInputText] = useState<string>('');
  const [history, setHistory] = useState<TaskResult[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // 3. Action handler (simulating calling your Python logic)
  const handleProcess = () => {
    if (!inputText.trim()) return;

    setLoading(true);

    // Simulated task execution
    setTimeout(() => {
      const newEntry: TaskResult = {
        id: Date.now(),
        input: inputText,
        output: `Processed: ${inputText.toUpperCase()}`,
        timestamp: new Date().toLocaleTimeString(),
      };

      setHistory((prev) => [newEntry, ...prev]);
      setInputText('');
      setLoading(false);
    }, 400);
  };

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', fontFamily: 'sans-serif', padding: 16 }}>
      <h1>Project Control Panel</h1>

      {/* Input Section */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input
          type="text"
          value={inputText}
          placeholder="Enter parameters for Python logic..."
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleProcess()}
          style={{ flex: 1, padding: '8px 12px', fontSize: 16 }}
        />
        <button
          onClick={handleProcess}
          disabled={loading || !inputText.trim()}
          style={{ padding: '8px 16px', fontSize: 16, cursor: 'pointer' }}
        >
          {loading ? 'Running...' : 'Run Task'}
        </button>
      </div>

      {/* Results / History Table */}
      <h2>Execution History</h2>
      {history.length === 0 ? (
        <p style={{ color: '#888' }}>No tasks run yet.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ddd' }}>
              <th style={{ padding: 8 }}>Time</th>
              <th style={{ padding: 8 }}>Input</th>
              <th style={{ padding: 8 }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {history.map((item) => (
              <tr key={item.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: 8, color: '#666', fontSize: 14 }}>{item.timestamp}</td>
                <td style={{ padding: 8 }}>{item.input}</td>
                <td style={{ padding: 8, fontWeight: 'bold' }}>{item.output}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}