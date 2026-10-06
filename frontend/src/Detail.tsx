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
        <Link to="/">← Lentaga qaytish</Link>
        <ErrorBox retry={() => setRetry(retry + 1)} />
      </main>
    );
  const c = p.content!;
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
      <Link className="back-link" to="/">
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
                olingan; taxminiy foyda va xulosalar qo‘shilmagan.
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
