import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { clearAdminSession, isAdminPath } from "./adminSession";
import { Footer, Header, NotFound } from "./components";
import { Detail } from "./Detail";
import { Home } from "./Home";
import { ArchivePage, DashboardPage, SourcesPage } from "./Intelligence";
import { AdminPage } from "./Admin";
import "./style.css";
import "./intelligence-theme.css";
import "./controls.css";
function AdminSessionGuard() {
  // Visiting any public page ends the admin session, so typing /admin again
  // without the key shows the ordinary "not found" page.
  const { pathname } = useLocation();
  useEffect(() => {
    if (!isAdminPath(pathname)) clearAdminSession();
  }, [pathname]);
  return null;
}
function App() {
  return (
    <BrowserRouter>
      <AdminSessionGuard />
      <Header />
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/loyihalar" element={<Home />} />
        <Route path="/boshqa" element={<Home section="boshqa" />} />
        <Route path="/arxiv" element={<ArchivePage />} />
        <Route path="/loyiha/:id" element={<Detail />} />
        <Route path="/manbalar" element={<SourcesPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/admin/status" element={<AdminPage />} />
        <Route path="/admin/review" element={<AdminPage section="review" />} />
        <Route path="/admin/catalog" element={<AdminPage section="catalog" />} />
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
