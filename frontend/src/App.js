import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './components/Home';
import Status from './components/Status';
import Debug from './components/Debug';
import './App.css';

function App() {
  // Read PUBLIC_URL and strip any trailing slashes so basename like '/ui/' -> '/ui'
  const rawPublicUrl = process.env.PUBLIC_URL || '';
  const basename = rawPublicUrl.replace(/\/+$/, '');

  return (
    <Router basename={basename || '/'}>
      <div className="min-h-screen bg-slate-950">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/status" element={<Status />} />
          <Route path="/debug" element={<Debug />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
