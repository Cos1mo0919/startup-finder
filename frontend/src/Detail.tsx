import { EvidencePanel, ProblemPanel } from "./Radar";
import {
  ArrowLeft,
  BookOpen,
  Check,
  MapPin,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Project } from "./types";

import {
  ErrorBox,
  External,
  Loading,
  ProjectImage,
  Ratings,
} from "./components";
import { audienceLabels } from "./labels";
import { useApi } from "./useApi";
import { date } from "./utils";
export function Detail() {
  const { id } = useParams(),
    [retry, setRetry] = useState(0);
  const {
    data: p,
    error,
    loading,
  } = useApi<Project>("/api/projects/" + encodeURIComponent(id || ""), retry);
  const meta = useApi<{ categories: Record<string, string> }>("/api/meta");
  if (loading)
    return (
      <main className="page">
        <Loading />
      </main>
    );
  if (error || !p)
    return (
      <main className="page">
        <Link to="/loyihalar">← Lentaga qaytish</Link>
        <ErrorBox retry={() => setRetry(retry + 1)} />
      </main>
    );
  const c = p.content!;
  const opportunity = p.opportunity_details as { criteria?: Record<string, { score: number; reason: string; evidence_refs: string[] }>; groups?: Record<string, number>; evidence_level?: number; reasons?: string[] } | undefined;
  const rubric: [string, [string, string][]][] = [
    ["Muammo", [["pain_strength","Muammoning og‘irligi"],["frequency","Takrorlanish"],["mandatory_pressure","Majburiy talab"],["current_cost","Hozirgi xarajat"]]],
    ["Bozor", [["potential_customer_count","Mijozlar soni"],["willingness_to_pay","To‘lov istagi"],["expansion_potential","Kengayish imkoniyati"]]],
    ["Biznes modeli", [["recurring_revenue_potential","Takroriy tushum"],["customer_accessibility","Mijozga yetish"],["low_capital_requirement","Kam kapital talabi"],["low_legal_risk","Huquqiy xavf"]]],
    ["Amalga oshirish", [["mvp_speed","MVP tezligi"],["competition_attractiveness","Raqobat"],["implementation_feasibility","Amalga oshirish imkoniyati"],["uzbekistan_applicability","O‘zbekistonga moslik"]]],
  ];
  const labels: Record<string, string> = {
    official: "Rasmiy sayt",
    github: "GitHub",
    university: "Universitet sahifasi",
    event: "Tadbir sahifasi",
    creator: "Muallif sahifasi",
    company: "Tashkilot sahifasi",
  };
  return (
    <main className="page detail">
      <Link className="back-link" to="/loyihalar">
        <ArrowLeft size={16} /> Loyihalar lentasiga
      </Link>
      <div className="detail-heading">
        <span className="category">
          {meta.data?.categories[p.primary_sector || p.category] || "Loyiha"}
        </span>
        <h1>{p.name}</h1>
        <p>{p.summary_uz}</p>
        <div className="detail-tags">
          <span>
            <MapPin size={15} />
            {p.city || "O‘zbekiston"}
          </span>
          <span>
            <Users size={15} />
            {audienceLabels[p.audience]}
          </span>
          <span>
            <BookOpen size={15} />
            {p.source_count} ta manba
          </span>
        </div>
      </div>
      <div className="detail-grid">
        <div>
          <section className="detail-section">
            <h2>Qanday muammoni hal qiladi?</h2>
            <p>{p.problem_statement || "Muammo haqidagi aniq dalil tekshirilmoqda."}</p>
            <p className="section-note">Holat: {p.problem_gate_status === "PASS" ? "Manbaga asoslangan" : p.problem_gate_status === "REJECT" ? "Rad etilgan" : "Qo‘shimcha tahlil kutilmoqda"}. Imkoniyat: {p.opportunity_score === null ? "baholanmagan" : `${p.opportunity_score}/100 · ${p.opportunity_grade}`}.</p>
            {p.related_problems?.map(problem => <p key={problem.id}><Link to={`/muammo/${problem.id}`}>{problem.title_uz} →</Link></p>)}
          </section>
          <section className="detail-section">
            <h2>Imkoniyat bahosi</h2>
            <p className="section-note">Har bir mezon manbali izoh talab qiladi. Noma’lum qiymat taxminiy o‘rtacha ball bilan to‘ldirilmaydi.</p>
            <p>{p.opportunity_score === null ? "To‘liq baho uchun dalil yetarli emas." : `${p.opportunity_score}/100 · ${p.opportunity_grade}`}</p>
            {rubric.map(([group, fields]) => <div className="analysis-block" key={group}><h3>{group}</h3><dl className="intel-rubric">{fields.map(([key,label]) => {const item=opportunity?.criteria?.[key];return <div key={key}><dt>{label}</dt><dd>{item?`${item.score}/5 — ${item.reason}`:"Dalil yetarli emas"}</dd></div>})}</dl></div>)}
            {opportunity?.evidence_level && <p>Dalil darajasi: {opportunity.evidence_level}/5</p>}
          </section>
          <section className="detail-section">
            <div className="detail-images">
              {p.images.length ? (
                p.images.map((i) => (
                  <figure key={i.url}>
                    <img
                      src={i.url}
                      alt={`${p.name} — ${i.publisher} manbasidagi rasm`}
                      referrerPolicy="no-referrer"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                    <figcaption>
                      Rasm manbasi:{" "}
                      <External href={i.source_url}>{i.publisher}</External>
                    </figcaption>
                  </figure>
                ))
              ) : (
                <ProjectImage project={p} />
              )}
            </div>
            <dl className="identity-grid">
              {[
                ["Kim yaratgan", p.creator],
                ["Tashkilot", p.organization],
                ["Universitet", c.university],
                ["Qayerda taqdim etilgan", p.event],
                ["Shahar", p.city],
                ["Davlat", "O‘zbekiston"],
                ["Nashr sanasi", date(p.published_at)],
                ["Topilgan sana", date(p.first_seen, true)],
                ["Oxirgi dalil qo‘shilgan", date(p.last_seen, true)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value || "Manbada ko‘rsatilmagan"}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="detail-section">
            <h2>
              <ShieldCheck size={21} /> Tasdiqlangan faktlar
            </h2>
            <p className="section-note">
              Manbalarda keltirilgan va iqtibos bilan bog‘langan ma’lumotlar. Bu
              mustaqil audit o‘rnini bosmaydi.
            </p>
            {c.facts.map((f, i) => (
              <div className="fact" key={i}>
                <Check size={17} />
                <div>
                  <p>{f.text_uz}</p>
                  <External href={f.source_url}>Manbani o‘qish</External>
                  <details>
                    <summary>Original iqtibos</summary>
                    <blockquote>{f.quote}</blockquote>
                  </details>
                </div>
              </div>
            ))}
          </section>
          <EvidencePanel project={p} />
          <section className="detail-section ai-section">
            <div className="section-heading">
              <h2>
                <Sparkles size={21} /> AI tahlili
              </h2>
              <span className="tag">Faktlardan alohida</span>
            </div>
            {p.analysis_mode === "extractive" ? (
              <p>
                AI tahlili hali bajarilmagan. Quyidagi qisqa tavsif manbadan
                olingan; taxminiy foyda va xulosalar qo‘shilmagan. Foydalilik
                reytingi qoidalar asosida hisoblangan; ekspert AI bahosi emas.
              </p>
            ) : (
              <>
                <p className="section-note">
                  Quyidagilar modelning izohi va ehtimoliy foyda haqidagi
                  xulosalaridir. Xatolik bo‘lishi mumkin.
                </p>
                <p>{c.ai_analysis_uz || "Qo‘shimcha tahlil mavjud emas."}</p>
              </>
            )}
            <ProblemPanel project={p} />
            {[
              ["Bu nima", c.what_uz],
              ["Qanday ishlaydi", c.how_uz],
              ["Qanday muammoni hal qiladi", c.problem_uz],
              ["Jismoniy shaxslar uchun foydasi", c.individual_benefit_uz],
              ["Yuridik shaxslar uchun foydasi", c.business_benefit_uz],
              [
                "Asosiy auditoriya",
                p.audience_groups.join(", ") || audienceLabels[p.audience],
              ],
            ].map(([label, value]) => (
              <div className="analysis-block" key={label}>
                <h3>{label}</h3>
                <p>
                  {value || "Xulosa chiqarish uchun ma’lumot yetarli emas."}
                </p>
              </div>
            ))}
            {[
              ["Afzalliklari", c.advantages_uz],
              ["Cheklovlari", c.limitations_uz],
            ].map(([label, values]) => (
              <div className="analysis-block" key={String(label)}>
                <h3>{label}</h3>
                {(values as string[]).length ? (
                  <ul>
                    {(values as string[]).map((v, i) => (
                      <li key={i}>{v}</li>
                    ))}
                  </ul>
                ) : (
                  <p>Ma’lumot yetarli emas.</p>
                )}
              </div>
            ))}
          </section>
          <section className="detail-section">
            <h2>Manbalar va havolalar</h2>
            {p.sources?.map((s, i) => (
              <div className="source-row" key={s.url}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <External href={s.url}>{s.publisher}</External>
                  <p>{date(s.published_at)} · Original maqola</p>
                  <External href={s.url} className="source-url">
                    {s.url}
                  </External>
                </div>
              </div>
            ))}
            {Object.entries(c.links).map(([k, v]) => (
              <p key={k}>
                <External href={v}>{labels[k] || "Qo‘shimcha havola"}</External>
              </p>
            ))}
          </section>
        </div>
        <aside>
          <Ratings
            title="Foydalilik reytingi"
            total={p.rating}
            components={p.rating_components || {}}
          />
          <Ratings
            title="Ishonchlilik reytingi"
            total={p.confidence}
            components={p.confidence_components || {}}
          />
          <p className="rating-disclaimer">
            Dalil yetishmagan mezonlar 0 ball oladi. Past ball loyiha
            sifatsizligini anglatmaydi. Turli nashrlar bir xabarni takrorlagan
            bo‘lishi mumkin.
          </p>
        </aside>
      </div>
    </main>
  );
}
