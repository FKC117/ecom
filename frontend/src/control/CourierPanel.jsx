import {useEffect, useState} from 'react'
import {controlRequest} from './api'
import CourierLocations from './CourierLocations'

export default function CourierPanel({order, labels:l, packaging=null, onChanged=()=>{}}) {
  const [data,setData]=useState(null)
  const [error,setError]=useState(null)
  const [busy,setBusy]=useState(false)
  const [account,setAccount]=useState('')
  const [locationsReady,setLocationsReady]=useState(false)
  const [confirm,setConfirm]=useState(null)
  const base=`operations/orders/${order.id}/courier/`
  useEffect(()=>{
    const controller=new AbortController()
    controlRequest(base,{signal:controller.signal}).then(result=>{setData(result);if(result.accounts.length===1)setAccount(String(result.accounts[0].id))}).catch(e=>{if(e.name!=='AbortError')setError(e)})
    return()=>controller.abort()
  },[base,order.revision])
  async function reload(){setData(await controlRequest(base))}
  async function book(){
    setBusy(true);setError(null)
    try{await controlRequest(`${base}book/`,{method:'POST',body:confirm});setConfirm(null)}
    catch(e){setError(e);setConfirm(null)}
    finally{try{await reload()}catch(e){setError(e)}setBusy(false)}
  }
  async function refresh(event,row){
    event.preventDefault();setBusy(true);setError(null)
    try{await controlRequest(`${base}${row.id}/refresh/`,{method:'POST',body:new FormData(event.currentTarget)});await reload()}
    catch(e){setError(e)}finally{setBusy(false)}
  }
  async function handover(row){
    if(!window.confirm(l.packaging_handover_confirm))return
    setBusy(true);setError(null)
    const body=new FormData();body.set('shipment',row.id)
    try{await controlRequest(`operations/packaging/${order.id}/handover/`,{method:'POST',body});await onChanged()}
    catch(e){setError(e)}finally{setBusy(false)}
  }
  return <section className="control-form-section courier-panel"><h2>{l.courier_title}</h2>
    {error&&<div className="control-error" role="alert">{error.message}{Object.values(error.fields||{}).flat().map((message,i)=><p key={i}>{message}</p>)}</div>}
    {!data&&!error&&<p role="status">{l.loading}</p>}
    {data&&<>{data.rows.length===0&&<p>{l.courier_empty}</p>}{data.rows.map(row=><article className="ops-order-block" key={row.id}><h3>{row.account} · {row.state_label}</h3><p>{row.courier_status}</p><p>{l.courier_merchant_reference}: {row.merchant_order_id}</p><p>{l.courier_consignment}: {row.consignment_id||l.blank}</p><p>{l.courier_amount}: {row.amount_to_collect} · {l.courier_fee}: {row.delivery_fee??l.blank}</p>{row.last_error&&<p role="status">{row.last_error}</p>}{data.can_refresh&&<form className="ops-form" onSubmit={event=>refresh(event,row)}>{row.can_reconcile&&<label>{l.courier_consignment}<input name="consignment_id" maxLength={100} required disabled={busy}/></label>}<button className="control-button" disabled={busy||(!row.can_reconcile&&!row.consignment_id)}>{l.courier_refresh}</button></form>}{packaging&&row.state==='booked'&&<div className="control-toolbar"><a className="control-button" href={`/parcel-label/${row.id}/`} target="_blank" rel="noreferrer">{l.packaging_label}</a>{packaging.can_change&&packaging.state==='packed'&&row.environment==='live'&&<button className="control-button primary" disabled={busy} onClick={()=>handover(row)}>{l.packaging_handover}</button>}</div>}</article>)}
    {packaging&&packaging.state==='waiting'&&<p>{l.packaging_wait}</p>}{data.can_book&&(!packaging||(packaging.state==='packed'&&!data.rows.some(row=>row.environment==='live'&&row.state!=='failed')))&&<>{data.accounts.length===0?<p>{l.courier_no_accounts}</p>:<>
      <form key={`${packaging?.state}-${packaging?.item_weight}-${packaging?.item_quantity}`} className="ops-form" onChange={()=>setConfirm(null)} onSubmit={event=>{event.preventDefault();const body=new FormData(event.currentTarget);if(!locationsReady)return;body.set('expected_version',order.revision);setConfirm(body)}}><div className="control-field-grid">
        <label>{l.courier_account} *<select name="account" required value={account} onChange={e=>{setLocationsReady(false);setAccount(e.target.value);setConfirm(null)}} disabled={busy}><option value="">{l.blank}</option>{data.accounts.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        {data.fields.filter(field=>!['recipient_city','recipient_zone','recipient_area'].includes(field.name)).map(field=><label key={field.name}>{field.label}{field.required?' *':''}{field.choices.length?<select name={field.name} required={field.required} disabled={busy}>{field.choices.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>:<input name={field.name} type={field.type} min={field.min??undefined} max={field.max??undefined} step={field.step} maxLength={field.max_length??undefined} readOnly={!!packaging&&['item_weight','item_quantity'].includes(field.name)} defaultValue={field.name==='item_weight'?(packaging?.item_weight||'0.5'):field.name==='item_quantity'?(packaging?.item_quantity||'1'):undefined} required={field.required} disabled={busy}/>}</label>)}
      <CourierLocations key={`${account}-${order.city}-${JSON.stringify(data.destinations?.[account]||{})}`} account={account} fields={data.fields} destination={data.destinations?.[account]||{}} order={order} labels={l} busy={busy} onReady={setLocationsReady}/></div><p>{l.courier_amount}: {order.amount_due}</p><button className="control-button primary" disabled={busy||!account||!locationsReady}>{l.courier_book}</button></form>
      {confirm&&<div className="ops-status-confirm"><p>{l.courier_confirm_help}</p><p>{data.accounts.find(row=>String(row.id)===confirm.get('account'))?.name} · {l.courier_amount}: {order.amount_due}</p><div className="control-toolbar"><button className="control-button primary" disabled={busy||!locationsReady} onClick={book}>{busy?l.loading:l.courier_confirm}</button><button className="control-button" disabled={busy} onClick={()=>setConfirm(null)}>{l.cancel}</button></div></div>}

    </>}</>}
    </>}
  </section>
}
