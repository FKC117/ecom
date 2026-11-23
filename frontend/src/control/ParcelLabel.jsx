import {useEffect,useState} from 'react'
import {controlRequest} from './api'
import {applyBranding} from '../branding'

export default function ParcelLabel(){
  const [data,setData]=useState(null)
  const [error,setError]=useState('')
  useEffect(()=>{const id=window.location.pathname.split('/').filter(Boolean)[1];controlRequest(`parcel-label/${encodeURIComponent(id)}/`).then(result=>{applyBranding(result.site);document.documentElement.dataset.palette=result.site.palette;document.documentElement.dataset.mode='light';setData(result)}).catch(e=>setError(e.message))},[])
  if(!data)return <main className="invoice-page"><p role="status">{error}</p></main>
  const {shipment:s,site,labels:l}=data
  return <main className="parcel-label-page"><div className="invoice-toolbar"><button className="control-button" onClick={()=>window.print()}>{l.packaging_label}</button></div><article className="parcel-label-sheet">
    {s.environment==='sandbox'&&<h2 className="parcel-label-test">{l.packaging_sandbox}</h2>}
    <header><h1>{site.site_name}</h1><p>{l.packaging_label_title}</p><p>{s.account}</p></header>
    <section><h2>{l.courier_consignment}</h2><strong className="parcel-label-tracking">{s.consignment_id}</strong><p>{l.ops_reference}: {s.reference}</p></section>
    <section><h2>{l.packaging_recipient}</h2><strong>{s.recipient_name}</strong><p>{s.recipient_phone}</p><p>{s.recipient_address}</p></section>
    <section><strong>{l.courier_amount}: {s.amount_to_collect}</strong><p>{l.packaging_weight}: {s.item_weight} · {l.packaging_parcels}: {s.item_quantity}</p>{s.special_instruction&&<p>{s.special_instruction}</p>}</section>
    <footer><h2>{l.packaging_sender}</h2><p>{site.invoice_address}</p><p>{site.invoice_phone}</p><small>{l.packaging_label_note}</small></footer>
  </article></main>
}
