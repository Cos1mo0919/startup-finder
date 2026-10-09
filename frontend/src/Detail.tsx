import { ArrowLeft, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorBox, External, Loading, ProjectImage } from "./components";
import type { Project } from "./types";
import { useApi } from "./useApi";
import { date } from "./utils";

const scoreLabels: Record<string,string> = {clarity:"Aniqlik",real_product:"Mahsulot dalili",novelty:"Yangilik",potential:"Salohiyat"};
export function Detail() {
  const {id}=useParams();
  const [retry,setRetry]=useState(0);
  const {data:p,error,loading}=useApi<Project>("/api/projects/"+encodeURIComponent(id||""),retry);
  if(loading)return <main className="page"><Loading/></main>;
  if(error||!p)return <main className="page"><Link to="/loyihalar">← Loyihalarga qaytish</Link><ErrorBox retry={()=>setRetry(retry+1)}/></main>;
  const facts=p.content?.facts||[];
  const benefit=p.content?.individual_benefit_uz||p.content?.business_benefit_uz||p.content?.why_now_uz||"";
  const description=p.short_description||p.summary_uz;
  const hasAnalysis=!!(p.problem_statement||p.problem_subject||benefit||p.secondary_problems?.length||p.opportunity_score!==null);
  return <main className="page detail public-detail">
    <Link className="back-link" to="/loyihalar"><ArrowLeft size={16}/> Loyihalarga qaytish</Link>
    <header className="detail-heading"><span className="category">{p.country==="Uzbekistan"?"O‘zbekiston":p.country||"Davlat noma’lum"} · {p.primary_sector||"Other"} · {date(p.published_at)}{p.date_estimated?" (taxminiy)":""}</span><h1>{p.name}</h1>{(p.creator||p.organization)&&<p>{p.creator||p.organization}</p>}</header>
    <div className="public-detail-layout"><div className="public-detail-main">
      <section className="detail-section"><h2>Loyiha nima qiladi?</h2><p>{description}</p><div className="catalog-detail-meta"><span>{p.catalog_score===null||p.score_pending?"Baholanmagan":`${p.catalog_score.toFixed(1)} / 10`}</span><span>{p.source_count} ta manba</span><span>{p.project_type}</span></div></section>
      <section className="detail-section"><h2>Asl manbalar</h2>{p.official_url&&<p><External href={p.official_url}>Rasmiy loyiha sahifasi</External></p>}{p.sources?.map(source=><p key={source.url}><External href={source.url}>{source.publisher} · {date(source.published_at)}</External></p>)}</section>
      {!!facts.length&&<section className="detail-section"><h2><ShieldCheck size={20}/> Tasdiqlangan asosiy faktlar</h2>{facts.map((fact,index)=><div className="fact" key={index}><p>{fact.text_uz}</p><External href={fact.source_url}>Asl dalil</External><details><summary>Original iqtibos</summary><blockquote>{fact.quote}</blockquote></details></div>)}</section>}
      {!facts.length&&!!p.sources?.some(source=>source.quotes.length)&&<section className="detail-section"><h2>Manbadagi tavsif</h2>{p.sources?.flatMap(source=>source.quotes.slice(0,1).map(quote=><blockquote key={source.url}>{quote} <External href={source.url}>Manba</External></blockquote>))}</section>}
      {hasAnalysis&&<details className="detail-section public-analysis"><summary>Batafsil tahlil</summary>{p.problem_statement&&<section><h3>Qanday muammoni hal qiladi?</h3><p>{p.problem_statement}</p></section>}{p.problem_subject&&<section><h3>Kim uchun?</h3><p>{p.problem_subject}</p></section>}{benefit&&<section><h3>Nega foydali?</h3><p>{benefit}</p><small>Tizim tahlili — tasdiqlangan fakt emas</small></section>}{p.secondary_problems?.length?<section><h3>Qo‘shimcha muammolar</h3>{p.secondary_problems.map(problem=><p key={problem.problem_id}>{problem.statement} <External href={problem.source_url}>Dalil</External></p>)}</section>:null}{p.opportunity_score!==null&&<p>Imkoniyat: {p.opportunity_score}/100 · {p.opportunity_grade}</p>}</details>}
      {p.catalog_score!==null&&!p.score_pending&&<details className="detail-section public-analysis"><summary>Katalog bahosi</summary><dl className="catalog-factor-list">{Object.entries(p.catalog_scores).map(([key,value])=><div key={key}><dt>{scoreLabels[key]||key}</dt><dd>{value}/10 · {p.score_reasons?.[key]||""}</dd></div>)}</dl></details>}
    </div><aside className="public-detail-aside"><ProjectImage project={p}/><dl><div><dt>Soha</dt><dd>{p.primary_sector||"Other"}</dd></div><div><dt>Davlat</dt><dd>{p.country||"Aniqlanmagan"}</dd></div><div><dt>Manbalar</dt><dd>{p.source_count}</dd></div></dl></aside></div>
  </main>;
}
