import { RadarAdmin } from "./Radar";
import { Activity, Clock3 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Status } from "./types";

import { ErrorBox, External, Loading } from "./components";
import { countLabels, errorLabels, statusLabels } from "./labels";
import { useApi } from "./useApi";
import { date } from "./utils";
const stopReasonLabels: Record<string,string> = {
  daily_publish_limit_reached: "Kunlik 100 ta nashr chegarasiga yetildi",
  local_reservation_active: "O‘zbekiston loyihalari uchun joy saqlanmoqda",
  queue_empty: "Ishlanadigan navbat tugadi",
  ai_provider_limit: "AI xizmatlari hozircha mavjud emas yoki limitga yetdi",
  source_error: "Manba xatosi",
  batch_budget_reached: "Bir ishga tushirish limiti tugadi",
  processing_disabled: "Ushbu ishga tushirishda qayta ishlash o‘chirilgan",
};
export function StatusPage({adminKey}:{adminKey:string}) {
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setRefresh((v) => v + 1), 30000);
    return () => clearInterval(id);
  }, []);
  const { data: s, error, loading } = useApi<Status>("/api/admin/status", refresh, adminKey);
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
        <p>Manbalardan muammo, loyiha va signallargacha — tizimning joriy holati.</p>
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
          ["Keyingi kunlik ishlov", s.scheduler_enabled ? date(s.next_daily_processing||null, true) : "Jadval o‘chirilgan"],
          ["Jami loyihalar", String(s.total_projects)],
          ["Bugun nashr etildi", `${s.daily_publication?.published??0}/${s.daily_publication?.limit??100}`],
          ["7 kunda", String(s.daily_publication?.week??0)],
          ["Oy davomida", String(s.daily_publication?.month??0)],
          ["Tahlil kutilmoqda", String(s.pending_candidates)],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="notice"><p>Bo‘limlar: O‘zbekiston {s.public_sections?.Uzbekistan??0} · Global {s.public_sections?.Global??0} · GitHub {s.public_sections?.GitHub??0} · Boshqa {s.public_sections?.Boshqa??0}. Oxirgi to‘xtash sababi: {stopReasonLabels[s.last_stop_reason||""]||"Hali aniqlanmagan"}.</p></div>
      <p className="status-database-id">Baza ID: {s.database_instance_id||"—"} · {s.database_driver||"—"}</p>
      <div className="notice">
        <Clock3 size={18} />
        <p>
          {s.scheduler_enabled
            ? "Loyiha qidiruvi har soatda, moslashtirish esa 08:00 va 23:30 da tekshiriladi. Mahalliy muammolar haftalik, jahon tendensiyalari oylik ko‘riladi; manbalar o‘z davriga ega."
            : "Avtomatik qidiruv jadvali hozir o‘chirilgan. Qo‘lda ishga tushirilgan qidiruv natijalari shu yerda ko‘rinadi."} Barcha vaqtlar Toshkent vaqti bilan ko‘rsatilgan. Bu sahifa har
          30 soniyada yangilanadi.
        </p>
      </div>
      <div className="status-grid">
        <section className="detail-section">
          <h2>
            Oxirgi ishga tushirish{" "}
            <span className={`tag status-${run?.status || "waiting"}`}>
              {run ? statusLabels[run.status] : "Kutilmoqda"}
            </span>
          </h2>
          {run ? (
            <>
              {run.details?.summary && (
                <div className="notice">
                  <p>
                    {run.details.mode === "archive"
                      ? "Arxiv qidiruvi"
                      : "Yangi nashrlar qidiruvi"}
                    :{" "}
                    {run.details.window
                      ?.map((value) => date(value))
                      .join(" — ")}
                    . Manba xatolari: {run.details.summary.source_errors};
                    sahifa xatolari: {run.details.summary.parser_errors}; tadbir
                    qidiruvi xatolari: {run.details.summary.event_errors};
                    sozlash kerak: {run.details.summary.configuration_errors};
                    kutilayotgan nomzodlar: {run.details.summary.pending}.
                    {run.details.summary.ai_unavailable &&
                      " AI kaliti yo‘q; qoidalar asosidagi tahlil ishlaydi."}
                  </p>
                </div>
              )}
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
            <span>Manbalar reyestri</span>
            <span className="tag">{s.sources.length} ta sozlangan</span>
          </div>
          <div className="service">
            <span>AI tahlili va tarjima</span>
            <span className={`tag ${s.ai_enabled ? "" : "health-needs_config"}`}>
              {s.ai_enabled ? "Sozlangan" : "Kalit kutilmoqda"}
            </span>
          </div>
          <div className="service">
            <span>Internet qidiruvi</span>
            <span className={`tag ${s.search_enabled ? "" : "health-needs_config"}`}>
              {s.search_enabled ? "Sozlangan" : "Kalit kutilmoqda"}
            </span>
          </div>
          <p className="section-note">
            Kalitlarsiz aniq nom va muallifga ega materiallar qoidalar asosida
            ajratiladi. Boshqa tillardagi dalillar asl iqtibos va qisqa
            o‘zbekcha izoh bilan saqlanadi; to‘liq tarjima AI talab qiladi.
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
      <RadarAdmin status={s} />
      <section className="detail-section">
        <h2>Muammo va signal jarayoni</h2>
        <div className="run-counts">
          {Object.entries(s.intelligence_counts || {}).map(([key, value]) => <div key={key}><span>{{projects:"Loyihalar",problems:"Muammolar",ideas:"G‘oyalar",signals:"Signallar",candidates:"Nomzodlar",sources:"Manbalar"}[key] || key}</span><strong>{value}</strong></div>)}
        </div>
        <p>Muammo darvozasi: {Object.entries(s.problem_gate_counts || {}).map(([key,value]) => `${key}: ${value}`).join(" · ") || "Hali ma’lumot yo‘q"}</p>
        <h3>Imkoniyat baholari</h3>
        <div className="run-counts">
          <div><span>To‘liq baholangan</span><strong>{s.scoring_summary?.scored ?? 0}</strong></div>
          <div><span>Dalil kutilmoqda</span><strong>{s.scoring_summary?.pending ?? 0}</strong></div>
          <div><span>Stop-filtr rad etgan</span><strong>{s.scoring_summary?.rejected_by_stop_filter ?? 0}</strong></div>
          <div><span>O‘rtacha imkoniyat</span><strong>{s.scoring_summary?.average_opportunity === null || s.scoring_summary?.average_opportunity === undefined ? "Baholanmagan" : s.scoring_summary.average_opportunity + "/100"}</strong></div>
        </div>
        <p>Muammo dalil darajalari: {Object.entries(s.scoring_summary?.problem_evidence_levels || {}).map(([level,count]) => level + "/5: " + count).join(" · ") || "Hali ma’lumot yo‘q"}</p>
        <p>Baholash usuli: qoidalar — {s.scoring_summary?.rating_methods.extractive ?? 0}, AI — {s.scoring_summary?.rating_methods.ai ?? 0}.</p>
        <h3>Tekshiruv nuqtalari</h3>
        <p>Oxirgi muvaffaqiyatli qidiruv: {date(s.last_successful_scan_at, true)} · manba tekshiruvi: {date(s.last_successful_source_check_at, true)} · material ishlovi: {date(s.last_processed_item_at, true)}</p>
        {s.scan_checkpoints?.length ? s.scan_checkpoints.map(c => <p key={c.name}>{c.name}: oxirgi urinish {date(c.last_attempt_at, true)}, muvaffaqiyat {date(c.last_success_at, true)}</p>) : <p>Chuqur tekshiruv hali boshlanmagan.</p>}
      </section>
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
