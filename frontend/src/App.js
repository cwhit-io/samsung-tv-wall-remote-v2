import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
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
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/status" element={<Status />} />
          <Route path="/debug" element={<Debug />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
