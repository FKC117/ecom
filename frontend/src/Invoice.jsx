import { useEffect, useState } from 'react'
import { applyBranding } from './branding'
import { controlRequest } from './control/api'

export default function Invoice() {
  const [data,setData]=useState(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    const controller=new AbortController()
    const id=window.location.pathname.split('/').filter(Boolean)[1]
    controlRequest(`/api/shop/orders/${encodeURIComponent(id)}/invoice/`,{signal:controller.signal}).then((result)=>{applyBranding(result.site);document.documentElement.dataset.palette=result.site.palette;document.documentElement.dataset.mode='light';setData(result)}).catch((failure)=>{if(failure.name!=='AbortError')setError(failure.message)})
    return()=>controller.abort()
  },[])
  if(!data)return <main className="loading-screen">{error&&<p role="alert">{error}</p>}</main>
  const {order:o,site,labels:l}=data
  const amount=(value)=>new Intl.NumberFormat(l.currency_locale,{style:'currency',currency:o.currency}).format(Number(value))
  return <main className="invoice-page"><div className="invoice-toolbar"><a href="/">{l.continue_shopping}</a><button className="button button-primary" onClick={()=>window.print()}>{l.print_invoice}</button></div><article className="invoice-sheet">
    <header className="invoice-heading"><div>{site.logo?<img className="invoice-logo" src={site.logo} alt={site.logo_alt||site.site_name}/>:<h1>{site.site_name}</h1>}<p>{site.invoice_address}</p>{site.invoice_phone&&<p>{site.invoice_phone}</p>}{site.contact_email&&<p>{site.contact_email}</p>}</div><div><p className="eyebrow">{l.invoice}</p><h2>{o.invoice_reference}</h2><p>{l.order_number}: {o.reference}</p><p>{l.invoice_date}: {new Date(o.created_at).toLocaleDateString(l.currency_locale,{day:'2-digit',month:'short',year:'numeric'})}</p></div></header>
    {o.simulated&&<p className="invoice-banner">{l.dummy_payment_completed}</p>}
    {o.advance_pending&&<p className="invoice-banner">{l.advance_pending}: {o.advance_reference}</p>}
    {o.status==='cancelled'&&<p className="invoice-banner">{l.invoice_cancelled}</p>}
    <section className="invoice-parties"><div><h3>{l.bill_to}</h3><strong>{o.customer}</strong>{o.email&&<p>{o.email}</p>}{o.phone&&<p>{o.phone}</p>}{(o.address||o.area||o.city||o.postal_code)&&<p>{o.address}{o.address&&<br/>}{o.area}{o.area&&<br/>}{o.city} {o.postal_code}</p>}</div><div><h3>{l.order_status}</h3><p>{l[`shop_${o.status}`]}</p><h3>{l.payment_status}</h3><p><strong>{l[o.payment_status]}</strong></p>{Number(o.amount_due)>0&&<p>{l.cod}: {amount(o.amount_due)}</p>}<p>{l.delivery_zone}: {l[`delivery_${o.delivery_zone}`]}</p><p>{o.status==='cancelled'?l.invoice_cancelled:o.payment_status==='paid'?l.paid:`${l.amount_due}: ${amount(o.amount_due)}`}</p></div></section>
    <div className="invoice-table-wrap"><table className="invoice-table"><thead><tr><th>{l.invoice_item}</th><th>{l.quantity}</th><th>{l.regular_price}</th><th>{l.invoice_discount}</th><th>{l.total}</th></tr></thead><tbody>{o.items.map((item,index)=><tr key={index}><td><strong>{item.product_name}</strong>{item.variant_name&&<p>{item.variant_name}</p>}{item.sku&&<p>{l.invoice_sku}: {item.sku}</p>}</td><td>{item.quantity}</td><td>{amount(item.regular_price)}</td><td>{amount(item.discount_amount)}</td><td>{amount(item.line_total)}</td></tr>)}</tbody></table></div>
    <dl className="invoice-totals">{[[l.regular_price,o.regular_subtotal],[l.invoice_discount,o.discount_total],[l.subtotal,o.subtotal],[l.shipping,o.shipping_fee],[l.total,o.total],[l.received,o.received],[l.refunded,o.refunded],[l.amount_due,o.amount_due],[l.refund_due,o.refund_due]].map(([label,value],index)=><div key={index}><dt>{label}</dt><dd>{amount(value)}</dd></div>)}</dl>
    {o.payments?.length>0&&<section><h3>{l.payment_history}</h3><ul>{o.payments.map((row)=><li key={row.id}>{new Date(row.occurred_at).toLocaleDateString(l.currency_locale)} · {l[row.kind]} · {l[`method_${row.method}`]} · {amount(row.amount)}</li>)}</ul></section>}
    {site.invoice_note&&<footer className="invoice-footer">{site.invoice_note}</footer>}
  </article></main>
}
