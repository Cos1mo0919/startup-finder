import {
  ArrowRight,
  ArrowUpRight,
  Layers3,
  Leaf,
  Sprout,
} from "lucide-react";
import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import type { Component, Project } from "./types";

import { audienceLabels } from "./labels";
import { date } from "./utils";
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
export function Header() {
  return (
    <header className="header">
      <div className="header-inner">
        <Link className="brand" to="/" aria-label="Izlanish bosh sahifa">
          <span className="brand-icon">
            <Sprout size={25} />
          </span>
          izlanish<span className="brand-dot">.</span>
        </Link>
        <nav aria-label="Asosiy menyu">
          <NavLink to="/" end>
            <span className="flag">●</span> Bosh sahifa
          </NavLink>
          <NavLink to="/loyihalar">Loyihalar</NavLink>
          <NavLink to="/arxiv">Arxiv</NavLink>
          <NavLink to="/manbalar">Manbalar</NavLink>
        </nav>
        <span className="header-note">Yaxshi g‘oyalar e’tiborga loyiq.</span>
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
      <p>Haqiqiy muammolarni hal qilayotgan loyihalar.</p>
      <span>Faktlar — manbalardan. Tahlil — alohida.</span>
    </footer>
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
      <Layers3 size={32} />
      <span>Rasm mavjud emas</span>
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
          {categories[p.primary_sector || p.category] || "Boshqa"}
        </span>
        <span className="card-date">{date(p.published_at)}</span>
      </div>
      <div className="card-body">
        <div className="card-copy">
          <Link to={`/loyiha/${p.id}`} className="project-title">
            {p.name}
            <ArrowUpRight size={20} />
          </Link>
          <p className="card-problem"><strong>Qanday muammoni hal qiladi?</strong> {p.problem_statement}</p>
          <p className="card-audience"><span>Kim uchun?</span><strong>{p.problem_subject || p.audience_groups.join(", ") || audienceLabels[p.audience]}</strong></p>
          <p className="summary"><strong>Yechim</strong> {p.solution_uz}</p>
          <p className="card-evidence">Dalil: {p.source_count} ta manba · Tasdiqlanganlik {p.confidence.toFixed(1)}/10</p>
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
