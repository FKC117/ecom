import {useEffect, useState} from 'react'
import {controlRequest} from './api'

export default function CourierPanel({order, labels:l}) {
  const [data,setData]=useState(null)
  const [error,setError]=useState(null)
  const [busy,setBusy]=useState(false)
  const [account,setAccount]=useState('')
  const [confirm,setConfirm]=useState(null)
  const [lookup,setLookup]=useState(null)
  const [kind,setKind]=useState('stores')
  const [parent,setParent]=useState('')
  const base=`operations/orders/${order.id}/courier/`
  useEffect(()=>{
    const controller=new AbortController()
    controlRequest(base,{signal:controller.signal}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e)})
    return()=>controller.abort()
  },[base])
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
  async function loadLookup(){
    setBusy(true);setError(null)
    try{setLookup(await controlRequest(`couriers/${account}/${kind}/?parent=${encodeURIComponent(parent)}`))}
    catch(e){setError(e)}finally{setBusy(false)}
  }
  return <section className="control-form-section courier-panel"><h2>{l.courier_title}</h2><p className="control-muted">{l.courier_help}</p>
    {error&&<div className="control-error" role="alert">{error.message}{Object.values(error.fields||{}).flat().map((message,i)=><p key={i}>{message}</p>)}</div>}
    {!data&&!error&&<p role="status">{l.loading}</p>}
    {data&&<>{data.rows.length===0&&<p>{l.courier_empty}</p>}{data.rows.map(row=><article className="ops-order-block" key={row.id}><h3>{row.account} · {row.state_label}</h3><p>{row.courier_status}</p><p>{l.courier_merchant_reference}: {row.merchant_order_id}</p><p>{l.courier_consignment}: {row.consignment_id||l.blank}</p><p>{l.courier_amount}: {row.amount_to_collect} · {l.courier_fee}: {row.delivery_fee??l.blank}</p>{row.last_error&&<p role="status">{row.last_error}</p>}{data.can_refresh&&<form className="ops-form" onSubmit={event=>refresh(event,row)}>{row.can_reconcile&&<label>{l.courier_consignment}<input name="consignment_id" maxLength={100} required disabled={busy}/></label>}<button className="control-button" disabled={busy||(!row.can_reconcile&&!row.consignment_id)}>{l.courier_refresh}</button></form>}</article>)}
    {data.can_book&&<>{data.accounts.length===0?<p>{l.courier_no_accounts}</p>:<>
      <form className="ops-form" onSubmit={event=>{event.preventDefault();const body=new FormData(event.currentTarget);body.set('expected_version',order.revision);setConfirm(body)}}><div className="control-field-grid">
        <label>{l.courier_account} *<select name="account" required value={account} onChange={e=>{setAccount(e.target.value);setLookup(null);setConfirm(null)}} disabled={busy}><option value="">{l.blank}</option>{data.accounts.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        {data.fields.map(field=><label key={field.name}>{field.label}{field.required?' *':''}{field.choices.length?<select name={field.name} required={field.required} disabled={busy}>{field.choices.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>:<input name={field.name} type={field.type} min={field.min??undefined} max={field.max??undefined} step={field.step} maxLength={field.max_length??undefined} defaultValue={field.name==='item_weight'?'0.5':field.name==='item_quantity'?'1':undefined} required={field.required} disabled={busy}/>}</label>)}
      </div><p>{l.courier_amount}: {order.amount_due}</p><button className="control-button primary" disabled={busy||!account}>{l.courier_book}</button></form>
      {confirm&&<div className="ops-status-confirm"><p>{l.courier_confirm_help}</p><p>{data.accounts.find(row=>String(row.id)===confirm.get('account'))?.name} · {l.courier_amount}: {order.amount_due}</p><div className="control-toolbar"><button className="control-button primary" disabled={busy} onClick={book}>{busy?l.loading:l.courier_confirm}</button><button className="control-button" disabled={busy} onClick={()=>setConfirm(null)}>{l.cancel}</button></div></div>}
      <details><summary>{l.courier_lookup}</summary><div className="ops-form"><label>{l.courier_lookup}<select value={kind} onChange={e=>{setKind(e.target.value);setLookup(null)}}>{['stores','cities','zones','areas'].map(value=><option key={value} value={value}>{l[`courier_${value}`]}</option>)}</select></label>{['zones','areas'].includes(kind)&&<label>{data.fields.find(field=>field.name===(kind==='zones'?'recipient_city':'recipient_zone'))?.label}<input type="number" min="1" value={parent} onChange={e=>setParent(e.target.value)}/></label>}<button className="control-button" disabled={busy||!account} onClick={loadLookup}>{l.courier_lookup}</button>{lookup&&<pre className="courier-lookup">{JSON.stringify(lookup.data,null,2)}</pre>}</div></details>
    </>}</>}
    </>}
  </section>
}
