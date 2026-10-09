import { ArrowLeft, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorBox, External, Loading, ProjectImage, Ratings } from "./components";
import type { Project } from "./types";
import { useApi } from "./useApi";
import { date } from "./utils";

export function Detail() {
  const {id}=useParams();
  const [retry,setRetry]=useState(0);
  const {data:p,error,loading}=useApi<Project>("/api/projects/"+encodeURIComponent(id||""),retry);
  if(loading)return <main className="page"><Loading/></main>;
  if(error||!p)return <main className="page"><Link to="/loyihalar">← Loyihalarga qaytish</Link><ErrorBox retry={()=>setRetry(retry+1)}/></main>;
  const content=p.content!;
  const benefit=content.individual_benefit_uz||content.business_benefit_uz||content.why_now_uz||"";
  return <main className="page detail public-detail">
    <Link className="back-link" to="/loyihalar"><ArrowLeft size={16}/> Loyihalarga qaytish</Link>
    <header className="detail-heading"><span className="category">{p.country==="Uzbekistan"?"O‘zbekiston":"Global"} · {date(p.published_at)}</span><h1>{p.name}</h1><p>{p.creator||p.organization}</p></header>
    <div className="public-detail-layout"><div className="public-detail-main">
      <section className="detail-section"><h2>Qanday muammoni hal qiladi?</h2><p>{p.problem_statement}</p></section>
      <section className="detail-section"><h2>Kim uchun?</h2><p>{p.problem_subject}</p></section>
      <section className="detail-section"><h2>Yechim qanday ishlaydi?</h2><p>{p.solution_uz}</p></section>
      {benefit&&<section className="detail-section"><h2>Nega foydali?</h2><p>{benefit}</p><small>{content.why_now_uz===benefit?"Tizim tahlili — tasdiqlangan fakt emas":"Manbadagi tavsif"}</small></section>}
      <section className="detail-section"><h2><ShieldCheck size={20}/> Tasdiqlangan asosiy faktlar</h2>{content.facts.map((fact,index)=><div className="fact" key={index}><p>{fact.text_uz}</p><External href={fact.source_url}>Asl dalil</External><details><summary>Original iqtibos</summary><blockquote>{fact.quote}</blockquote></details></div>)}</section>
      <section className="detail-section"><h2>Asl manbalar</h2>{p.official_url&&<p><External href={p.official_url}>Rasmiy loyiha sahifasi</External></p>}{p.sources?.map(source=><p key={source.url}><External href={source.url}>{source.publisher} · {date(source.published_at)}</External></p>)}</section>
      {(p.opportunity_score!==null||!!p.secondary_problems?.length)&&<details className="detail-section public-analysis"><summary>Batafsil tahlil</summary>{p.secondary_problems?.length?<section><h3>Qo‘shimcha muammolar</h3>{p.secondary_problems.map(problem=><p key={problem.problem_id}>{problem.statement} <External href={problem.source_url}>Dalil</External></p>)}</section>:null}{p.opportunity_score!==null&&<><p>Imkoniyat: {p.opportunity_score}/100 · {p.opportunity_grade}</p><Ratings title="Foydalilik reytingi" total={p.rating} components={p.rating_components||{}}/><Ratings title="Ishonchlilik reytingi" total={p.confidence} components={p.confidence_components||{}}/></>}</details>}
    </div><aside className="public-detail-aside"><ProjectImage project={p}/><dl><div><dt>Soha</dt><dd>{p.primary_sector}</dd></div><div><dt>Davlat</dt><dd>{p.country}</dd></div><div><dt>Manbalar</dt><dd>{p.source_count}</dd></div></dl></aside></div>
  </main>;
}
