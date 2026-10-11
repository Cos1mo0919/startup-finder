import { Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, ErrorBox, Loading } from "./components";
import type { Project } from "./types";
import { useApi } from "./useApi";

export function Home() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || "");
  const [refresh, setRefresh] = useState(0);
  const country = params.get("country") || "";
  const page = Math.max(1, Number(params.get("page") || 1));
  const request = new URLSearchParams({period: "all", sort: "catalog", page: String(page)});
  if (country) request.set("country", country);
  if (params.get("q")) request.set("q", params.get("q")!);
  const results = useApi<{items: Project[]; total: number; page: number; page_size: number}>("/api/projects?" + request, refresh);
  const meta = useApi<{categories: Record<string,string>}>("/api/meta");
  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (key !== "page") next.delete("page");
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  };
  return <main className="page catalog-page">
    <div className="catalog-heading"><h1>Loyihalar</h1><p>Mahsulotlar, startaplar va prototiplar — qisqa tavsif va asl manbalar bilan.</p></div>
    <div className="catalog-controls">
      <div className="intel-tabs" aria-label="Loyihalar hududi">{[["","Barchasi"],["Uzbekistan","O‘zbekiston"],["global","Global"],["github","GitHub"]].map(([value,label])=><button key={value} className={country===value?"selected":""} onClick={()=>change("country",value)}>{label}</button>)}</div>
      <form className="catalog-search" role="search" onSubmit={event=>{event.preventDefault();change("q",query.trim())}}><Search size={18}/><input aria-label="Loyiha nomini qidirish" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Loyiha nomi"/><button type="submit">Qidirish</button></form>
    </div>
    <div className="catalog-count">{results.data?.total ?? 0} ta loyiha</div>
    {results.error?<ErrorBox retry={()=>setRefresh(refresh+1)}/>:results.loading?<Loading/>:results.data?.items.length?<div className="catalog-grid">{results.data.items.map(project=><Card key={project.id} project={project} categories={meta.data?.categories || {}}/>)}</div>:<div className="intel-quiet-state"><strong>Mos loyiha topilmadi.</strong><span>Boshqa nom yoki hududni tanlang.</span></div>}
    {results.data && results.data.total > results.data.page_size && <div className="pagination"><button disabled={page===1} onClick={()=>change("page",String(page-1))}>← Oldingi</button><span>{page}-sahifa</span><button disabled={page*results.data!.page_size>=results.data.total} onClick={()=>change("page",String(page+1))}>Keyingi →</button></div>}
  </main>;
}
