import { Link, useParams, useSearchParams } from "react-router-dom";
import { External, Loading } from "./components";
import { useApi } from "./useApi";
import { date } from "./utils";
import type { Project, RegistrySource } from "./types";

type Problem = { id: string; title_uz: string; description_uz: string; scope: string; sector: string; affected_users: string; evidence_level: number; source_count: number; first_seen_at: string; first_evidence_published_at: string | null; evidence?: {source_url: string; quote: string; evidence_type: string}[]; projects?: {id: string; name: string}[]; ideas?: Idea[] };
type Idea = { id: string; problem_id: string; idea_title: string; idea_summary: string; target_user: string; proposed_solution: string; current_alternatives: string; why_current_alternatives_fail: string; business_model_hypothesis: string; mvp_hypothesis: string; main_risks: string; evidence_basis: string[]; status: string };
type Signal = {url: string; title: string; summary_uz: string; signal_type: string; country: string; sector: string; published_at: string; why_it_matters_uz: string};
type ProjectPreview = {id:string;name:string;problem:string;affected_users:string;problem_gate_status:string;opportunity_score:number|null;opportunity_grade:string;problem_score:number|null;market_score:number|null;evidence_score:number;country:string;sector:string;published_at:string;source_count:number};
type Dashboard = {today: Record<string,number>; total: Record<string,number>; strong_opportunities: {id:string;name:string;score:number;grade:string;problem:string}[]; latest_projects: ProjectPreview[]; latest_problems: Problem[]; latest_ideas: Idea[]; latest_signals: Signal[]};
const scopeLabels: Record<string,string> = {EVERYDAY:"Kundalik muammo", UZBEKISTAN_LOCAL:"O‘zbekiston muammosi", GLOBAL:"Jahon tendensiyasi"};
const signalLabels: Record<string,string> = {ecosystem:"Ekotizim", TECHNOLOGY:"Texnologiya", REGULATION:"Qonunchilik", PROGRAM:"Dastur", INVESTMENT:"Investitsiya", FUND:"Jamg‘arma", DEMAND:"Talab"};
function Empty({children}:{children:string}) { return <p className="intel-empty">{children}</p> }
function ProblemCard({p}:{p:Problem}) {return <article className="intel-card"><span className="tag">{scopeLabels[p.scope] || p.scope}</span><h3><Link to={`/muammo/${p.id}`}>{p.title_uz}</Link></h3><p>Kimda: {p.affected_users || "Aniqlanmagan"}</p><small>{p.source_count || 1} ta manba · {date(p.first_evidence_published_at || p.first_seen_at)}</small></article>}
function SignalCard({s}:{s:Signal}) {return <article className="intel-card"><span className="tag">{signalLabels[s.signal_type]||s.signal_type}</span><h3>{s.title}</h3><p>{s.summary_uz}</p><small>{s.country} · {date(s.published_at)}</small><div><External href={s.url}>Asl manba</External></div></article>}
function ProjectPreviewCard({p}:{p:ProjectPreview}) {
  const metrics:[string,number|null][] = [["Muammo",p.problem_score],["Bozor",p.market_score],["Dalil",p.evidence_score],["Yechim",null]];
  return <article className="intel-project-card">
    <div className="intel-project-top"><h3><Link to={"/loyiha/" + p.id}>{p.name}</Link></h3><span>{p.sector === "other" ? "Loyiha" : p.sector}</span></div>
    <div className="intel-project-problem"><strong>Qanday muammoni hal qiladi?</strong><p>{p.problem || "Muammo dalili tekshirilmoqda."}</p></div>
    <p className="intel-project-audience">Kim uchun <strong>{p.affected_users || "Aniqlanmagan"}</strong></p>
    <div className="intel-project-opportunity"><span>Imkoniyat</span><strong>{p.opportunity_score === null ? "Dalil kutilmoqda" : p.opportunity_score + "/100 · " + p.opportunity_grade}</strong></div>
    <dl className="intel-project-scores">{metrics.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value === null ? "—" : value.toFixed(1)}</dd></div>)}</dl>
    <small>{date(p.published_at)} · {p.country} · {p.source_count} ta manba</small>
  </article>;
}
export function DashboardPage() {
  const {data,loading}=useApi<Dashboard>("/api/intelligence/dashboard");
  if(loading)return <main className="page"><Loading/></main>;
  return <main className="page intel-page intel-dashboard">
    <section className="intel-overview">
      <div className="intel-overview-copy"><h1>Izlanish</h1><p>Haqiqiy muammolar, tekshirilgan loyihalar, yechim g‘oyalari va bozor signallari — har biri o‘z manbasi bilan.</p></div>
      <div className="intel-metrics">{[
        ["Loyihalar",data?.total.projects],
        ["Muammolar",data?.total.problems],
        ["Yechim g‘oyalari",data?.total.ideas],
        ["Signallar",data?.total.signals],
        ["Bugun tekshirilgan manbalar",data?.today.sources_checked],
      ].map(([label,value])=><div key={String(label)}><strong>{value ?? 0}</strong><span>{label}</span></div>)}</div>
    </section>
    <section className="intel-opportunities">
      <div className="intel-heading"><h2>Eng kuchli imkoniyatlar</h2><Link to="/loyihalar?period=all">Loyihalarni ko‘rish →</Link></div>
      {data?.strong_opportunities.length?<div className="intel-grid">{data.strong_opportunities.slice(0,4).map(o=><article className="intel-card" key={o.id}><span className="tag">{o.grade} · {o.score}/100</span><h3><Link to={"/loyiha/" + o.id}>{o.name}</Link></h3><p>{o.problem}</p></article>)}</div>:<div className="intel-quiet-state"><strong>Hozircha A/B darajali imkoniyat tasdiqlanmadi.</strong><span>Radar yangi dalillarni kuzatishda davom etmoqda.</span></div>}
    </section>
    <div className="intel-dashboard-grid">
      <section className="intel-section intel-projects">
        <div className="intel-heading"><h2>Yangi loyihalar</h2><Link to="/loyihalar?period=all">Barchasi →</Link></div>
        {data?.latest_projects.length?<div className="intel-project-grid">{data.latest_projects.slice(0,3).map(p=><ProjectPreviewCard p={p} key={p.id}/>)}</div>:<div className="intel-quiet-state"><strong>Bugun yangi tasdiqlangan loyiha topilmadi.</strong><span>Radar ishlashda davom etmoqda.</span></div>}
      </section>
      <section className="intel-section intel-problems">
        <div className="intel-heading"><h2>Muammolar</h2><Link to="/muammolar">Barchasi →</Link></div>
        {data?.latest_problems.length?<div className="intel-list">{data.latest_problems.map(p=><ProblemCard p={p} key={p.id}/>)}</div>:<div className="intel-quiet-state"><strong>Yangi muammo tasdiqlanmadi.</strong><span>Manbalar kuzatilmoqda.</span></div>}
      </section>
      <section className="intel-section intel-ideas">
        <div className="intel-heading"><h2>Yechim g‘oyalari</h2><Link to="/goyalar">Barchasi →</Link></div>
        {data?.latest_ideas.length?<div className="intel-list">{data.latest_ideas.map(i=><article className="intel-card" key={i.id}><span className="tag">GIPOTEZA</span><h3><Link to={"/goya/" + i.id}>{i.idea_title}</Link></h3><p>{i.idea_summary}</p></article>)}</div>:<div className="intel-quiet-state"><strong>Dalilga asoslangan yangi g‘oya yo‘q.</strong><span>Yechim gipotezalari tasdiqlangan muammolardan kelib chiqadi.</span></div>}
      </section>
      <section className="intel-section intel-signals">
        <div className="intel-heading"><h2>Muhim signallar</h2><Link to="/signallar">Barchasi →</Link></div>
        {data?.latest_signals.length?<div className="intel-list">{data.latest_signals.map(s=><SignalCard s={s} key={s.url}/>)}</div>:<div className="intel-quiet-state"><strong>Yangi signal qayd etilmadi.</strong><span>Manbalar kuzatilmoqda.</span></div>}
      </section>
    </div>
  </main>;
}

export function ProblemsPage(){
  const [params,setParams]=useSearchParams();
  const scope=params.get("scope")||"";
  const year=params.get("year")||"";
  const page=Math.max(1,Number(params.get("page")||1));
  const query=new URLSearchParams();
  if(scope)query.set("scope",scope);
  if(year)query.set("year",year);
  query.set("page",String(page));
  const {data,loading}=useApi<{items:Problem[];total:number}>("/api/problems?"+query.toString());
  const update=(key:string,value:string)=>{const next=new URLSearchParams(params);if(value)next.set(key,value);else next.delete(key);if(key!=="page")next.delete("page");setParams(next)};
  return <main className="page intel-page"><h1>Muammolar</h1><p>Manbada qayd etilgan ehtiyoj va qiyinchiliklar. Taxminlar fakt sifatida ko‘rsatilmaydi.</p>
    <div className="intel-tabs">{[["","Barchasi"],["EVERYDAY","Kundalik"],["UZBEKISTAN_LOCAL","O‘zbekiston"],["GLOBAL","Jahon"]].map(([k,v])=><button className={scope===k?"selected":""} key={k} onClick={()=>update("scope",k)}>{v}</button>)}</div>
    <label>Nashr yili <select value={year} onChange={e=>update("year",e.target.value)}><option value="">Barcha yillar</option>{Array.from({length:new Date().getFullYear()-2021},(_,i)=>2022+i).reverse().map(y=><option key={y} value={y}>{y}</option>)}</select></label>
    {loading?<Loading/>:data?.items.length?<div className="intel-grid">{data.items.map(p=><ProblemCard p={p} key={p.id}/>)}</div>:<Empty>Bu tanlov uchun tasdiqlangan muammo yo‘q.</Empty>}
    {data&&data.total>12&&<div className="intel-tabs"><button disabled={page===1} onClick={()=>update("page",String(page-1))}>← Oldingi</button><span>{page}-sahifa</span><button disabled={page*12>=data.total} onClick={()=>update("page",String(page+1))}>Keyingi →</button></div>}
  </main>
}
export function ProblemDetailPage(){const {id}=useParams();const {data:p,loading}=useApi<Problem>(`/api/problems/${encodeURIComponent(id||"")}`);if(loading)return <main className="page"><Loading/></main>;if(!p)return <main className="page"><Empty>Muammo topilmadi.</Empty></main>;return <main className="page intel-page"><Link to="/muammolar">← Muammolar</Link><span className="tag">{scopeLabels[p.scope]||p.scope}</span><h1>{p.title_uz}</h1><p>{p.description_uz}</p><dl className="intel-facts"><div><dt>Kimda bu muammo bor?</dt><dd>{p.affected_users||"Aniqlanmagan"}</dd></div><div><dt>Dalil darajasi</dt><dd>{p.evidence_level}/5</dd></div><div><dt>Yo‘nalish</dt><dd>{p.sector}</dd></div></dl><h2>Manbalar va dalillar</h2>{p.evidence?.map((e,i)=><blockquote className="intel-quote" key={i}>{e.quote}<div><External href={e.source_url}>Asl manba</External></div></blockquote>)}<h2>Mavjud yechimlar</h2>{p.projects?.length?p.projects.map(x=><p key={x.id}><Link to={`/loyiha/${x.id}`}>{x.name} →</Link></p>):<Empty>Hozircha bog‘langan tasdiqlangan loyiha yo‘q.</Empty>}<h2>Yechim g‘oyalari</h2>{p.ideas?.length?p.ideas.map(x=><p key={x.id}><Link to={`/goya/${x.id}`}>{x.idea_title} →</Link></p>):<Empty>Dalil yetarli bo‘lmagani uchun g‘oya yaratilmagan.</Empty>}</main>}
export function IdeasPage(){const {data,loading}=useApi<Idea[]>("/api/ideas");return <main className="page intel-page"><h1>Yechim g‘oyalari</h1><p>Bu sahifadagi g‘oyalar mavjud startap emas, tekshirilishi kerak bo‘lgan gipotezalardir.</p>{loading?<Loading/>:data?.length?<div className="intel-grid">{data.map(i=><article className="intel-card" key={i.id}><span className="tag">GIPOTEZA</span><h3><Link to={`/goya/${i.id}`}>{i.idea_title}</Link></h3><p>{i.idea_summary}</p></article>)}</div>:<Empty>Hozircha dalilga asoslangan yechim g‘oyasi yaratilmagan.</Empty>}</main>}
export function IdeaDetailPage(){const {id}=useParams();const {data:i,loading}=useApi<Idea>(`/api/ideas/${encodeURIComponent(id||"")}`);if(loading)return <main className="page"><Loading/></main>;if(!i)return <main className="page"><Empty>G‘oya topilmadi.</Empty></main>;return <main className="page intel-page"><span className="tag">TIZIM GIPOTEZASI · MAVJUD MAHSULOT EMAS</span><h1>{i.idea_title}</h1><p>{i.idea_summary}</p><p><Link to={`/muammo/${i.problem_id}`}>Asosiy muammo →</Link></p>{[["Kim uchun",i.target_user],["Taklif etilgan yechim",i.proposed_solution],["Hozirgi muqobillar",i.current_alternatives],["Muqobillarning kamchiligi",i.why_current_alternatives_fail],["Biznes modeli gipotezasi",i.business_model_hypothesis],["MVP gipotezasi",i.mvp_hypothesis],["Xatarlar",i.main_risks]].map(([label,value])=><section className="intel-section" key={label}><h2>{label}</h2><p>{value||"Hozircha dalil yetarli emas."}</p></section>)}</main>}
export function SignalsPage(){const {data,loading}=useApi<Signal[]>("/api/signals");return <main className="page intel-page"><h1>Signallar</h1><p>Bozor va ekotizim xabarlari. Signal avtomatik ravishda loyiha yoki tasdiqlangan talab degani emas.</p>{loading?<Loading/>:data?.length?<div className="intel-grid">{data.map(s=><SignalCard s={s} key={s.url}/>)}</div>:<Empty>Hozircha signal yo‘q.</Empty>}</main>}
export function SectorsPage(){const {data,loading}=useApi<{sector:string;label:string;projects:number;problems:number;signals:number;average_opportunity:number|null;sample_size:number}[]>("/api/sectors/intelligence");return <main className="page intel-page"><h1>Sektorlar</h1><p>Faqat bazada mavjud tasdiqlangan yozuvlar sanaladi. Kichik tanlama bo‘yicha kuchli bozor xulosasi chiqarilmaydi.</p>{loading?<Loading/>:data?.length?<div className="intel-grid">{data.map(s=><article className="intel-card" key={s.sector}><h3>{s.label}</h3><p>{s.projects} loyiha · {s.problems} muammo · {s.signals} signal</p><small>O‘rtacha imkoniyat: {s.average_opportunity===null?"Baholanmagan":`${s.average_opportunity}/100 (${s.sample_size} ta baho)`}</small></article>)}</div>:<Empty>Hozircha sektor ma’lumotlari yo‘q.</Empty>}</main>}
export function SourcesPage(){const {data,loading}=useApi<RegistrySource[]>("/api/sources");return <main className="page intel-page"><h1>Manbalar</h1><p>Integratsiya yoqilgan manbalar va tekshiruvni kutayotgan konseptlar alohida ko‘rsatiladi.</p>{loading?<Loading/>:<div className="intel-grid">{data?.map(s=><article className="intel-card" key={s.id}><span className="tag">{s.enabled?s.status:"O‘CHIRILGAN"}</span><h3>{s.name}</h3><p>{s.region} · ustuvorlik {s.priority}/5</p><small>Topilgan materiallar: {s.candidates_found} · xatolar: {s.consecutive_errors} · HTTP: {s.last_http_status ?? "—"}</small><p>Oxirgi muvaffaqiyat: {date(s.last_success_at, true)}</p><div><External href={s.url}>Manba</External></div>{s.last_error&&<small>Xato: {s.last_error}</small>}</article>)}</div>}</main>}

export function ArchivePage(){
  const [params,setParams]=useSearchParams();
  const kind=params.get("type")||"PROJECT";
  const period=params.get("period")||"all";
  const year=params.get("year")||"";
  const sector=params.get("sector")||"";
  const grade=params.get("grade")||"";
  const scope=params.get("scope")||"";
  const country=params.get("country")||"";
  const minEvidence=params.get("evidence")||"";
  const query=new URLSearchParams();
  query.set("period",period);
  if(year)query.set("year",year);
  if(sector)query.set(kind==="PROJECT"?"category":"sector",sector);
  if(country)query.set("country",country);
  if(kind==="PROJECT"){
    query.set("page_size","50");
    if(grade)query.set("grade",grade);
    if(scope)query.set("problem_scope",scope);
    if(minEvidence)query.set("min_evidence",minEvidence);
  } else if(kind==="PROBLEM"){
    if(scope)query.set("scope",scope);
    if(minEvidence)query.set("min_evidence_level",minEvidence);
  }
  const endpoint=kind==="PROJECT"?"/api/projects":kind==="PROBLEM"?"/api/problems":kind==="SIGNAL"?"/api/signals":"/api/ideas";
  const {data,loading}=useApi<{items:Project[];total:number}|{items:Problem[];total:number}|Signal[]|Idea[]>(endpoint+"?"+query.toString());
  const update=(key:string,value:string)=>{const next=new URLSearchParams(params);if(value)next.set(key,value);else next.delete(key);if(key==="period"&&value!=="all")next.delete("year");if(key==="year"&&value)next.set("period","all");setParams(next)};
  const projectItems=kind==="PROJECT"&&!Array.isArray(data)?(data as {items:Project[]}|null)?.items:[];
  const problemItems=kind==="PROBLEM"&&!Array.isArray(data)?(data as {items:Problem[]}|null)?.items:[];
  const signalItems=kind==="SIGNAL"&&Array.isArray(data)?data as Signal[]:[];
  const ideaItems=kind==="SOLUTION_IDEA"&&Array.isArray(data)?data as Idea[]:[];
  const hasItems=!!(projectItems?.length||problemItems?.length||signalItems.length||ideaItems.length);
  return <main className="page intel-page"><h1>Arxiv</h1><p>Yangi kun eski yozuvlarni o‘chirmaydi. Nashr yili va dalil turi bo‘yicha ko‘ring.</p>
    <div className="intel-tabs">{[["PROJECT","Loyihalar"],["PROBLEM","Muammolar"],["SOLUTION_IDEA","G‘oyalar"],["SIGNAL","Signallar"]].map(([value,label])=><button key={value} className={kind===value?"selected":""} onClick={()=>update("type",value)}>{label}</button>)}</div>
    <div className="intel-tabs" aria-label="Arxiv davri">{[["today","Bugun"],["7d","Oxirgi 7 kun"],["30d","Oxirgi 30 kun"],["all","Barcha vaqt"]].map(([value,label])=><button key={value} className={period===value?"selected":""} onClick={()=>update("period",value)}>{label}</button>)}</div>
    <div className="intel-archive-filters">
      <label>Yil <select value={year} onChange={e=>update("year",e.target.value)}><option value="">Barchasi</option>{Array.from({length:new Date().getFullYear()-2021},(_,i)=>2022+i).reverse().map(y=><option value={y} key={y}>{y}</option>)}</select></label>
      {(kind==="PROJECT"||kind==="PROBLEM")&&<label>Muammo ko‘lami <select value={scope} onChange={e=>update("scope",e.target.value)}><option value="">Barchasi</option><option value="EVERYDAY">Kundalik</option><option value="UZBEKISTAN_LOCAL">O‘zbekiston</option><option value="GLOBAL">Jahon</option></select></label>}
      {kind==="PROJECT"&&<label>Imkoniyat <select value={grade} onChange={e=>update("grade",e.target.value)}><option value="">Barchasi</option>{["A","B","C","D","PENDING"].map(g=><option key={g} value={g}>{g}</option>)}</select></label>}
      {(kind==="PROJECT"||kind==="PROBLEM")&&<label>Dalil <select value={minEvidence} onChange={e=>update("evidence",e.target.value)}><option value="">Barchasi</option>{(kind==="PROJECT"?[3,5,7,9]:[2,3,4,5]).map(v=><option value={v} key={v}>{v}+</option>)}</select></label>}
      {kind!=="SOLUTION_IDEA"&&<label>Davlat <input value={country} onChange={e=>update("country",e.target.value)} placeholder="Davlat nomi" /></label>}
      {kind!=="SOLUTION_IDEA"&&<label>Sektor <input value={sector} onChange={e=>update("sector",e.target.value)} placeholder="Masalan, healthtech" /></label>}
    </div>
    {loading?<Loading/>:hasItems?<div className="intel-grid">
      {projectItems?.map(p=><article className="intel-card" key={p.id}><span className="tag">{p.opportunity_grade}</span><h3><Link to={`/loyiha/${p.id}`}>{p.name}</Link></h3><p>{p.problem_statement||"Muammo dalili kutilmoqda."}</p><small>{date(p.published_at)} · {p.country} · {p.source_count} ta manba</small></article>)}
      {problemItems?.map(p=><ProblemCard p={p} key={p.id}/>)}
      {signalItems.map(s=><SignalCard s={s} key={s.url}/>)}
      {ideaItems.map(i=><article className="intel-card" key={i.id}><span className="tag">GIPOTEZA</span><h3><Link to={`/goya/${i.id}`}>{i.idea_title}</Link></h3><p>{i.idea_summary}</p></article>)}
    </div>:<Empty>Bu filtrlar uchun tasdiqlangan yozuv yo‘q.</Empty>}
  </main>
}
