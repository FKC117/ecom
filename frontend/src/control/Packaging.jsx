import {useEffect, useState} from 'react'
import {controlRequest} from './api'
import CourierPanel from './CourierPanel'

export default function Packaging({route, labels:l, navigate, onAuthError}) {
  const id=route.split('/').filter(Boolean)[1]
  const step=route.split('/').filter(Boolean)[2]
  const [data,setData]=useState(null)
  const [error,setError]=useState(null)
  const [busy,setBusy]=useState(false)
  const [page,setPage]=useState(1)
  const endpoint=id?`operations/packaging/${id}/`:`operations/packaging/?page=${page}`
  useEffect(()=>{
    const controller=new AbortController()
    const load=()=>controlRequest(endpoint,{signal:controller.signal}).then(setData).catch(e=>{if(e.name!=='AbortError'){setError(e);onAuthError(e)}})
    load();const timer=setInterval(load,15000)
    return()=>{controller.abort();clearInterval(timer)}
  },[endpoint,onAuthError])
  async function pack(event){
    event.preventDefault();setBusy(true);setError(null)
    const body=new FormData(event.currentTarget);body.set('expected_version',data.order.revision)
    try{await controlRequest(`${endpoint}pack/`,{method:'POST',body});setData(await controlRequest(endpoint));navigate(`/operations.packaging/${id}/courier`)}
    catch(e){setError(e);onAuthError(e)}finally{setBusy(false)}
  }
  const showCourier=data&&id&&(data.state==='packed'||data.state==='handed_over')&&step!=='pack'
  return <><div className="control-page-heading"><div><p className="eyebrow">{l.packaging_title}</p><h1>{data?.order?.reference||l.packaging_title}</h1><p className="control-muted">{l.packaging_intro}</p></div><button className="control-button" onClick={async()=>{try{setData(await controlRequest(endpoint));setError(null)}catch(e){setError(e)}}}>{l.refresh}</button></div>
    {error&&<div className="control-error" role="alert">{error.message}{Object.values(error.fields||{}).flat().map((message,i)=><p key={i}>{message}</p>)}</div>}
    {!data&&!error&&<p role="status">{l.loading}</p>}
    {data&&id?<><button className="control-back" onClick={()=>navigate('/operations.packaging')}>← {l.packaging_back}</button>{!showCourier&&<section className="control-form-section"><h2>{data.state_label}</h2><p>{data.order.customer} · {data.order.phone}</p><p>{data.order.address}, {data.order.area}, {data.order.city}</p>{data.order.notes&&<p>{l.ops_notes}: {data.order.notes}</p>}<div className="control-table-wrap"><table className="control-table"><thead><tr><th>{l.ops_item}</th><th>{l.ops_sku}</th><th>{l.ops_quantity}</th></tr></thead><tbody>{data.items.map((item,i)=><tr key={i}><td data-label={l.ops_item}>{item.name} {item.variant}</td><td data-label={l.ops_sku}>{item.sku}</td><td data-label={l.ops_quantity}>{item.quantity}</td></tr>)}</tbody></table></div>
      {data.can_change&&data.can_pack&&data.state!=='handed_over'&&<form className="ops-form" onSubmit={pack}><div className="control-field-grid"><label>{l.packaging_weight} *<input type="number" name="item_weight" min="0.5" max="10" step="0.01" defaultValue={data.item_weight??'0.5'} required disabled={busy}/></label><label>{l.packaging_parcels} *<input type="number" name="item_quantity" min="1" max="100" step="1" defaultValue={data.item_quantity||1} required disabled={busy}/></label></div><label className="control-checkbox"><input type="checkbox" name="checked" required disabled={busy}/>{l.packaging_check}</label><button className="control-button primary" disabled={busy}>{busy?l.loading:l.packaging_packed}</button></form>}
      </section>}{showCourier&&<><section className="control-form-section"><h2>{l.courier_title}</h2><p>{data.state_label} · {l.packaging_weight}: {data.item_weight} · {l.packaging_parcels}: {data.item_quantity}</p><p>{data.order.customer} · {data.order.phone}</p>{data.can_change&&data.can_pack&&<button className="control-button" onClick={()=>navigate(`/operations.packaging/${id}/pack`)}>{l.edit} · {l.packaging_title}</button>}</section><CourierPanel order={data.order} packaging={data} labels={l} onChanged={async()=>setData(await controlRequest(endpoint))}/></>}</>:data&&<><section className="packaging-grid">{data.rows.map(row=><article key={row.id} className="control-form-section"><h2>{row.reference}</h2><p>{row.customer}</p><p>{row.state}</p><p>{new Date(row.queued_at).toLocaleString()}</p><button className="control-button primary" onClick={()=>navigate(`/operations.packaging/${row.order_id}`)}>{l.packaging_open}</button></article>)}</section>{!data.rows.length&&<p>{l.packaging_missing}</p>}<div className="control-pagination"><span>{l.page} {data.page} / {data.pages}</span><button className="control-button" disabled={page<=1} onClick={()=>setPage(page-1)}>{l.previous}</button><button className="control-button" disabled={page>=data.pages} onClick={()=>setPage(page+1)}>{l.next}</button></div></>}
  </>
}
