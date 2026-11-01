import PaymentPanel from './PaymentPanel'
import { useEffect, useRef, useState } from 'react'
import { controlRequest } from './api'

function money(amount,currency) {try{return new Intl.NumberFormat(undefined,{style:'currency',currency}).format(Number(amount))}catch{return `${currency} ${amount}`}}
function Errors({error}) {return error&&<div className="control-error" role="alert"><p>{error.message}</p>{Object.entries(error.fields||{}).map(([key,values])=><p key={key}>{values.join(' ')}</p>)}</div>}

function StockDialog({row,labels:l,onClose,onSaved,setDirty}) {
  const dialog=useRef(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState(null)
  useEffect(()=>{dialog.current.showModal();document.body.classList.add('modal-open');return()=>document.body.classList.remove('modal-open')},[])
  async function submit(event) {
    event.preventDefault();setBusy(true);setError(null)
    const body=new FormData(event.currentTarget);body.set('expected',row.on_hand)
    try{await controlRequest(`operations/stock/${row.model}/${row.id}/adjust/`,{method:'POST',body});setDirty(false);onSaved()}
    catch(failure){setError(failure)}finally{setBusy(false)}
  }
  return <dialog ref={dialog} className="dialog ops-dialog" aria-label={l.ops_adjust} onCancel={(event)=>{event.preventDefault();if(!busy)onClose()}}><button className="icon-button dialog-close" disabled={busy} onClick={onClose} aria-label={l.close}>×</button><h2>{l.ops_adjust}</h2><p>{row.name} {row.variant}</p><p>{l.ops_on_hand}: {row.on_hand} · {l.ops_reserved}: {row.reserved} · {l.ops_available}: {row.available}</p><Errors error={error}/><form className="ops-form" onSubmit={submit} onChange={()=>setDirty(true)}><label>{l.ops_delta}<input type="number" name="delta" required step="1" disabled={busy}/></label><label>{l.ops_reason}<textarea name="note" required maxLength={500} disabled={busy}/></label><div className="control-toolbar"><button type="button" className="control-button" disabled={busy} onClick={onClose}>{l.cancel}</button><button className="control-button primary" disabled={busy}>{busy?l.loading:l.save}</button></div></form></dialog>
}

export default function Operations({kind,canCreate,route,labels:l,navigate,setDirty,onAuthError,onRefresh}) {
  const [data,setData]=useState(null)
  const [error,setError]=useState(null)
  const [query,setQuery]=useState('')
  const [filter,setFilter]=useState('')
  const [term,setTerm]=useState('')
  const [page,setPage]=useState(1)
  const [revision,setRevision]=useState(0)
  const [adjust,setAdjust]=useState(null)
  const historyPanel=useRef(null)
  const [invoiceHistory,setInvoiceHistory]=useState(null)
  const [history,setHistory]=useState(null)
  const [pending,setPending]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{if(invoiceHistory){historyPanel.current?.focus({preventScroll:true});historyPanel.current?.scrollIntoView({block:'start'})}},[invoiceHistory])
  const id=route.split('/').filter(Boolean)[1]
  const endpoint=kind==='orders'&&id?`operations/orders/${encodeURIComponent(id)}/`:`operations/${kind}/?q=${encodeURIComponent(query)}&${kind==='orders'?'status':'state'}=${encodeURIComponent(filter)}&page=${page}`
  useEffect(()=>{
    const controller=new AbortController()
    controlRequest(endpoint,{signal:controller.signal}).then((result)=>{setData(result);setError(null)}).catch((failure)=>{if(failure.name!=='AbortError'){setError(failure);onAuthError(failure)}})
    return()=>controller.abort()
  },[endpoint,revision,onAuthError])
  useEffect(()=>{
    const update=()=>{if(document.visibilityState==='visible'&&!adjust&&!busy&&!pending)setRevision((value)=>value+1)}
    const timer=setInterval(update,15000)
    window.addEventListener('focus',update)
    return()=>{clearInterval(timer);window.removeEventListener('focus',update)}
  },[adjust,busy,pending])
  async function changeStatus() {
    setBusy(true);setError(null)
    const body=new FormData();body.set('status',pending)
    try{await controlRequest(`models/sanjilas/order/${encodeURIComponent(id)}/`,{method:'POST',body});setPending('');setRevision((value)=>value+1);onRefresh().catch(()=>{})}catch(failure){setError(failure);onAuthError(failure)}finally{setBusy(false)}
  }
  async function showHistory(row) {
    try{const result=await controlRequest(`operations/stock/${row.model}/${row.id}/movements/`);setHistory({...result,name:`${row.name} ${row.variant}`})}catch(failure){setError(failure)}
  }
  const statuses=Object.fromEntries(data?.statuses||[])
  const title=kind==='orders'?l.ops_orders:l.ops_stock
  return <>
    <div className="control-page-heading"><div><p className="eyebrow">{title}</p><h1>{id&&data?data.reference:title}</h1><p className="control-muted">{kind==='orders'?l.ops_orders_intro:l.ops_stock_intro}</p></div><div className="control-toolbar">{kind==='orders'&&!id&&canCreate&&<button className="control-button primary" onClick={()=>navigate('/operations.orders/new')}>{l.manual_title}</button>}<button className="control-button" onClick={()=>setRevision((value)=>value+1)}>{l.refresh}</button></div></div>
    <Errors error={error}/>{!data&&!error&&<p role="status">{l.loading}</p>}
    {data&&id&&kind==='orders'?<>
      <button className="control-back" onClick={()=>navigate('/operations.orders')}>← {l.back}</button>
      <section className="control-form-section ops-order-panel">
        <header className="ops-order-heading"><h2>{l.ops_order_details}</h2><div className="control-toolbar">{data.can_edit_invoice&&<button className="control-button" onClick={()=>navigate(`/operations.orders/${data.id}/edit`)}>{l.invoice_edit}</button>}{data.can_history&&<button className="control-button" onClick={async()=>{try{setInvoiceHistory(await controlRequest(`invoices/${data.id}/history/`))}catch(failure){setError(failure)}}}>{l.invoice_history}</button>}<a className="control-button" href={`/invoice/${data.id}/`} target="_blank" rel="noreferrer">{l.ops_invoice} ↗</a><span className="ops-status-badge">{statuses[data.status]}</span></div></header>
        <div className="ops-order-grid">
          <section className="ops-order-block"><h3>{l.ops_customer}</h3><strong>{data.customer}</strong><span>{data.email}</span><span>{data.phone}</span></section>
          <section className="ops-order-block"><h3>{l.ops_delivery}</h3><span className="ops-address">{data.address}</span><span>{data.area}</span><span>{data.city} {data.postal_code}</span></section>
          <section className="ops-order-block"><h3>{l.ops_when}</h3><span>{new Date(data.created_at).toLocaleString()}</span><span className="ops-payment">{l.ops_cod} · {l[data.payment_status]}</span><span>{l.delivery_zone}: {l[`delivery_${data.delivery_zone}`]}</span></section>
        </div>
        {data.notes&&<section className="ops-order-notes"><h3>{l.ops_notes}</h3><p>{data.notes}</p></section>}
        {data.actions.length>0&&<div className="ops-order-actions"><h3>{l.ops_action}</h3><div className="control-toolbar">{data.actions.map((status)=><button className={`control-button ${pending===status?'primary':status==='cancelled'?'danger-outline':''}`} key={status} disabled={busy} aria-pressed={pending===status} onClick={()=>setPending(status)}>{statuses[status]}</button>)}</div></div>}
        {pending&&<section className="ops-status-confirm" aria-label={l.ops_confirm}><div><span className="ops-status-badge">{statuses[pending]}</span><p>{l.ops_confirm_status}</p></div><div className="control-toolbar"><button className="control-button" disabled={busy} onClick={()=>setPending('')}>{l.cancel}</button><button className="control-button primary" disabled={busy} onClick={changeStatus}>{l.ops_confirm}</button></div></section>}
      </section>
      <PaymentPanel key={data.id} data={data} labels={l} onSaved={()=>{setRevision((value)=>value+1);setInvoiceHistory(null)}}/>
      <section className="control-form-section"><div className="control-table-wrap"><table className="control-table"><thead><tr><th>{l.ops_item}</th><th>{l.ops_sku}</th><th>{l.ops_quantity}</th><th>{l.manual_regular_price}</th><th>{l.manual_discount_total}</th><th>{l.invoice_net_unit}</th><th>{l.ops_total}</th></tr></thead><tbody>{data.items.map((item,index)=><tr key={index}><td data-label={l.ops_item}>{item.name}<br/>{item.variant}</td><td data-label={l.ops_sku}>{item.sku||l.blank}</td><td data-label={l.ops_quantity}>{item.quantity}</td><td data-label={l.manual_regular_price}>{money(item.regular_price,data.currency)}</td><td data-label={l.manual_discount_total}>{money(item.discount,data.currency)}</td><td data-label={l.invoice_net_unit}>{money(item.unit_price,data.currency)}</td><td data-label={l.ops_total}>{money(item.total,data.currency)}</td></tr>)}</tbody></table></div><dl className="bag-totals"><div><dt>{l.invoice_regular_subtotal}</dt><dd>{money(data.regular_subtotal,data.currency)}</dd></div><div><dt>{l.manual_discount_total}</dt><dd>{money(data.discount_total,data.currency)}</dd></div><div><dt>{l.ops_subtotal}</dt><dd>{money(data.subtotal,data.currency)}</dd></div><div><dt>{l.ops_shipping}</dt><dd>{money(data.shipping_fee,data.currency)}</dd></div><div><dt>{l.ops_total}</dt><dd>{money(data.total,data.currency)}</dd></div></dl></section>
    </>:data&&<>
      <div className="ops-metrics">{Object.entries(kind==='orders'?data.counts:data.summary).map(([key,value])=><div key={key}><span>{kind==='orders'?statuses[key]:l[`ops_${key}`]}</span><strong>{value}</strong></div>)}</div>
      <form className="ops-filters" onSubmit={(event)=>{event.preventDefault();setQuery(term);setPage(1)}}><label>{l.search}<input type="search" value={term} onChange={(event)=>setTerm(event.target.value)}/></label><label>{kind==='orders'?l.ops_status:l.ops_stock}<select value={filter} onChange={(event)=>{setFilter(event.target.value);setPage(1)}}><option value="">{l.ops_all}</option>{kind==='orders'?data.statuses.map(([key,label])=><option key={key} value={key}>{label}</option>):['low','untracked'].map((key)=><option key={key} value={key}>{l[`ops_${key}`]}</option>)}</select></label><button className="control-button">{l.search}</button></form>
      {kind==='stock'&&<p className="control-muted">{l.ops_low_help}: {data.threshold}</p>}
      <div className="ops-records">{data.rows.map((row)=><article className="control-form-section ops-record" key={kind==='orders'?row.id:`${row.model}-${row.id}`}><div><h2>{kind==='orders'?row.reference:row.name}</h2><p>{kind==='orders'?row.customer:row.variant}</p>{kind==='orders'&&row.simulated&&<p className="control-muted">{l.dummy_payment_title}</p>}{kind==='orders'&&row.source==='manual'&&<p className="control-muted">{l.manual_title}</p>}{kind==='stock'&&<p className="control-muted">{l.ops_sku}: {row.sku||l.blank}</p>}</div>{kind==='orders'?<><p>{statuses[row.status]} · {l[row.payment_status]} · {money(row.total,row.currency)}</p><p className="control-muted">{new Date(row.created_at).toLocaleString()}</p><button className="control-button" onClick={()=>navigate(`/operations.orders/${row.id}`)}>{l.view} →</button></>:<><div className="ops-stock-counts"><span>{l.ops_on_hand}: <strong>{row.on_hand}</strong></span><span>{l.ops_reserved}: <strong>{row.reserved}</strong></span><span>{l.ops_available}: <strong>{row.available}</strong></span></div>{!row.tracked&&<p>{l.ops_untracked}</p>}{row.tracked&&row.available<=data.threshold&&<p className="ops-low">{l.ops_low}</p>}<div className="control-toolbar">{row.can_change&&<button className="control-button" onClick={()=>setAdjust(row)}>{l.ops_adjust}</button>}{row.can_history&&<button className="control-button" onClick={()=>showHistory(row)}>{l.ops_movements}</button>}</div></>}</article>)}</div>
      {data.rows.length===0&&<p>{l.empty}</p>}<div className="control-pagination"><span>{l.page} {data.page} / {data.pages}</span><div><button className="control-button" disabled={page<=1} onClick={()=>setPage(page-1)}>{l.previous}</button><button className="control-button" disabled={page>=data.pages} onClick={()=>setPage(page+1)}>{l.next}</button></div></div>
      {history&&<section className="control-form-section"><h2>{l.ops_movements}: {history.name}</h2><button className="control-button" onClick={()=>setHistory(null)}>{l.close}</button>{history.rows.map((row,index)=><div className="ops-movement" key={index}><strong>{row.quantity>0?'+':''}{row.quantity} · {row.reason}</strong><p>{row.note}</p><p>{l.ops_actor}: {row.actor||l.blank} · {row.reference}</p><small>{new Date(row.created_at).toLocaleString()}</small></div>)}</section>}
    </>}
    {invoiceHistory&&<section ref={historyPanel} tabIndex={-1} className="control-form-section invoice-history-panel" aria-label={l.invoice_history}><h2>{l.invoice_history}: {invoiceHistory.reference}</h2><button className="control-button" onClick={()=>setInvoiceHistory(null)}>{l.close}</button>{invoiceHistory.rows.length===0&&<p>{l.empty}</p>}{invoiceHistory.rows.map((entry)=><article className="invoice-history-entry" key={entry.version}><h3>{l.invoice_version} {entry.version}</h3><p>{entry.actor||l.blank} · {new Date(entry.created_at).toLocaleString()}</p><p>{entry.reason}</p><div className="invoice-history-comparison">{['before','after'].map((side)=><section key={side}><h4>{l[`invoice_${side}`]}</h4><p>{entry[side].customer_name} · {entry[side].phone}</p><p>{entry[side].email}</p><p>{entry[side].address} {entry[side].area} {entry[side].city} {entry[side].postal_code}</p><p>{entry[side].notes}</p><p>{l.payment_status}: {l[entry[side].payment_status]||l.blank}</p><p>{l.delivery_zone}: {l[`delivery_${entry[side].delivery_zone}`]||l.blank}</p><p>{statuses[entry[side].status]||entry[side].status}</p><ul>{entry[side].items.map((item,index)=><li key={index}>{item.product_name} {item.variant_name} {item.sku} × {item.quantity} {item.discount_mode&&<>· {l.manual_discount_type}: {l[`manual_discount_${item.discount_mode}`]} {item.discount_mode==='percent'?`${item.discount_input}%`:money(item.discount_input,entry[side].currency)}</>} · {l.manual_regular_price}: {money(item.regular_price,entry[side].currency)} · {l.invoice_net_unit}: {money(item.unit_price,entry[side].currency)} · {l.ops_total}: {money(item.line_total,entry[side].currency)}</li>)}</ul><p>{l.ops_shipping}: {money(entry[side].shipping_fee,entry[side].currency)}</p><strong>{l.ops_total}: {money(entry[side].total,entry[side].currency)}</strong></section>)}</div></article>)}</section>}
    {adjust&&<StockDialog row={adjust} labels={l} setDirty={setDirty} onClose={()=>{setDirty(false);setAdjust(null)}} onSaved={()=>{setAdjust(null);setHistory(null);setRevision((value)=>value+1);onRefresh().catch(()=>{})}}/>}
  </>
}
