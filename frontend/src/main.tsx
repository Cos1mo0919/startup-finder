import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import { Footer, Header } from "./components";
import { Detail } from "./Detail";
import { Home } from "./Home";
import { ArchivePage, DashboardPage, SourcesPage } from "./Intelligence";
import { AdminPage } from "./Admin";
import "./style.css";
import "./intelligence-theme.css";
function NotFound() {
  return (
    <main className="page empty-state">
      <h1>Sahifa topilmadi</h1>
      <Link to="/">Bosh sahifaga qaytish →</Link>
    </main>
  );
}
function App() {
  return (
    <BrowserRouter>
      <Header />
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/loyihalar" element={<Home />} />
        <Route path="/arxiv" element={<ArchivePage />} />
        <Route path="/loyiha/:id" element={<Detail />} />
        <Route path="/muammolar" element={<Navigate to="/admin" replace />} />
        <Route path="/muammo/:id" element={<Navigate to="/admin" replace />} />
        <Route path="/goyalar" element={<Navigate to="/admin" replace />} />
        <Route path="/goya/:id" element={<Navigate to="/admin" replace />} />
        <Route path="/signallar" element={<Navigate to="/admin" replace />} />
        <Route path="/sektorlar" element={<Navigate to="/admin" replace />} />
        <Route path="/manbalar" element={<SourcesPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/admin/status" element={<AdminPage />} />
        <Route path="/admin/review" element={<AdminPage section="review" />} />
        <Route path="/admin/sources" element={<AdminPage section="sources" />} />
        <Route path="/admin/muammolar" element={<AdminPage section="problems" />} />
        <Route path="/admin/muammo/:id" element={<AdminPage section="problem" />} />
        <Route path="/admin/goyalar" element={<AdminPage section="ideas" />} />
        <Route path="/admin/goya/:id" element={<AdminPage section="idea" />} />
        <Route path="/admin/signallar" element={<AdminPage section="signals" />} />
        <Route path="/admin/sektorlar" element={<AdminPage section="sectors" />} />
        <Route path="/status" element={<AdminPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <Footer />
    </BrowserRouter>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
