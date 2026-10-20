import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { StatusPage } from "./StatusPage";
import { External, Loading, NotFound } from "./components";
import { useApi } from "./useApi";
import { ProblemsPage, ProblemDetailPage, IdeasPage, IdeaDetailPage, SignalsPage, SectorsPage } from "./Intelligence";

type ReviewItem = {url:string;title:string;source_id:string|null;status:string;reason:string;detector_result:string;canonical_project:string;creator:string;primary_problem:string;evidence:{url:string;type:string;quote:string}[];confidence:number|null;review_decision:string};
type Yield = {source_id:string;name:string;enabled:boolean;items_fetched:number;candidate_records:number;project_candidates:number;verified_projects:number;published_projects:number;rejected_items:number;dominant_rejection_reasons:[string,number][]};
type CatalogItem = {id:string;name:string;status:string;reason:string;method:string;analysis_method:string;scope:string;section_reason:string;source_count:number};

function CatalogReview({adminKey}:{adminKey:string}) {
  const [refresh,setRefresh]=useState(0);
  const [message,setMessage]=useState("");
  const [reason,setReason]=useState("");
  const [target,setTarget]=useState("");
  const [sections,setSections]=useState<Record<string,string>>({});
  const [onlyBoshqa,setOnlyBoshqa]=useState(false);
  const {data,loading,error}=useApi<{total:number;items:CatalogItem[]}>(onlyBoshqa?"/api/admin/catalog?section=Boshqa":"/api/admin/catalog",refresh,adminKey);
  const act=async (item:CatalogItem,action:"PUBLISH"|"HIDE"|"REJECT"|"MERGE")=>{
    const params=new URLSearchParams({action,reason,target_id:target});
    const response=await fetch(`/api/admin/projects/${encodeURIComponent(item.id)}/action?${params}`,{method:"POST",headers:{"X-Admin-Key":adminKey}});
    setMessage(response.ok?`${item.name}: ${action}`:`${item.name}: qaror saqlanmadi`);
    if(response.ok)setRefresh(value=>value+1);
  };
  const assign=async(item:CatalogItem)=>{
    const params=new URLSearchParams({section:sections[item.id]||item.scope,reason:reason.trim()});
    const response=await fetch(`/api/admin/projects/${encodeURIComponent(item.id)}/section?${params}`,{method:"POST",headers:{"X-Admin-Key":adminKey}});
    setMessage(response.ok?`${item.name}: bo‘lim yangilandi`:`${item.name}: bo‘lim saqlanmadi`);
    if(response.ok)setRefresh(value=>value+1);
  };
  return <section className="detail-section"><h1>Loyihalar boshqaruvi</h1><p>{data?.total||0} ta loyiha yozuvi. Birlashtirish manba va dalillarni saqlaydi.</p><label><input type="checkbox" checked={onlyBoshqa} onChange={event=>setOnlyBoshqa(event.target.checked)}/> Faqat Boshqa</label><label>Qaror sababi <input value={reason} onChange={event=>setReason(event.target.value)} /></label><label>Birlashtirish manzili ID <input value={target} onChange={event=>setTarget(event.target.value)} /></label>{message&&<p role="status">{message}</p>}{loading?<Loading/>:error?<p>Ro‘yxatni yuklab bo‘lmadi.</p>:<div className="admin-review-list">{data?.items.map(item=><article className="intel-card" key={item.id}><h2>{item.name}</h2><p>{item.status} · {item.scope} · {item.reason||"—"} · {item.analysis_method} · {item.source_count} manba</p><small>{item.id}</small><div className="admin-actions"><button onClick={()=>act(item,"PUBLISH")}>Nashr</button><button disabled={!reason.trim()} onClick={()=>act(item,"HIDE")}>Yashirish</button><button disabled={!reason.trim()} onClick={()=>act(item,"REJECT")}>Rad etish</button><button disabled={!target.trim()} onClick={()=>act(item,"MERGE")}>Birlashtirish</button><select aria-label={`${item.name} bo‘limi`} value={sections[item.id]||item.scope} onChange={event=>setSections({...sections,[item.id]:event.target.value})}>{[["Uzbekistan","O‘zbekiston"],["Global","Global"],["GitHub","GitHub"],["Boshqa","Boshqa"]].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><button disabled={!reason.trim()} onClick={()=>assign(item)}>Bo‘limni saqlash</button></div></article>)}</div>}</section>;
}

function ReviewQueue({adminKey}:{adminKey:string}) {
  const [refresh,setRefresh]=useState(0);
  const [reasons,setReasons]=useState<Record<string,string>>({});
  const [message,setMessage]=useState("");
  const {data,loading,error}=useApi<{total:number;items:ReviewItem[]}>("/api/admin/review",refresh,adminKey);
  const act=async (item:ReviewItem,action:"ACCEPT"|"REJECT"|"KEEP_FOR_REVIEW")=>{
    const params=new URLSearchParams({url:item.url,action,reason:reasons[item.url]||""});
    const response=await fetch("/api/admin/review/action?"+params,{method:"POST",headers:{"X-Admin-Key":adminKey}});
    setMessage(response.ok?"Qaror saqlandi. Qabul qilingan nomzod oddiy tekshiruvga qaytadi.":"Qarorni saqlab bo‘lmadi.");
    if(response.ok)setRefresh(value=>value+1);
  };
  return <section className="detail-section"><h2>Ko‘rib chiqish navbati</h2><p>Qabul qilish loyiha nashriga ruxsat bermaydi; barcha dalil darvozalari qayta ishlaydi.</p>{message&&<p role="status">{message}</p>}{loading?<Loading/>:error?<p>Navbatni yuklab bo‘lmadi.</p>:<><p>{data?.total||0} ta nomzod ko‘rib chiqishni kutmoqda.</p><div className="admin-review-list">{data?.items.map(item=><article className="intel-card" key={item.url}><h3>{item.canonical_project||item.title||item.url}</h3><p>{item.source_id||"Manba noma’lum"} · {item.status} · {item.reason}</p><p>Yaratuvchi: {item.creator||"Aniqlanmagan"} · Dalil ishonchi: {item.confidence??"Aniqlanmagan"}</p><p>Muammo: {item.primary_problem||"Aniqlanmagan"}</p><External href={item.url}>Asl manba</External>{item.evidence.map((e,index)=><blockquote key={index}>{e.quote}</blockquote>)}<div className="admin-actions"><button onClick={()=>act(item,"ACCEPT")}>Qayta tekshirish</button><button onClick={()=>act(item,"KEEP_FOR_REVIEW")}>Navbatda qoldirish</button><select aria-label="Rad sababi" value={reasons[item.url]||""} onChange={event=>setReasons({...reasons,[item.url]:event.target.value})}><option value="">Rad sababi</option>{["not_project","no_meaningful_problem","minor_feature","duplicate","insufficient_evidence","missing_creator","signal_only","irrelevant","old_irrelevant_content","other"].map(reason=><option key={reason}>{reason}</option>)}</select><button disabled={!reasons[item.url]} onClick={()=>act(item,"REJECT")}>Rad etish</button></div></article>)}</div></>}</section>;
}

function SourceYield({adminKey}:{adminKey:string}) {
  const {data,loading}=useApi<Yield[]>("/api/admin/source-yield",0,adminKey);
  return <section className="detail-section"><h2>Manbalar samarasi</h2>{loading?<Loading/>:<div className="admin-yield-table"><table><thead><tr><th>Manba</th><th>Topilgan</th><th>Nomzod</th><th>Tasdiqlangan</th><th>Nashr</th><th>Rad</th><th>Asosiy sabab</th></tr></thead><tbody>{data?.map(row=><tr key={row.source_id}><td>{row.name}</td><td>{row.items_fetched}</td><td>{row.project_candidates}</td><td>{row.verified_projects}</td><td>{row.published_projects}</td><td>{row.rejected_items}</td><td>{row.dominant_rejection_reasons.map(([reason,count])=>`${reason}: ${count}`).join(", ")||"—"}</td></tr>)}</tbody></table></div>}</section>;
}

const ADMIN_KEY_STORAGE="izlanish-admin-key";
let verifiedKey:string|null=null; // Key the server accepted in this tab; avoids re-checks between sections.

function readStoredKey(){try{return sessionStorage.getItem(ADMIN_KEY_STORAGE)||""}catch{return ""}}
function storeKey(value:string|null){try{if(value)sessionStorage.setItem(ADMIN_KEY_STORAGE,value);else sessionStorage.removeItem(ADMIN_KEY_STORAGE)}catch{/* storage unavailable */}}
function keyFromHash(){
  // Entry point: /admin#KEY. The fragment is never sent to the server or written to its logs.
  const raw=window.location.hash.slice(1);
  if(!raw)return "";
  try{return decodeURIComponent(raw)}catch{return raw}
}

export function AdminPage({section="status"}:{section?:"status"|"review"|"catalog"|"sources"|"problems"|"problem"|"ideas"|"idea"|"signals"|"sectors"}) {
  const navigate=useNavigate();
  const [candidate,setCandidate]=useState(()=>keyFromHash()||readStoredKey());
  const [attempt,setAttempt]=useState(0);
  const [state,setState]=useState<"checking"|"ok"|"denied">(()=>!candidate?"denied":candidate===verifiedKey?"ok":"checking");
  useEffect(()=>{
    // Typing "#KEY" after an already open /admin changes only the fragment (no reload).
    const onHash=()=>{const next=keyFromHash();if(next){setState(next===verifiedKey?"ok":"checking");setCandidate(next);setAttempt(value=>value+1)}};
    window.addEventListener("hashchange",onHash);
    return ()=>window.removeEventListener("hashchange",onHash);
  },[]);
  useEffect(()=>{
    if(window.location.hash)window.history.replaceState(window.history.state,"",window.location.pathname+window.location.search);
    if(!candidate||candidate===verifiedKey)return;
    const controller=new AbortController();
    fetch("/api/admin/verify",{headers:{"X-Admin-Key":candidate},signal:controller.signal})
      .then(response=>{
        if(response.ok){verifiedKey=candidate;storeKey(candidate);setState("ok")}
        else{verifiedKey=null;storeKey(null);setState("denied")}
      })
      .catch(()=>{if(!controller.signal.aborted)setState("denied")});
    return ()=>controller.abort();
  },[candidate,attempt]);
  if(state==="checking")return <main className="page" aria-busy="true"/>;
  if(state==="denied")return <NotFound/>;
  const key=candidate;
  const logout=()=>{verifiedKey=null;storeKey(null);navigate("/",{replace:true})};
  return <><nav className="page admin-nav" aria-label="Admin menyusi"><Link to="/admin/status">Holat</Link><Link to="/admin/review">Ko‘rib chiqish</Link><Link to="/admin/catalog">Loyihalar</Link><Link to="/admin/sources">Manbalar samarasi</Link><Link to="/admin/muammolar">Muammolar</Link><Link to="/admin/goyalar">G‘oyalar</Link><Link to="/admin/signallar">Signallar</Link><Link to="/admin/sektorlar">Sektorlar</Link><button onClick={logout}>Chiqish</button></nav>{section==="status"?<StatusPage adminKey={key}/>:section==="problems"?<ProblemsPage adminKey={key}/>:section==="problem"?<ProblemDetailPage adminKey={key}/>:section==="ideas"?<IdeasPage adminKey={key}/>:section==="idea"?<IdeaDetailPage adminKey={key}/>:section==="signals"?<SignalsPage adminKey={key}/>:section==="sectors"?<SectorsPage adminKey={key}/>:<main className="page admin-page">{section==="review"?<ReviewQueue adminKey={key}/>:section==="catalog"?<CatalogReview adminKey={key}/>:<SourceYield adminKey={key}/>}</main>}</>;
}
