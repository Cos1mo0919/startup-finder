import { Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, ErrorBox, Loading } from "./components";
import type { Project } from "./types";
import { useApi } from "./useApi";
import { date } from "./utils";

type Facets = {total:number;sections:Record<string,number>;years:Record<string,number>;recent?:Recent};
type Recent = {period:"this_week"|"last_week";start:string;end:string;total:number};

export function Home({section}:{section?:"boshqa"}={}) {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || "");
  const [refresh, setRefresh] = useState(0);
  const country = section || params.get("country") || "";
  const year = params.get("year") || "";
  const recentOnly = params.get("period") === "recent";
  const page = Math.max(1, Number(params.get("page") || 1));
  const request = new URLSearchParams({period: recentOnly ? "recent" : "all", sort: "catalog", page: String(page)});
  if (country) request.set("country", country);
  if (year) request.set("year", year);
  if (params.get("q")) request.set("q", params.get("q")!);
  const results = useApi<{items: Project[]; total: number; page: number; page_size: number}>("/api/projects?" + request, refresh);
  const meta = useApi<{categories: Record<string,string>}>("/api/meta");
  const facets = useApi<Facets>("/api/catalog/facets");
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (key !== "page") next.delete("page");
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  };
  return <main className="page catalog-page">
    <div className="catalog-heading"><h1>{section ? "Boshqa" : "Loyihalar"}</h1><p>{section ? "Bo‘limi ishonchli aniqlanmagan, lekin nashrga yaroqli loyihalar." : "Mahsulotlar, startaplar va prototiplar — qisqa tavsif va asl manbalar bilan."}</p></div>
    <div className="catalog-controls">
      <label>Davr <select aria-label="Davr" value={recentOnly ? "recent" : ""} onChange={event=>change("period",event.target.value)}><option value="">Barcha vaqt ({facets.data?.total??0})</option><option value="recent">So‘nggi paytda ({facets.data?.recent?.total??0})</option></select></label>
      <label>Yil <select aria-label="Yil" value={year} onChange={event=>change("year",event.target.value)}><option value="">Barchasi ({facets.data?.total??0})</option>{[2026,2025].map(value=><option key={value} value={value}>{value} ({facets.data?.years[String(value)]??0})</option>)}</select></label>
      {!section && <label>Bo‘lim <select aria-label="Bo‘lim" value={country} onChange={event=>change("country",event.target.value)}><option value="">Barchasi ({facets.data?.total??0})</option>{[["Uzbekistan","O‘zbekiston"],["global","Global"],["github","GitHub"],["boshqa","Boshqa"]].map(([value,label])=><option key={value} value={value}>{label} ({facets.data?.sections[value==="global"?"Global":value==="github"?"GitHub":value==="boshqa"?"Boshqa":"Uzbekistan"]??0})</option>)}</select></label>}
      <form className="catalog-search" role="search" onSubmit={event=>{event.preventDefault();change("q",query.trim())}}><Search size={18}/><input aria-label="Loyiha nomini qidirish" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Loyiha nomi"/><button type="submit">Qidirish</button></form>
    </div>
    {recentOnly && facets.data?.recent && <p className="catalog-recent-note">{facets.data.recent.period==="this_week"?"Joriy hafta":"O‘tgan hafta"}: {date(facets.data.recent.start)} — {date(facets.data.recent.end)}</p>}
    <div className="catalog-count">Ko‘rsatilmoqda: {results.data?.items.length ?? 0} / {results.data?.total ?? 0} ta loyiha</div>
    {results.error?<ErrorBox retry={()=>setRefresh(refresh+1)}/>:results.loading?<Loading/>:results.data?.items.length?<div className="catalog-grid">{results.data.items.map(project=><Card key={project.id} project={project} categories={meta.data?.categories || {}}/>)}</div>:<div className="intel-quiet-state"><strong>Mos loyiha topilmadi.</strong><span>Boshqa nom yoki hududni tanlang.</span></div>}
    {results.data && results.data.total > results.data.page_size && <div className="pagination"><button disabled={page===1} onClick={()=>change("page",String(page-1))}>← Oldingi</button><span>{page}-sahifa</span><button disabled={page*results.data!.page_size>=results.data.total} onClick={()=>change("page",String(page+1))}>Keyingi →</button></div>}
  </main>;
}
