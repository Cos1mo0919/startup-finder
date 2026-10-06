import {
  ArrowDownWideNarrow,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CheckCheck,
  ChevronDown,
  Clock3,
  Globe2,
  MapPin,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sprout,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Project, Status } from "./types";

import { Card, ErrorBox, Loading } from "./components";
import { audienceLabels } from "./labels";
import { useApi } from "./useApi";
import { time } from "./utils";
export function Home() {
  const [params, setParams] = useSearchParams(),
    [query, setQuery] = useState(params.get("q") || ""),
    [retry, setRetry] = useState(0),
    [filtersOpen, setFiltersOpen] = useState(false);
  const meta = useApi<{ categories: Record<string, string>; years: number[] }>(
    "/api/meta",
  );
  const status = useApi<Status>("/api/status", retry);
  const period = params.get("period") || "today";
  const year = params.get("year") || "";
  const request = new URLSearchParams(params);
  if (!request.has("period")) request.set("period", "today");
  const results = useApi<{
    items: Project[];
    total: number;
    page: number;
    page_size: number;
  }>("/api/projects?" + request.toString(), retry);
  useEffect(() => {
    setQuery(params.get("q") || "");
  }, [params]);
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.delete("page");
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }
  function periodChange(value: string) {
    const next = new URLSearchParams(params);
    next.delete("page");
    next.delete("year");
    if (/^\d{4}$/.test(value)) {
      next.set("period", "all");
      next.set("year", value);
    } else next.set("period", value);
    setParams(next);
  }
  const title = params.get("q")
    ? "Qidiruv natijalari"
    : year
      ? `${year}-yil loyihalari`
      : period === "today"
        ? "Bugun O‘zbekistonda"
        : period === "7d"
          ? "Oxirgi 7 kun"
          : period === "30d"
            ? "Oxirgi 30 kun"
            : "Barcha loyihalar";
  const activeFilters = ["category", "city", "audience", "min_rating"].filter(
    (k) => params.get(k),
  ).length;
  return (
    <>
      <section className="hero">
        <div className="eyebrow">
          <span /> O‘ZBEKISTONNING YANGI G‘OYALARI
        </div>
        <h1>
          Bugunning loyihalari.
          <br />
          <em>Ertaning imkoniyatlari.</em>
        </h1>
        <p>
          Haqiqiy startaplar, foydali ishlanmalar va yangi yechimlar.
          <br className="desktop-break" /> Ishonchli manbalar bilan, o‘zbek
          tilida.
        </p>
        <form
          className="search-box"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            change("q", query);
          }}
        >
          <Search size={23} />
          <input
            aria-label="Loyihalarni qidirish"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Loyiha, startap yoki dastur qidiring..."
          />
          <button type="submit">
            Qidirish <ArrowRight size={17} />
          </button>
        </form>
        <div className="hero-notes">
          <span>
            <Clock3 size={14} /> Har soatda yangi qidiruv
          </span>
          <span>
            <CheckCheck size={15} /> Manbalar bilan tasdiqlangan
          </span>
          <span>
            <Globe2 size={14} /> Faqat O‘zbekiston
          </span>
        </div>
      </section>
      <main className="home-layout">
        <aside className={`filters ${filtersOpen ? "open" : ""}`}>
          <div className="aside-title">
            <SlidersHorizontal size={17} />
            <h2>Saralash</h2>
            <button
              className="mobile-close"
              onClick={() => setFiltersOpen(false)}
              aria-label="Filtrlarni yopish"
            >
              <X size={18} />
            </button>
          </div>
          <label>
            Yo‘nalish
            <select
              value={params.get("category") || ""}
              onChange={(e) => change("category", e.target.value)}
            >
              <option value="">Barcha yo‘nalishlar</option>
              {Object.entries(meta.data?.categories || {}).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Auditoriya
            <select
              value={params.get("audience") || ""}
              onChange={(e) => change("audience", e.target.value)}
            >
              <option value="">Barcha auditoriyalar</option>
              {Object.entries(audienceLabels).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            Shahar
            <input
              placeholder="Masalan, Toshkent"
              value={params.get("city") || ""}
              onChange={(e) => change("city", e.target.value)}
            />
          </label>
          <label>
            Eng kam foydalilik
            <select
              value={params.get("min_rating") || ""}
              onChange={(e) => change("min_rating", e.target.value)}
            >
              <option value="">Barcha reytinglar</option>
              {[3, 5, 7, 9].map((v) => (
                <option key={v} value={v}>
                  {v} va undan yuqori
                </option>
              ))}
            </select>
          </label>
          <button
            className="reset"
            onClick={() => {
              setParams({ period: "today" });
              setQuery("");
            }}
          >
            Filtrlarni tozalash
          </button>
          <div className="aside-explainer">
            <BookOpen size={22} />
            <h3>Shunchaki g‘oya emas.</h3>
            <p>
              Har bir loyihada uning mavjudligini ko‘rsatuvchi manba va dalil
              bo‘lishi kerak.
            </p>
            <Link to="/status">
              Qidiruv qanday ishlayapti? <ArrowUpRight size={14} />
            </Link>
          </div>
        </aside>
        <section className="feed" aria-label="Loyihalar lentasi">
          <div className="feed-header">
            <div>
              <div className="feed-kicker">KASHF ETING</div>
              <h2>{title}</h2>
              <p>O‘zbekistonda yaratilgan yoki unga bog‘liq loyihalar.</p>
            </div>
            <span className="result-count">
              {results.data?.total ?? 0} ta loyiha
            </span>
          </div>
          <div className="feed-toolbar">
            <div className="period-tabs" aria-label="Vaqt bo‘yicha filtr">
              {[
                ["today", "Bugun"],
                ["7d", "7 kun"],
                ["30d", "30 kun"],
                ["all", "Barchasi"],
              ].map(([k, v]) => (
                <button
                  key={k}
                  className={!year && period === k ? "selected" : ""}
                  onClick={() => periodChange(k)}
                >
                  {v}
                </button>
              ))}
              <label className="year-select">
                <span className="sr-only">Nashr yili</span>
                <select
                  aria-label="Nashr yili"
                  value={year}
                  onChange={(e) => periodChange(e.target.value || "all")}
                >
                  <option value="">Yil</option>
                  {(meta.data?.years || [2026, 2025, 2024, 2023, 2022]).map(
                    (y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ),
                  )}
                </select>
                <ChevronDown size={13} />
              </label>
            </div>
            <label className="sort">
              <ArrowDownWideNarrow size={16} />
              <select
                aria-label="Saralash tartibi"
                value={params.get("sort") || "date"}
                onChange={(e) => change("sort", e.target.value)}
              >
                <option value="date">Eng yangilari</option>
                <option value="rating">Reyting bo‘yicha</option>
                <option value="confidence">Ishonchlilik bo‘yicha</option>
                <option value="usefulness">Foydalilik bo‘yicha</option>
              </select>
            </label>
          </div>
          <button
            className="mobile-filter-button"
            onClick={() => setFiltersOpen(!filtersOpen)}
          >
            <SlidersHorizontal size={16} /> Filtrlar{" "}
            {activeFilters ? `(${activeFilters})` : ""}
          </button>
          {results.error ? (
            <ErrorBox retry={() => setRetry(retry + 1)} />
          ) : results.loading ? (
            <Loading />
          ) : results.data?.items.length ? (
            <div className="cards">
              {results.data.items.map((p) => (
                <Card
                  key={p.id}
                  project={p}
                  categories={meta.data?.categories || {}}
                />
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-art">
                <span className="orbit one" />
                <span className="orbit two" />
                <Sprout size={46} />
                <span className="small-star">✦</span>
              </div>
              <span className="empty-tag">YANGI IMKONIYATLAR KUTILMOQDA</span>
              <h3>
                {params.get("q") || activeFilters
                  ? "Mos loyiha topilmadi"
                  : period === "today"
                    ? "Bugungi kashfiyotlar hali oldinda"
                    : "Hozircha loyihalar topilmadi"}
              </h3>
              <p>
                {params.get("q") || activeFilters
                  ? "Qidiruv so‘zini yoki filtrlarni o‘zgartirib ko‘ring."
                  : "Tasdiqlangan yangi loyiha topilganda shu yerda paydo bo‘ladi. Har bir karta haqiqiy manbaga tayanadi."}
              </p>
              <button
                className="outline-button"
                onClick={() => periodChange("all")}
              >
                Barcha loyihalarni ko‘rish <ArrowRight size={16} />
              </button>
              <Link className="quiet-link" to="/status">
                Qidiruv holatini tekshirish
              </Link>
            </div>
          )}
          {results.data && results.data.total > results.data.page_size && (
            <div className="pagination">
              <button
                disabled={results.data.page === 1}
                onClick={() => change("page", String(results.data!.page - 1))}
              >
                ← Oldingi
              </button>
              <span>
                {results.data.page} /{" "}
                {Math.ceil(results.data.total / results.data.page_size)}
              </span>
              <button
                disabled={
                  results.data.page * results.data.page_size >=
                  results.data.total
                }
                onClick={() => change("page", String(results.data!.page + 1))}
              >
                Keyingi →
              </button>
            </div>
          )}
          <div className="feed-footnote">
            <ShieldCheck size={16} />
            <p>
              Reytinglar mavjud dalillarga asoslanadi. AI xulosalari
              tasdiqlangan faktlardan alohida ko‘rsatiladi.
            </p>
          </div>
        </section>
        <aside className="right-rail">
          <div className="live-card">
            <div className="live-label">
              <span
                className={
                  status.data?.last_run?.status === "completed"
                    ? "live-dot"
                    : "idle-dot"
                }
              />{" "}
              QIDIRUV HOLATI
            </div>
            <h3>
              Yangiliklardan
              <br />
              xabardor bo‘ling.
            </h3>
            <p>Manbalar har soatda tekshiriladi.</p>
            <div className="live-metric">
              <span>Keyingi qidiruv</span>
              <strong>{time(status.data?.next_run)}</strong>
            </div>
            <div className="live-metric">
              <span>Bugun topildi</span>
              <strong>
                {status.data?.today_projects ?? 0} <small>ta</small>
              </strong>
            </div>
            <Link to="/status">
              Batafsil holat <ArrowUpRight size={15} />
            </Link>
          </div>
          <div className="how-card">
            <h3>Nimalarni topamiz?</h3>
            {[
              [
                "01",
                "Haqiqiy loyihalar",
                "Prototip, ishga tushirilgan mahsulot yoki tasdiqlangan ishlanma.",
              ],
              [
                "02",
                "Turli yo‘nalishlar",
                "Tibbiyotdan qishloq xo‘jaligigacha. Faqat IT bilan cheklanmaymiz.",
              ],
              [
                "03",
                "Tekshirish mumkin",
                "Original manbalar, aniq sanalar va alohida tahlil.",
              ],
            ].map(([n, t, p]) => (
              <div key={n}>
                <span>{n}</span>
                <section>
                  <h4>{t}</h4>
                  <p>{p}</p>
                </section>
              </div>
            ))}
          </div>
          <div className="rail-note">
            <MapPin size={15} /> O‘zbekiston · Toshkent vaqti
          </div>
        </aside>
      </main>
    </>
  );
}
