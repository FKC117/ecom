import {useState} from 'react'
import {controlRequest} from './api'

export default function OrderReviewPanel({order,labels:l,onSaved,setDirty}) {
  const [decision,setDecision]=useState('approved')
  const [reason,setReason]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const review=order.review
  if(!review)return null
  async function submit(event){
    event.preventDefault();setBusy(true);setError('')
    const body=new FormData();body.set('expected',review.status);body.set('decision',decision);body.set('reason',reason)
    try{await controlRequest(`operations/orders/${order.id}/review/`,{method:'POST',body});setReason('');setDirty(false);onSaved()}
    catch(failure){setError([failure.message,...Object.values(failure.fields||{}).flat()].join(' '))}finally{setBusy(false)}
  }
  return <section className={`control-form-section order-review-panel ${review.status==='pending'?'needs-review':''}`}>
    <header className="ops-order-heading"><h2>{l.review_title}</h2><span className="ops-status-badge">{l[`review_${review.status}`]}</span></header>
    <p className="control-muted">{l.review_help}</p>
    {review.reasons.length>0&&<ul>{review.reasons.map((code)=><li key={code}>{l[`review_${code}`]}</li>)}</ul>}
    {error&&<p className="control-error" role="alert">{error}</p>}
    {review.can_review&&<form className="order-review-form" onSubmit={submit} onChange={()=>setDirty(true)}>
      <label>{l.review_decision}<select value={decision} disabled={busy} onChange={(event)=>setDecision(event.target.value)}><option value="approved">{l.review_approve}</option><option value="rejected">{l.review_reject}</option></select></label>
      <label>{l.review_reason}<input value={reason} onChange={(event)=>setReason(event.target.value)} required maxLength={500} disabled={busy}/></label>
      <button className="control-button primary" disabled={busy}>{busy?l.loading:l.review_save}</button>
    </form>}
    {review.history.length>0&&<div><h3>{l.review_history}</h3>{review.history.map((row,index)=><article className="ops-movement" key={index}><strong>{l[`review_${row.decision}`]}</strong><p>{row.reason}</p><small>{row.actor} · {new Date(row.created_at).toLocaleString()}</small></article>)}</div>}
  </section>
}
