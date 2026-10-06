import { Activity, Clock3 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Status } from "./types";

import { ErrorBox, External, Loading } from "./components";
import { countLabels, errorLabels, statusLabels } from "./labels";
import { useApi } from "./useApi";
import { date } from "./utils";
export function StatusPage() {
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setRefresh((v) => v + 1), 30000);
    return () => clearInterval(id);
  }, []);
  const { data: s, error, loading } = useApi<Status>("/api/status", refresh);
  if (error)
    return (
      <main className="page">
        <ErrorBox retry={() => setRefresh(refresh + 1)} />
      </main>
    );
  if (!s)
    return (
      <main className="page">
        <Loading />
      </main>
    );
  const run = s.last_run;
  return (
    <main className="page status-page">
      <div className="page-heading">
        <div className="eyebrow">
          <Activity size={16} /> SHAFFOF JARAYON
        </div>
        <h1>Qidiruv holati</h1>
        <p>Manbalardan loyihalar lentasigacha — tizimning joriy holati.</p>
        <button
          className="outline-button"
          onClick={() => setRefresh(refresh + 1)}
          disabled={loading}
        >
          Yangilash
        </button>
      </div>
      <div className="status-metrics">
        {[
          [
            "Oxirgi qidiruv",
            run ? date(run.started_at, true) : "Hali ishga tushmagan",
          ],
          [
            "Keyingi qidiruv",
            s.scheduler_enabled ? date(s.next_run, true) : "Jadval o‘chirilgan",
          ],
          ["Jami loyihalar", String(s.total_projects)],
          ["Tahlil kutilmoqda", String(s.pending_candidates)],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="notice">
        <Clock3 size={18} />
        <p>
          Qidiruv har soatning boshida ishlaydi. Barcha vaqtlar Toshkent vaqti
          bilan ko‘rsatilgan. Bu sahifa har 30 soniyada yangilanadi.
        </p>
      </div>
      <div className="status-grid">
        <section className="detail-section">
          <h2>
            Oxirgi ishga tushirish{" "}
            <span className="tag">
              {run ? statusLabels[run.status] : "Kutilmoqda"}
            </span>
          </h2>
          {run ? (
            <>
              <div className="run-counts">
                {Object.entries(countLabels).map(([k, label]) => (
                  <div key={k}>
                    <span>{label}</span>
                    <strong>{run.counts[k] || 0}</strong>
                  </div>
                ))}
              </div>
              <p className="section-note">
                Davomiyligi:{" "}
                {run.duration_seconds === null
                  ? "Jarayonda"
                  : `${run.duration_seconds} soniya`}
              </p>
              {run.errors.length > 0 && (
                <div className="run-errors">
                  <h3>Qidiruvdagi xatolar</h3>
                  {run.errors.map((e, i) => (
                    <p key={i}>
                      <strong>{e.source}:</strong>{" "}
                      {errorLabels[e.code] ||
                        "Manba yoki javob tekshiruvdan o‘tmadi"}{" "}
                      <code>{e.code}</code>
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p>
              Hali qidiruv bajarilmagan. Birinchi rejalashtirilgan ishga
              tushirishdan so‘ng natijalar shu yerda ko‘rinadi.
            </p>
          )}
        </section>
        <section className="detail-section">
          <h2>Ulangan xizmatlar</h2>
          <div className="service">
            <span>Ochiq RSS manbalari</span>
            <span className="tag">{s.sources.length} ta sozlangan</span>
          </div>
          <div className="service">
            <span>AI tahlili va tarjima</span>
            <span className="tag">
              {s.ai_enabled ? "Sozlangan" : "Kalit kutilmoqda"}
            </span>
          </div>
          <div className="service">
            <span>Internet qidiruvi</span>
            <span className="tag">
              {s.search_enabled ? "Sozlangan" : "Kalit kutilmoqda"}
            </span>
          </div>
          <p className="section-note">
            Kalitlarsiz faqat yetarli dalilli o‘zbekcha materiallar qayta
            ishlanadi. Boshqa tillardagi materiallar tarjima va tahlilni kutadi.
            Sozlangan xizmatning ishlashi qidiruv natijasida tekshiriladi.
          </p>
          <h3>Qidiruv manbalari</h3>
          {s.sources.map((source) => (
            <p key={source.url}>
              <External href={source.url}>{source.name}</External>
            </p>
          ))}
        </section>
      </div>
      <section className="detail-section">
        <h2>Qidiruvlar tarixi</h2>
        {s.runs.length ? (
          s.runs.map((r) => (
            <div className="run-history" key={r.id}>
              <span>{date(r.started_at, true)}</span>
              <span className="tag">{statusLabels[r.status]}</span>
              <span>{r.counts.new_projects || 0} ta yangi loyiha</span>
              <span>{r.duration_seconds ?? "—"} s</span>
            </div>
          ))
        ) : (
          <p>Tarix hali bo‘sh.</p>
        )}
      </section>
    </main>
  );
}
