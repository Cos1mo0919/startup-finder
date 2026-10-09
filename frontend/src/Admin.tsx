import { useState } from "react";
import { Link } from "react-router-dom";
import { StatusPage } from "./StatusPage";
import { External, Loading } from "./components";
import { useApi } from "./useApi";

type ReviewItem = {url:string;title:string;source_id:string|null;status:string;reason:string;detector_result:string;canonical_project:string;creator:string;primary_problem:string;evidence:{url:string;type:string;quote:string}[];confidence:number|null;review_decision:string};
type Yield = {source_id:string;name:string;enabled:boolean;items_fetched:number;candidate_records:number;project_candidates:number;verified_projects:number;published_projects:number;rejected_items:number;dominant_rejection_reasons:[string,number][]};

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

export function AdminPage({section="status"}:{section?:"status"|"review"|"sources"}) {
  const [key,setKey]=useState(()=>sessionStorage.getItem("izlanish-admin-key")||"");
  const [input,setInput]=useState("");
  if(!key)return <main className="page admin-login"><h1>Egasi uchun boshqaruv</h1><p>Texnik ma’lumotlar va ko‘rib chiqish navbati faqat administratorga ochiq.</p><form onSubmit={event=>{event.preventDefault();sessionStorage.setItem("izlanish-admin-key",input);setKey(input)}}><label>Admin kaliti <input type="password" value={input} onChange={event=>setInput(event.target.value)} autoComplete="off"/></label><button type="submit" disabled={!input}>Kirish</button></form></main>;
  return <><nav className="page admin-nav" aria-label="Admin menyusi"><Link to="/admin/status">Holat</Link><Link to="/admin/review">Ko‘rib chiqish</Link><Link to="/admin/sources">Manbalar samarasi</Link><button onClick={()=>{sessionStorage.removeItem("izlanish-admin-key");setKey("")}}>Chiqish</button></nav>{section==="status"?<StatusPage adminKey={key}/>:<main className="page admin-page">{section==="review"?<ReviewQueue adminKey={key}/>:<SourceYield adminKey={key}/>}</main>}</>;
}
