import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Footer, Header } from "./components";
import { Detail } from "./Detail";
import { Home } from "./Home";
import { ArchivePage, DashboardPage, ProblemsPage, ProblemDetailPage, IdeasPage, IdeaDetailPage, SignalsPage, SectorsPage, SourcesPage } from "./Intelligence";
import { StatusPage } from "./StatusPage";
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
        <Route path="/muammolar" element={<ProblemsPage />} />
        <Route path="/muammo/:id" element={<ProblemDetailPage />} />
        <Route path="/goyalar" element={<IdeasPage />} />
        <Route path="/goya/:id" element={<IdeaDetailPage />} />
        <Route path="/signallar" element={<SignalsPage />} />
        <Route path="/sektorlar" element={<SectorsPage />} />
        <Route path="/manbalar" element={<SourcesPage />} />
        <Route path="/status" element={<StatusPage />} />
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
