import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

import Home from './pages/HomePage/home';
import Situation from './pages/SituationPage/situation';
import Result from './pages/ResultPage/result';
import Preview from './pages/PreviewPage/preview';
import Dashboard from './pages/DashboardPage/dashboard';

function App() {
  return (
    <Router>
      <div
        style={{
          background: "linear-gradient(135deg, #1c0d2bff 0%, #2d0c4d 100%)",
          minHeight: "100vh"
        }}
      >

        { /* App Routes */ }
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/welcome" element={<Home />} />
          <Route path="/situation" element={<Situation />} />
          <Route path="/result" element={<Result />} />
          <Route path="/preview" element={<Preview />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
