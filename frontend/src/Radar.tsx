import { Link } from "react-router-dom";
import { ShieldCheck, Layers3 } from "lucide-react";
import { External } from "./components";
import { useApi } from "./useApi";
import { date } from "./utils";
import type { Project, Status, SectorStats } from "./types";

const health: Record<string, string> = {
  ACTIVE: "Ishlamoqda",
  ERROR: "Xatolik",
  NEEDS_CONFIG: "Sozlash kerak",
  UNTESTED: "Tekshirilmagan",
  DISABLED: "O‘chirilgan",
};
const methods: Record<string, string> = {
  RSS: "RSS",
  search: "Internet qidiruvi",
  direct_page: "Ochiq sahifa",
  API: "API",
  browser: "Brauzer",
  manual_config: "Qo‘lda sozlash",
};
const kinds: Record<string, string> = {
  startup_platform: "Startap platformasi",
  university: "Universitet",
  hackathon: "Hakaton",
  accelerator: "Akselerator",
  news: "OAV",
  government: "Davlat",
  company: "Kompaniya",
  event: "Tadbir",
  RSS: "RSS",
  community: "Hamjamiyat",
  other: "Boshqa",
};
const eventTypes: Record<string, string> = {
  hackathon: "Hakaton",
  competition: "Tanlov",
  demo_day: "Namoyish kuni",
  startup_pitch: "Startap taqdimoti",
  exhibition: "Ko‘rgazma",
  university_event: "Universitet tadbiri",
  accelerator_demo: "Akselerator namoyishi",
  innovation_forum: "Innovatsiya forumi",
  grant_competition: "Grant tanlovi",
  other: "Boshqa",
};
const errorLabels: Record<string, string> = {
  requires_api_key: "Qidiruv kaliti kerak",
  event_requires_search_key: "Tadbir qidiruvi uchun kalit kerak",
  source_requires_configuration: "Yig‘ish usulini sozlash kerak",
  http_403: "Kirish rad etildi (403)",
  network_unavailable: "Tarmoqqa ulanish imkoni bo‘lmadi",
  dns_failed: "Manzil aniqlanmadi",
  robots_disallowed: "Avtomatik o‘qishga ruxsat yo‘q",
  http_409: "Manba so‘rovni rad etdi (409)",
};
function region(value: string) {
  return value
    .replace("Regional Uzbekistan", "O‘zbekiston hududlari")
    .replace(
      "International source covering Uzbekistan",
      "O‘zbekistonni yorituvchi xorijiy manba",
    )
    .replace(/^Uzbekistan$/, "O‘zbekiston");
}
function frequency(minutes: number) {
  return minutes % 1440 === 0
    ? `${minutes / 1440} kunda`
    : `${minutes / 60} soatda`;
}

export function SectorOverview() {
  const { data, error } = useApi<SectorStats>("/api/sectors/stats");
  if (!data || error) return null;
  const items = data.items.filter((s) => s.count > 0);
  return (
    <section className="sector-overview" aria-label="Sektorlar statistikasi">
      <div>
        <h3>
          <Layers3 size={15} /> Oxirgi 30 kun · yo‘nalishlar
        </h3>
        <span>{data.total_projects} ta tasdiqlangan loyiha</span>
      </div>
      {items.length ? (
        <div className="sector-buttons">
          {items.slice(0, 8).map((s) => (
            <Link key={s.sector} to={`/?period=30d&category=${s.sector}`}>
              <span>{s.label}</span>
              <strong>{s.count}</strong>
              <small>Bugun: {s.today}</small>
            </Link>
          ))}
        </div>
      ) : (
        <p>
          Yetarli dalilga ega loyihalar paydo bo‘lganda statistika yangilanadi.
        </p>
      )}
      <p className="section-note">
        Bir loyiha bir nechta yo‘nalishga tegishli bo‘lishi mumkin.
      </p>
    </section>
  );
}

export function EvidencePanel({ project: p }: { project: Project }) {
  return (
    <section className="detail-section">
      <h2>
        <ShieldCheck size={20} /> Tasdiqlanganlik dalillari
      </h2>
      <p className="section-note">
        Quyidagi signallar manbalardagi iqtiboslarga asoslangan. Ishonch
        ko‘rsatkichi ehtimollikning statistik o‘lchovi emas.
      </p>
      <div className="evidence-signals">
        {p.detection_signals?.map((s) => (
          <span className="tag" key={s.type}>
            {s.label}
          </span>
        ))}
      </div>
      <p>
        Dalilga asoslangan ishonch:{" "}
        <strong>{p.real_project_confidence}%</strong>
      </p>
      {p.evidence?.map((e) => (
        <details className="evidence-record" key={e.id}>
          <summary>
            {e.label}{" "}
            <span>Manba ishonchi: {Math.round(e.confidence * 100)}%</span>
          </summary>
          <blockquote>{e.quote}</blockquote>
          <External href={e.url}>Dalil manbasi</External>
          <p className="section-note">
            Topilgan: {date(e.discovered_at, true)}
          </p>
        </details>
      ))}
    </section>
  );
}

export function ProblemPanel({ project: p }: { project: Project }) {
  const a = p.content?.problem_analysis;
  return (
    <div className="problem-panel">
      <h3>Muammo qanchalik muhim?</h3>
      <p className="section-note">
        AI tahlili. Bu baho umumiy foydalilik reytingini almashtirmaydi.
      </p>
      <dl>
        {[
          ["Kim bu muammoga duch keladi?", a?.affected_groups_uz],
          ["Muammoning jiddiyligi", a?.severity_uz],
          ["Qanchalik tez-tez yuz beradi?", a?.frequency_uz],
          ["Yechim to‘liqmi yoki qismanmi?", a?.solution_scope_uz],
        ].map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value || "Baholash uchun ma’lumot yetarli emas."}</dd>
          </div>
        ))}
      </dl>
      <p>
        Muammo jiddiyligi:{" "}
        <strong>
          {a?.problem_severity_score == null
            ? "Baholanmagan"
            : `${a.problem_severity_score} / 10`}
        </strong>
      </p>
      <h3>Nega bu loyiha hozir muhim?</h3>
      <p>{p.content?.why_now_uz || "AI xulosasi hali mavjud emas."}</p>
    </div>
  );
}

export function RadarAdmin({ status: s }: { status: Status }) {
  return (
    <div className="radar-admin">
      <section className="detail-section">
        <h2>Qayta ishlash va rad etish sabablari</h2>
        <div className="radar-metrics">
          {Object.entries({
            pending_ai: "AI yoki qo‘shimcha dalil kutilmoqda",
            queued: "Navbatdagi URL",
            processed_ai: "AI bilan ishlangan",
            processed_fallback: "Qoidalar bilan ishlangan",
            ai_errors: "AI xatolari",
            translation_errors: "Tarjima xatolari",
          }).map(([key, label]) => (
            <div key={key}>
              <span>{label}</span>
              <strong>{s.processing_summary[key] || 0}</strong>
            </div>
          ))}
        </div>
        <p className="section-note">
          Quyidagi sabablar saqlangan nomzodlar bo‘yicha; bir yozuvda bir nechta
          sabab bo‘lishi mumkin. Dublikatlar birlashtiriladi, ekotizim xabarlari
          alohida saqlanadi.
        </p>
        <div className="radar-metrics">
          {s.reject_reason_stats.map((r) => (
            <div key={r.reason}>
              <span>{r.label}</span>
              <strong>{r.count}</strong>
            </div>
          ))}
        </div>
        <h3>Nomzodlar qayerdan topildi?</h3>
        {s.origin_stats.map((o) => (
          <p key={o.origin}>
            <strong>{o.label}</strong>: {o.candidates || 0} nomzod ·{" "}
            {o.published || 0} qabul qilingan manba · {o.pending || 0}{" "}
            kutilmoqda · {o.rejected || 0} rad etilgan
          </p>
        ))}
        <p className="section-note">
          Bir loyiha bir nechta manbadan kelishi mumkin. Manbalar soni noyob
          loyihalar soniga teng emas.
        </p>
        <h3>Nashr yili bo‘yicha saqlangan loyihalar</h3>
        <div className="sector-buttons">
          {Object.entries(s.historical_counts).map(([year, count]) => (
            <Link key={year} to={`/?period=all&year=${year}`}>
              {year}: {count}
            </Link>
          ))}
        </div>
      </section>
      <section className="detail-section">
        <h2>Radar ko‘rsatkichlari</h2>
        <div className="radar-metrics">
          {[
            ["Jami manbalar", s.source_summary.total],
            ["Yoqilgan manbalar", s.source_summary.active],
            ["Xatoli manbalar", s.source_summary.failed],
            ["Ustuvorligi 5", s.source_summary.priority_5],
            ["Tadbirlar", s.event_summary.total],
            ["Bugungi yangi tadbirlar", s.event_summary.today],
            [
              "Tadbir orqali topilgan loyihalar",
              s.event_summary.projects_found,
            ],
            ["Jami nomzodlar", s.candidate_summary.total],
            ["Qabul qilingan loyihalar", s.candidate_summary.accepted],
            ["Sifat filtrida to‘xtatilgan", s.candidate_summary.stop_filtered],
            ["Birlashtirilgan dublikatlar", s.candidate_summary.duplicates],
            ["Ekotizim xabarlari", s.candidate_summary.ecosystem_signals],
            ["O‘rtacha tasdiqlanganlik", s.evidence_summary.average],
            ["Ishonchi past loyihalar", s.evidence_summary.low_confidence],
            ["Bir manbali loyihalar", s.evidence_summary.single_source],
            [
              "Bir nechta manbali loyihalar",
              s.evidence_summary.multiple_sources,
            ],
            ["Lentadan yashirilgan", s.evidence_summary.hidden_projects],
          ].map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
        <p className="section-note">
          Oxirgi manba tekshiruvi: {date(s.source_summary.last_check, true)}.
          Eng kam Tasdiqlanganlik: {s.evidence_summary.threshold} / 10. Muallif
          va mavjudlik dalili ham majburiy.
        </p>
      </section>
      <section className="detail-section">
        <h2>Manbalar reyestri va holati</h2>
        <p className="section-note">
          Har bir manba o‘z jadvali bo‘yicha tekshiriladi. Sozlangan yoki
          yoqilgan manba hali jonli ishlashi tasdiqlangan degani emas.
        </p>
        <div className="registry-list">
          {s.sources.map((source) => (
            <article className="registry-source" key={source.id}>
              <div className="registry-heading">
                <External href={source.url}>{source.name}</External>
                <span className={`tag health-${source.status.toLowerCase()}`}>
                  {health[source.status]}
                </span>
              </div>
              <p>
                {kinds[source.source_type]} · {region(source.region)} ·{" "}
                {methods[source.collection_method]}
              </p>
              <dl>
                <div>
                  <dt>Ustuvorlik</dt>
                  <dd>{source.priority}/5</dd>
                </div>
                <div>
                  <dt>Tekshirish davri</dt>
                  <dd>{frequency(source.check_frequency)}</dd>
                </div>
                <div>
                  <dt>Manba ishonchliligi</dt>
                  <dd>{source.reliability_score}/10</dd>
                </div>
                <div>
                  <dt>Oxirgi tekshiruv</dt>
                  <dd>{date(source.last_checked_at, true)}</dd>
                </div>
                <div>
                  <dt>Oxirgi muvaffaqiyat</dt>
                  <dd>{date(source.last_success_at, true)}</dd>
                </div>
                <div>
                  <dt>Keyingi tekshiruv</dt>
                  <dd>
                    {source.enabled
                      ? date(source.next_check_at, true)
                      : "O‘chirilgan"}
                  </dd>
                </div>
                <div>
                  <dt>Topilgan nomzodlar</dt>
                  <dd>{source.candidates_found}</dd>
                </div>
                <div>
                  <dt>Yangi loyihalar</dt>
                  <dd>{source.new_projects}</dd>
                </div>
                <div>
                  <dt>Ketma-ket xatolar</dt>
                  <dd>{source.consecutive_errors}</dd>
                </div>
              </dl>
              {source.last_error && (
                <p className="source-error">
                  {errorLabels[source.last_error] ||
                    "Manbani tekshirishda xatolik"}{" "}
                  <code>{source.last_error}</code>
                </p>
              )}
              <p className="section-note">{source.notes}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="detail-section">
        <h2>Topilgan tadbirlar</h2>
        {s.events.length ? (
          s.events.map((e) => (
            <article className="registry-source" key={e.id}>
              <External href={e.official_url || e.source_url}>
                {e.name}
              </External>
              <p>
                {eventTypes[e.event_type] || "Tadbir"} ·{" "}
                {e.city || "Shahar ko‘rsatilmagan"} · {e.projects_found} ta
                loyiha
              </p>
              <p className="section-note">
                Tashkilotchi: {e.organizer || "Ko‘rsatilmagan"}. Boshlanish:{" "}
                {date(e.start_date)}. Oxirgi qo‘shimcha qidiruv:{" "}
                {date(e.last_checked_at, true)}.
              </p>
              {e.last_error && (
                <p className="source-error">
                  {errorLabels[e.last_error] || "Qo‘shimcha qidiruvda xatolik"}
                </p>
              )}
            </article>
          ))
        ) : (
          <p>Hali tasdiqlangan tadbir topilmadi.</p>
        )}
      </section>
      <div className="status-grid">
        <section className="detail-section">
          <h2>Sifat filtrida to‘xtatilgan nomzodlar</h2>
          {s.rejected_candidates.length ? (
            s.rejected_candidates.map((r) => (
              <article className="review-record" key={r.url}>
                <External href={r.url}>{r.title}</External>
                <p>{r.reason_labels.join(" · ")}</p>
                <small>Tasdiqlanganlik: {r.evidence_score}/10</small>
              </article>
            ))
          ) : (
            <p>Ro‘yxat hozircha bo‘sh.</p>
          )}
        </section>
        <section className="detail-section">
          <h2>Ekotizim xabarlari</h2>
          <p className="section-note">
            Fondlar, grant dasturlari va akseleratorlar haqidagi xabarlar loyiha
            sifatida asosiy lentaga kiritilmaydi. Bu yerda manbaning original
            sarlavhasi ko‘rsatilgan.
          </p>
          {s.ecosystem_signals.length ? (
            s.ecosystem_signals.map((e) => (
              <article className="review-record" key={e.url}>
                <External href={e.url}>{e.title}</External>
                <p>{date(e.published_at)}</p>
              </article>
            ))
          ) : (
            <p>Hozircha bunday xabarlar yo‘q.</p>
          )}
        </section>
      </div>
      <section className="detail-section">
        <h2>Loyiha aniqlash sabablari</h2>
        {s.project_debug.map((p) => (
          <details className="evidence-record" key={p.id}>
            <summary>
              {p.name} · {p.visible ? "Lentada" : "Yashirilgan"} ·{" "}
              {p.confidence}/10
            </summary>
            <p>
              {p.stop_reasons.join(" · ") ||
                "Majburiy sifat tekshiruvlaridan o‘tgan."}
            </p>
            {p.signals.map((signal) => (
              <p key={signal.label}>
                {signal.label}:{" "}
                {signal.urls.map((url) => (
                  <External key={url} href={url}>
                    Manba
                  </External>
                ))}
              </p>
            ))}
          </details>
        ))}
      </section>
    </div>
  );
}
