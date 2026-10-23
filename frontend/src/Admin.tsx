import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { clearAdminSession, readStoredKey, setVerifiedKey, useAdminVerified, verifiedKey } from "./adminSession";
import { StatusPage } from "./StatusPage";
import { External, Loading, NotFound } from "./components";
import { useApi } from "./useApi";
import { ProblemsPage, ProblemDetailPage, IdeasPage, IdeaDetailPage, SignalsPage, SectorsPage } from "./Intelligence";

type ReviewItem = {url:string;title:string;source_id:string|null;status:string;reason:string;detector_result:string;canonical_project:string;creator:string;primary_problem:string;evidence:{url:string;type:string;quote:string}[];confidence:number|null;review_decision:string;publishable?:boolean};
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
  return <section className="detail-section"><h1>Loyihalar boshqaruvi</h1><p>{data?.total||0} ta loyiha yozuvi. Birlashtirish manba va dalillarni saqlaydi.</p><label><input type="checkbox" checked={onlyBoshqa} onChange={event=>setOnlyBoshqa(event.target.checked)}/> Faqat Boshqa</label><label>Qaror sababi <input value={reason} onChange={event=>setReason(event.target.value)} /></label><label>Birlashtirish manzili ID <input value={target} onChange={event=>setTarget(event.target.value)} /></label>{message&&<p role="status">{message}</p>}{loading?<Loading/>:error?<p>Ro‘yxatni yuklab bo‘lmadi.</p>:<div className="admin-review-list">{data?.items.map(item=><article className="intel-card" key={item.id}><h2>{item.name}</h2><p>{item.status} · {item.scope} · {item.reason||"—"} · {item.analysis_method} · {item.source_count} manba</p><small>{item.id}</small><div className="admin-actions"><button className="btn-primary" onClick={()=>act(item,"PUBLISH")}>Nashr</button><button className="btn-danger" disabled={!reason.trim()} onClick={()=>act(item,"HIDE")}>Yashirish</button><button className="btn-danger" disabled={!reason.trim()} onClick={()=>act(item,"REJECT")}>Rad etish</button><button disabled={!target.trim()} onClick={()=>act(item,"MERGE")}>Birlashtirish</button><select aria-label={`${item.name} bo‘limi`} value={sections[item.id]||item.scope} onChange={event=>setSections({...sections,[item.id]:event.target.value})}>{[["Uzbekistan","O‘zbekiston"],["Global","Global"],["GitHub","GitHub"],["Boshqa","Boshqa"]].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><button disabled={!reason.trim()} onClick={()=>assign(item)}>Bo‘limni saqlash</button></div></article>)}</div>}</section>;
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
  const publish=async (item:ReviewItem)=>{
    const response=await fetch("/api/admin/review/publish?"+new URLSearchParams({url:item.url}),{method:"POST",headers:{"X-Admin-Key":adminKey}});
    const detail=response.ok?"":String((await response.json().catch(()=>({})))?.detail||"");
    setMessage(response.ok?"Loyiha saytda nashr etildi.":detail==="not_analysed"?"Avval tahlil kerak: «Qayta tekshirish» tugmasini bosing.":response.status===409?"Bugungi nashr chegarasiga yetildi.":"Nashr etib bo‘lmadi.");
    if(response.ok)setRefresh(value=>value+1);
  };
  return <section className="detail-section"><h2>Ko‘rib chiqish navbati</h2><p>«Nashr etish» tahlil qilingan loyihani darhol saytga chiqaradi. «Qayta tekshirish» nomzodni sun’iy intellekt tahliliga qaytaradi.</p>{message&&<p role="status">{message}</p>}{loading?<Loading/>:error?<p>Navbatni yuklab bo‘lmadi.</p>:<><p>{data?.total||0} ta nomzod ko‘rib chiqishni kutmoqda.</p><div className="admin-review-list">{data?.items.map(item=><article className="intel-card" key={item.url}><h3>{item.canonical_project||item.title||item.url}</h3><p>{item.source_id||"Manba noma’lum"} · {item.status} · {item.reason}</p><p>Yaratuvchi: {item.creator||"Aniqlanmagan"} · Dalil ishonchi: {item.confidence??"Aniqlanmagan"}</p><p>Muammo: {item.primary_problem||"Aniqlanmagan"}</p><External href={item.url}>Asl manba</External>{item.evidence.map((e,index)=><blockquote key={index}>{e.quote}</blockquote>)}<div className="admin-actions"><button className="btn-primary" disabled={!item.publishable} title={item.publishable?"Loyihani saytda nashr etish":"Avval tahlil kerak: «Qayta tekshirish» tugmasini bosing"} onClick={()=>publish(item)}>Nashr etish</button><button onClick={()=>act(item,"ACCEPT")}>Qayta tekshirish</button><button onClick={()=>act(item,"KEEP_FOR_REVIEW")}>Navbatda qoldirish</button><select aria-label="Rad sababi" value={reasons[item.url]||""} onChange={event=>setReasons({...reasons,[item.url]:event.target.value})}><option value="">Rad sababi</option>{["not_project","no_meaningful_problem","minor_feature","duplicate","insufficient_evidence","missing_creator","signal_only","irrelevant","old_irrelevant_content","other"].map(reason=><option key={reason}>{reason}</option>)}</select><button className="btn-danger" disabled={!reasons[item.url]} onClick={()=>act(item,"REJECT")}>Rad etish</button></div></article>)}</div></>}</section>;
}

function SourceYield({adminKey}:{adminKey:string}) {
  const {data,loading}=useApi<Yield[]>("/api/admin/source-yield",0,adminKey);
  return <section className="detail-section"><h2>Manbalar samarasi</h2>{loading?<Loading/>:<div className="admin-yield-table"><table><thead><tr><th>Manba</th><th>Topilgan</th><th>Nomzod</th><th>Tasdiqlangan</th><th>Nashr</th><th>Rad</th><th>Asosiy sabab</th></tr></thead><tbody>{data?.map(row=><tr key={row.source_id}><td>{row.name}</td><td>{row.items_fetched}</td><td>{row.project_candidates}</td><td>{row.verified_projects}</td><td>{row.published_projects}</td><td>{row.rejected_items}</td><td>{row.dominant_rejection_reasons.map(([reason,count])=>`${reason}: ${count}`).join(", ")||"—"}</td></tr>)}</tbody></table></div>}</section>;
}

function stripFragment(){
  // Old "/admin#KEY" links must neither log in nor stay in the address bar.
  if(window.location.hash)window.history.replaceState(window.history.state,"",window.location.pathname+window.location.search);
}

function useBlindKeyEntry(enabled:boolean,submit:(value:string)=>void){
  // On the not-found /admin page the owner types (or pastes) the key and presses Enter.
  // Nothing is shown and nothing goes into the URL or browser history.
  // Layout effect: the listener exists before the page is painted, so no keystroke is lost.
  useLayoutEffect(()=>{
    if(!enabled)return;
    let buffer="";
    let timer=0;
    const reset=()=>{buffer="";window.clearTimeout(timer)};
    const onKey=(event:KeyboardEvent)=>{
      if(event.ctrlKey||event.metaKey||event.altKey||event.isComposing)return;
      if(event.key==="Enter"){
        if(buffer){event.preventDefault();const value=buffer;reset();submit(value)}
        return;
      }
      if(event.key==="Escape"){reset();return}
      if(event.key==="Backspace"){buffer=buffer.slice(0,-1);return}
      if(event.key.length===1){
        buffer=(buffer+event.key).slice(-512);
        window.clearTimeout(timer);
        timer=window.setTimeout(()=>{buffer=""},120000);
      }
    };
    const onPaste=(event:ClipboardEvent)=>{
      const value=event.clipboardData?.getData("text")?.trim();
      if(value){event.preventDefault();reset();submit(value)}
    };
    window.addEventListener("keydown",onKey);
    window.addEventListener("paste",onPaste);
    return ()=>{reset();window.removeEventListener("keydown",onKey);window.removeEventListener("paste",onPaste)};
  },[enabled,submit]);
}

export function AdminPage({section="status"}:{section?:"status"|"review"|"catalog"|"sources"|"problems"|"problem"|"ideas"|"idea"|"signals"|"sectors"}) {
  const [candidate,setCandidate]=useState(()=>verifiedKey()||readStoredKey());
  const [attempt,setAttempt]=useState(0);
  const [typed,setTyped]=useState(false);
  const [state,setState]=useState<"checking"|"ok"|"denied">(()=>!candidate?"denied":candidate===verifiedKey()?"ok":"checking");
  useEffect(()=>{
    stripFragment();
    window.addEventListener("hashchange",stripFragment);
    return ()=>window.removeEventListener("hashchange",stripFragment);
  },[]);
  const submit=useCallback((value:string)=>{
    setTyped(true);
    setState(value===verifiedKey()?"ok":"checking");
    setCandidate(value);
    setAttempt(count=>count+1);
  },[]);
  useBlindKeyEntry(state==="denied",submit);
  useEffect(()=>{
    if(!candidate||candidate===verifiedKey())return;
    const controller=new AbortController();
    fetch("/api/admin/verify",{headers:{"X-Admin-Key":candidate},signal:controller.signal})
      .then(response=>{
        if(response.ok){setVerifiedKey(candidate);setState("ok")}
        else{clearAdminSession();setState("denied")}
      })
      .catch(()=>{if(!controller.signal.aborted)setState("denied")});
    return ()=>controller.abort();
  },[candidate,attempt]);
  // Logging out elsewhere (header "Chiqish") must close this page too.
  const verified=useAdminVerified();
  // A typed attempt keeps the not-found page on screen, so a wrong guess shows nothing at all.
  if(state==="checking")return typed?<NotFound/>:<main className="page" aria-busy="true"/>;
  if(state==="denied"||!verified)return <NotFound/>;
  const key=candidate;
  return <>{section==="status"?<StatusPage adminKey={key}/>:section==="problems"?<ProblemsPage adminKey={key}/>:section==="problem"?<ProblemDetailPage adminKey={key}/>:section==="ideas"?<IdeasPage adminKey={key}/>:section==="idea"?<IdeaDetailPage adminKey={key}/>:section==="signals"?<SignalsPage adminKey={key}/>:section==="sectors"?<SectorsPage adminKey={key}/>:<main className="page admin-page">{section==="review"?<ReviewQueue adminKey={key}/>:section==="catalog"?<CatalogReview adminKey={key}/>:<SourceYield adminKey={key}/>}</main>}</>;
}
