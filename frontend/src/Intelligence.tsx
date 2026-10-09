import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Card, External, Loading } from "./components";
import { useApi } from "./useApi";
import { date } from "./utils";
import type { Project } from "./types";

type Problem = { id: string; title_uz: string; description_uz: string; scope: string; sector: string; affected_users: string; evidence_level: number; source_count: number; first_seen_at: string; first_evidence_published_at: string | null; evidence?: {source_url: string; quote: string; evidence_type: string}[]; projects?: {id: string; name: string}[]; ideas?: Idea[] };
type Idea = { id: string; problem_id: string; idea_title: string; idea_summary: string; target_user: string; proposed_solution: string; current_alternatives: string; why_current_alternatives_fail: string; business_model_hypothesis: string; mvp_hypothesis: string; main_risks: string; evidence_basis: string[]; status: string };
type Signal = {url: string; title: string; summary_uz: string; signal_type: string; country: string; sector: string; published_at: string; why_it_matters_uz: string};
type ProjectPreview = {id:string;name:string;problem:string;solution:string;affected_users:string;evidence_score:number;country:string;sector:string;published_at:string;source_count:number};
type Dashboard = {today: {projects:number;sources_checked:number}; total: {projects:number}; latest_projects: ProjectPreview[]};
const scopeLabels: Record<string,string> = {EVERYDAY:"Kundalik muammo", UZBEKISTAN_LOCAL:"O‘zbekiston muammosi", GLOBAL:"Jahon tendensiyasi"};
const signalLabels: Record<string,string> = {ecosystem:"Ekotizim", TECHNOLOGY:"Texnologiya", REGULATION:"Qonunchilik", PROGRAM:"Dastur", INVESTMENT:"Investitsiya", FUND:"Jamg‘arma", DEMAND:"Talab"};
function Empty({children}:{children:string}) { return <p className="intel-empty">{children}</p> }
function ProblemCard({p}:{p:Problem}) {return <article className="intel-card"><span className="tag">{scopeLabels[p.scope] || p.scope}</span><h3><Link to={`/admin/muammo/${p.id}`}>{p.title_uz}</Link></h3><p>Kimda: {p.affected_users || "Aniqlanmagan"}</p><small>{p.source_count || 1} ta manba · {date(p.first_evidence_published_at || p.first_seen_at)}</small></article>}
function SignalCard({s}:{s:Signal}) {return <article className="intel-card"><span className="tag">{signalLabels[s.signal_type]||s.signal_type}</span><h3>{s.title}</h3><p>{s.summary_uz}</p><small>{s.country} · {date(s.published_at)}</small><div><External href={s.url}>Asl manba</External></div></article>}
function ProjectPreviewCard({p}:{p:ProjectPreview}) {
  return <article className="intel-project-card">
    <div className="intel-project-top"><h3><Link to={"/loyiha/" + p.id}>{p.name}</Link></h3><span>{p.country === "Uzbekistan" ? "O‘zbekiston" : "Global"}</span></div>
    <div className="intel-project-problem"><strong>Qanday muammoni hal qiladi?</strong><p>{p.problem}</p></div>
    <p className="intel-project-audience">Kim uchun? <strong>{p.affected_users}</strong></p>
    <p><strong>Yechim</strong> {p.solution}</p>
    <p className="card-evidence">Dalil: {p.source_count} ta manba · Tasdiqlanganlik {p.evidence_score.toFixed(1)}/10</p>
    <small>{date(p.published_at)} · {p.country} · {p.source_count} ta manba</small>
  </article>;
}
export function DashboardPage() {
  const {data,loading}=useApi<Dashboard>("/api/intelligence/dashboard");
  if(loading)return <main className="page"><Loading/></main>;
  return <main className="page intel-page intel-dashboard public-home">
    <section className="intel-overview">
      <div className="intel-overview-copy"><h1>izlanish.</h1><p>Haqiqiy muammolarni hal qilayotgan loyihalarni topamiz.</p></div>
      <div className="intel-metrics">{[
        ["So‘nggi yangi loyihalar",data?.today.projects],
        ["Jami loyihalar",data?.total.projects],
        ["Bugun tekshirilgan manbalar",data?.today.sources_checked],
      ].map(([label,value])=><div key={String(label)}><strong>{value ?? 0}</strong><span>{label}</span></div>)}</div>
    </section>
    <section className="intel-section intel-projects"><div className="intel-heading"><h2>So‘nggi loyihalar</h2><Link to="/loyihalar">Barcha loyihalar →</Link></div>{data?.latest_projects.length?<div className="intel-project-grid">{data.latest_projects.slice(0,3).map(p=><ProjectPreviewCard p={p} key={p.id}/>)}</div>:<div className="intel-quiet-state"><strong>Oxirgi 30 kunda yangi loyiha nashr etilmadi.</strong><span>Oldingi loyihalar arxivda saqlanadi.</span><Link to="/arxiv">Arxivni ko‘rish →</Link></div>}</section>
  </main>;
}

export function ProblemsPage({adminKey}:{adminKey:string}){
  const [params,setParams]=useSearchParams();
  const scope=params.get("scope")||"";
  const year=params.get("year")||"";
  const page=Math.max(1,Number(params.get("page")||1));
  const query=new URLSearchParams();
  if(scope)query.set("scope",scope);
  if(year)query.set("year",year);
  query.set("page",String(page));
  const {data,loading}=useApi<{items:Problem[];total:number}>("/api/problems?"+query.toString(),0,adminKey);
  const update=(key:string,value:string)=>{const next=new URLSearchParams(params);if(value)next.set(key,value);else next.delete(key);if(key!=="page")next.delete("page");setParams(next)};
  return <main className="page intel-page"><h1>Muammolar</h1><p>Manbada qayd etilgan ehtiyoj va qiyinchiliklar. Taxminlar fakt sifatida ko‘rsatilmaydi.</p>
    <div className="intel-tabs">{[["","Barchasi"],["EVERYDAY","Kundalik"],["UZBEKISTAN_LOCAL","O‘zbekiston"],["GLOBAL","Jahon"]].map(([k,v])=><button className={scope===k?"selected":""} key={k} onClick={()=>update("scope",k)}>{v}</button>)}</div>
    <label>Nashr yili <select value={year} onChange={e=>update("year",e.target.value)}><option value="">Barcha yillar</option>{Array.from({length:new Date().getFullYear()-2021},(_,i)=>2022+i).reverse().map(y=><option key={y} value={y}>{y}</option>)}</select></label>
    {loading?<Loading/>:data?.items.length?<div className="intel-grid">{data.items.map(p=><ProblemCard p={p} key={p.id}/>)}</div>:<Empty>Bu tanlov uchun tasdiqlangan muammo yo‘q.</Empty>}
    {data&&data.total>12&&<div className="intel-tabs"><button disabled={page===1} onClick={()=>update("page",String(page-1))}>← Oldingi</button><span>{page}-sahifa</span><button disabled={page*12>=data.total} onClick={()=>update("page",String(page+1))}>Keyingi →</button></div>}
  </main>
}
export function ProblemDetailPage({adminKey}:{adminKey:string}){const {id}=useParams();const {data:p,loading}=useApi<Problem>(`/api/problems/${encodeURIComponent(id||"")}`,0,adminKey);if(loading)return <main className="page"><Loading/></main>;if(!p)return <main className="page"><Empty>Muammo topilmadi.</Empty></main>;return <main className="page intel-page"><Link to="/admin/muammolar">← Muammolar</Link><span className="tag">{scopeLabels[p.scope]||p.scope}</span><h1>{p.title_uz}</h1><p>{p.description_uz}</p><dl className="intel-facts"><div><dt>Kimda bu muammo bor?</dt><dd>{p.affected_users||"Aniqlanmagan"}</dd></div><div><dt>Dalil darajasi</dt><dd>{p.evidence_level}/5</dd></div><div><dt>Yo‘nalish</dt><dd>{p.sector}</dd></div></dl><h2>Manbalar va dalillar</h2>{p.evidence?.map((e,i)=><blockquote className="intel-quote" key={i}>{e.quote}<div><External href={e.source_url}>Asl manba</External></div></blockquote>)}<h2>Mavjud yechimlar</h2>{p.projects?.length?p.projects.map(x=><p key={x.id}><Link to={`/loyiha/${x.id}`}>{x.name} →</Link></p>):<Empty>Hozircha bog‘langan tasdiqlangan loyiha yo‘q.</Empty>}<h2>Yechim g‘oyalari</h2>{p.ideas?.length?p.ideas.map(x=><p key={x.id}><Link to={`/admin/goya/${x.id}`}>{x.idea_title} →</Link></p>):<Empty>Dalil yetarli bo‘lmagani uchun g‘oya yaratilmagan.</Empty>}</main>}
export function IdeasPage({adminKey}:{adminKey:string}){const {data,loading}=useApi<Idea[]>("/api/ideas",0,adminKey);return <main className="page intel-page"><h1>Yechim g‘oyalari</h1><p>Bu sahifadagi g‘oyalar mavjud startap emas, tekshirilishi kerak bo‘lgan gipotezalardir.</p>{loading?<Loading/>:data?.length?<div className="intel-grid">{data.map(i=><article className="intel-card" key={i.id}><span className="tag">GIPOTEZA</span><h3><Link to={`/admin/goya/${i.id}`}>{i.idea_title}</Link></h3><p>{i.idea_summary}</p></article>)}</div>:<Empty>Hozircha dalilga asoslangan yechim g‘oyasi yaratilmagan.</Empty>}</main>}
export function IdeaDetailPage({adminKey}:{adminKey:string}){const {id}=useParams();const {data:i,loading}=useApi<Idea>(`/api/ideas/${encodeURIComponent(id||"")}`,0,adminKey);if(loading)return <main className="page"><Loading/></main>;if(!i)return <main className="page"><Empty>G‘oya topilmadi.</Empty></main>;return <main className="page intel-page"><span className="tag">TIZIM GIPOTEZASI · MAVJUD MAHSULOT EMAS</span><h1>{i.idea_title}</h1><p>{i.idea_summary}</p><p><Link to={`/admin/muammo/${i.problem_id}`}>Asosiy muammo →</Link></p>{[["Kim uchun",i.target_user],["Taklif etilgan yechim",i.proposed_solution],["Hozirgi muqobillar",i.current_alternatives],["Muqobillarning kamchiligi",i.why_current_alternatives_fail],["Biznes modeli gipotezasi",i.business_model_hypothesis],["MVP gipotezasi",i.mvp_hypothesis],["Xatarlar",i.main_risks]].map(([label,value])=><section className="intel-section" key={label}><h2>{label}</h2><p>{value||"Hozircha dalil yetarli emas."}</p></section>)}</main>}
export function SignalsPage({adminKey}:{adminKey:string}){const {data,loading}=useApi<Signal[]>("/api/signals",0,adminKey);return <main className="page intel-page"><h1>Signallar</h1><p>Bozor va ekotizim xabarlari. Signal avtomatik ravishda loyiha yoki tasdiqlangan talab degani emas.</p>{loading?<Loading/>:data?.length?<div className="intel-grid">{data.map(s=><SignalCard s={s} key={s.url}/>)}</div>:<Empty>Hozircha signal yo‘q.</Empty>}</main>}
export function SectorsPage({adminKey}:{adminKey:string}){const {data,loading}=useApi<{sector:string;label:string;projects:number;problems:number;signals:number;average_opportunity:number|null;sample_size:number}[]>("/api/sectors/intelligence",0,adminKey);return <main className="page intel-page"><h1>Sektorlar</h1><p>Faqat bazada mavjud tasdiqlangan yozuvlar sanaladi. Kichik tanlama bo‘yicha kuchli bozor xulosasi chiqarilmaydi.</p>{loading?<Loading/>:data?.length?<div className="intel-grid">{data.map(s=><article className="intel-card" key={s.sector}><h3>{s.label}</h3><p>{s.projects} loyiha · {s.problems} muammo · {s.signals} signal</p><small>O‘rtacha imkoniyat: {s.average_opportunity===null?"Baholanmagan":`${s.average_opportunity}/100 (${s.sample_size} ta baho)`}</small></article>)}</div>:<Empty>Hozircha sektor ma’lumotlari yo‘q.</Empty>}</main>}
type PublicSource = {id:string;name:string;url:string;group:string};
export function SourcesPage(){const {data,loading}=useApi<PublicSource[]>("/api/public/sources");const groups=[...new Set(data?.map(source=>source.group)||[])];return <main className="page intel-page public-sources"><h1>Manbalar</h1><p>izlanish loyihalarni turli ochiq manbalardan topadi. Loyihani tasdiqlashda asl mahsulot, tashkilot yoki tadbir manbasiga ustunlik beriladi. Har bir loyiha dalil havolalarini saqlaydi.</p>{loading?<Loading/>:groups.map(group=><section className="intel-section" key={group}><h2>{group}</h2><div className="source-list">{data?.filter(source=>source.group===group).map(source=><article key={source.id}><h3>{source.name}</h3><External href={source.url}>Manbaga o‘tish</External></article>)}</div></section>)}</main>}

export function ArchivePage(){
  const [params,setParams]=useSearchParams();
  const [query,setQuery]=useState(params.get("q")||"");
  const period=params.get("period")||"all";
  const year=params.get("year")||"";
  const page=Math.max(1,Number(params.get("page")||1));
  const request=new URLSearchParams({period,page:String(page)});
  if(year)request.set("year",year);
  if(params.get("q"))request.set("q",params.get("q")!);
  const {data,loading}=useApi<{items:Project[];total:number;page_size:number}>("/api/projects?"+request.toString());
  const meta=useApi<{categories:Record<string,string>}>("/api/meta");
  const update=(key:string,value:string)=>{const next=new URLSearchParams(params);if(key!=="page")next.delete("page");if(value)next.set(key,value);else next.delete(key);if(key==="year"&&value)next.delete("period");if(key==="period"&&value!=="all")next.delete("year");setParams(next)};
  return <main className="page intel-page archive-page"><h1>Arxiv</h1><p>Loyihalar topilgan kuniga emas, manbadagi nashr sanasiga ko‘ra joylashtiriladi. Eski loyihalar saqlanadi.</p>
    <div className="catalog-controls"><div className="intel-tabs" aria-label="Arxiv davri">{[["today","Bugun"],["7d","7 kun"],["30d","30 kun"],["all","Barcha yillar"]].map(([value,label])=><button key={value} className={period===value&&!year?"selected":""} onClick={()=>update("period",value)}>{label}</button>)}</div><label>Yil <select value={year} onChange={event=>update("year",event.target.value)}><option value="">Barcha yillar</option>{Array.from({length:new Date().getFullYear()-2021},(_,i)=>2022+i).reverse().map(y=><option value={y} key={y}>{y}</option>)}</select></label><form className="catalog-search" role="search" onSubmit={event=>{event.preventDefault();update("q",query.trim())}}><input aria-label="Arxivda loyiha nomini qidirish" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Loyiha nomi"/><button type="submit">Qidirish</button></form></div>
    <p className="catalog-count">{data?.total??0} ta loyiha</p>{loading?<Loading/>:data?.items.length?<div className="catalog-grid">{data.items.map(project=><Card key={project.id} project={project} categories={meta.data?.categories||{}}/>)}</div>:<div className="intel-quiet-state"><strong>Bu davr uchun loyiha topilmadi.</strong><span>Boshqa yilni tanlang yoki barcha arxivni ko‘ring.</span></div>}
    {data&&data.total>data.page_size&&<div className="pagination"><button disabled={page===1} onClick={()=>update("page",String(page-1))}>← Oldingi</button><span>{page}-sahifa</span><button disabled={page*data.page_size>=data.total} onClick={()=>update("page",String(page+1))}>Keyingi →</button></div>}
  </main>;
}
