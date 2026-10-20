import {
  ArrowRight,
  ArrowUpRight,
  Layers3,
  Leaf,
  Sprout,
} from "lucide-react";
import React, { useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { ADMIN_LINKS, clearAdminSession, isAdminPath, useAdminVerified } from "./adminSession";
import type { Component, Project } from "./types";

import { date } from "./utils";

export function cardExcerpt(value: string, maxWords = 20): string {
  const words = value.trim().split(/\s+/).filter(Boolean);
  return words.length > maxWords ? `${words.slice(0, maxWords).join(" ")}…` : words.join(" ");
}
export function projectGeographyLabel(project: Project): string {
  if (project.scope === "Boshqa") return "Boshqa";
  if (project.scope === "GitHub") return "GitHub";
  if (project.country === "Uzbekistan" || project.scope === "Uzbekistan") return "O‘zbekiston";
  return project.country || (project.scope === "Global" ? "Global" : "Davlat noma’lum");
}
export function External({
  href,
  children,
  className = "",
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  if (!href.startsWith("https://")) return <span>{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
    >
      {children}
      <ArrowUpRight size={14} />
    </a>
  );
}
function AdminMenu() {
  const navigate = useNavigate();
  return (
    <nav aria-label="Admin menyusi" className="admin-menu">
      {ADMIN_LINKS.map(([to, label]) => (
        <NavLink key={to} to={to} end={to === "/admin/status"}>
          {label}
        </NavLink>
      ))}
      <button
        type="button"
        className="admin-logout"
        onClick={() => {
          clearAdminSession();
          navigate("/", { replace: true });
        }}
      >
        Chiqish
      </button>
    </nav>
  );
}
export function Header() {
  // Inside a verified admin session the public menu is replaced by the admin menu;
  // the logo still leads to the public home page.
  const { pathname } = useLocation();
  const adminOpen = useAdminVerified() && isAdminPath(pathname);
  return (
    <header className={adminOpen ? "header header-admin" : "header"}>
      <div className="header-inner">
        <Link className="brand" to="/" aria-label="Izlanish bosh sahifa">
          <span className="brand-icon">
            <Sprout size={25} />
          </span>
          izlanish<span className="brand-dot">.</span>
        </Link>
        {adminOpen ? (
          <AdminMenu />
        ) : (
          <nav aria-label="Asosiy menyu">
            <NavLink to="/" end>
              <span className="flag">●</span> Bosh sahifa
            </NavLink>
            <NavLink to="/loyihalar">Loyihalar</NavLink>
            <NavLink to="/boshqa">Boshqa</NavLink>
            <NavLink to="/arxiv">Arxiv</NavLink>
            <NavLink to="/manbalar">Manbalar</NavLink>
          </nav>
        )}
        {!adminOpen && <span className="header-note">Haqiqiy loyihalar, asl manbalar.</span>}
      </div>
    </header>
  );
}
export function Footer() {
  return (
    <footer>
      <Link className="footer-brand" to="/">
        izlanish.
      </Link>
      <p>Haqiqiy loyihalar va ularning manbalari.</p>
      <span>Faktlar — manbalardan. Tahlil — alohida.</span>
    </footer>
  );
}
export function NotFound() {
  // Shared by unknown URLs and the hidden admin area, so both look identical.
  const navigate = useNavigate();
  return (
    <main className="page empty-state not-found">
      <h1>Bunday sahifa mavjud emas</h1>
      <p>Siz qidirgan manzil topilmadi.</p>
      <button type="button" className="not-found-back" onClick={() => navigate("/", { replace: true })}>
        Orqaga
      </button>
    </main>
  );
}
export function ErrorBox({ retry }: { retry: () => void }) {
  return (
    <div role="alert" className="notice error">
      Ma’lumotni yuklab bo‘lmadi. Ulanishni tekshiring.
      <button onClick={retry}>Qayta urinish</button>
    </div>
  );
}
export function Loading() {
  return (
    <div role="status" className="loading">
      <span className="spinner" /> Ma’lumotlar yuklanmoqda…
    </div>
  );
}
export function ProjectImage({ project }: { project: Project }) {
  const [failed, setFailed] = useState(false);
  return project.images.length > 0 && !failed ? (
    <img
      className="project-image"
      src={project.images[0].url}
      alt={`${project.name} — manbadagi rasm`}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  ) : (
    <div className="image-placeholder">
      <Layers3 size={25} />
      <span className="project-initial">{project.name.slice(0,1).toLocaleUpperCase()}</span>
    </div>
  );
}
export function Card({
  project: p,
  categories,
}: {
  project: Project;
  categories: Record<string, string>;
}) {
  return (
    <article className="project-card">
      <div className="card-top">
        <span className="category">
          <Leaf size={13} />
          {categories[p.primary_sector] || p.primary_sector || categories[p.category] || "Boshqa"}
        </span>
        <span className="card-date">{projectGeographyLabel(p)} · {date(p.published_at)}{p.date_estimated ? " (taxminiy)" : ""}</span>
      </div>
      <div className="card-body">
        <div className="card-copy">
          <Link to={`/loyiha/${p.id}`} className="project-title">
            {p.name}
            <ArrowUpRight size={20} />
          </Link>
          <p className="summary">{cardExcerpt(p.short_description || p.summary_uz)}</p>
          {p.scope === "Boshqa" && <p className="card-section-note"><strong>AI aniqlay olmadi.</strong> {p.section_reason}</p>}
          {p.problem_statement && <p className="card-problem"><strong>Qanday muammoni hal qiladi?</strong> {cardExcerpt(p.problem_statement, 24)}</p>}
          <p className="card-evidence">{p.catalog_score === null || p.score_pending ? "Baholanmagan" : `${p.catalog_score.toFixed(1)} / 10`} · {p.source_count} ta manba</p>
        </div>
        <ProjectImage project={p} />
      </div>
      <div className="sector-chips">
        {p.sectors?.slice(1).map((sector) => (
          <span className="tag" key={sector}>
            {categories[sector] || sector}
          </span>
        ))}
      </div>
      <div className="card-bottom">
        <Link to={`/loyiha/${p.id}`}>
          Batafsil <ArrowRight size={16} />
        </Link>
      </div>
    </article>
  );
}
export function Ratings({
  title,
  components,
  total,
}: {
  title: string;
  components: Record<string, Component>;
  total: number;
}) {
  return (
    <section className="detail-section">
      <h2>
        {title}
        <span className="rating-total">
          {total.toFixed(1)} <small>/ 10</small>
        </span>
      </h2>
      {Object.entries(components).map(([key, c]) => (
        <div className="rating-row" key={key}>
          <div>
            <span>{c.label}</span>
            <strong>
              {c.score} / {c.max}
            </strong>
          </div>
          <progress value={c.score} max={c.max} />
          {c.reason && <p>{c.reason}</p>}
        </div>
      ))}
    </section>
  );
}
