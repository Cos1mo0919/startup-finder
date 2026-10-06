import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Footer, Header } from "./components";
import { Detail } from "./Detail";
import { Home } from "./Home";
import { StatusPage } from "./StatusPage";
import "./style.css";
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
        <Route path="/" element={<Home />} />
        <Route path="/loyiha/:id" element={<Detail />} />
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
