import {useEffect,useMemo,useState} from 'react'
import {controlRequest} from './api'
import {applyBranding} from '../branding'
import {consignmentCodes} from './parcelCodes'

function Barcode({codes,value,label}){
  return <svg className="parcel-barcode" role="img" aria-label={`${label}: ${value}`} viewBox={`0 0 ${codes.barcodeWidth} 60`} preserveAspectRatio="none"><title>{value}</title><path d={codes.barcodePath}/></svg>
}

export function ParcelLabelSheet({data,format,codes}){
  const {shipment:s,site,labels:l,sender}=data
  const money=new Intl.NumberFormat(undefined,{style:'currency',currency:s.currency||'BDT'}).format(Number(s.amount_to_collect||0))
  const large=format==='large'
  return <article className={`parcel-label-sheet parcel-label-${format}`}>
    {s.environment==='sandbox'&&<div className="parcel-label-test">{l.packaging_sandbox}</div>}
    <header className="parcel-label-header">
      {site.logo&&<img className="parcel-label-logo" src={site.logo} alt={site.logo_alt||site.site_name}/>}
      <div className="parcel-label-merchant"><h1>{sender.name}</h1>{sender.address&&<p>{sender.address}</p>}{sender.phone&&<p>{l.parcel_contact}: {sender.phone}</p>}<p className="parcel-label-courier">{s.account}</p></div>
    </header>
    {!large&&<><Barcode codes={codes} value={s.consignment_id} label={l.courier_consignment}/><div className="parcel-label-id">{s.consignment_id}</div></>}
    <section className="parcel-label-recipient">
      <div><p className="parcel-label-kicker">{l.parcel_to}</p><h2>{s.recipient_name}</h2><p className="parcel-label-phone">{s.recipient_phone}{s.recipient_secondary_phone&&<> · {s.recipient_secondary_phone}</>}</p><p className="parcel-label-address">{s.recipient_address}</p></div>
      {large&&<svg className="parcel-qr" viewBox={`0 0 ${codes.qrSize} ${codes.qrSize}`} role="img" aria-label={`${l.courier_consignment}: ${s.consignment_id}`}><title>{s.consignment_id}</title><path d={codes.qrPath}/></svg>}
    </section>
    <div className="parcel-label-details">
      <section className="parcel-label-summary"><p className="parcel-label-cod"><span>{l.parcel_cod}</span><strong>{money}</strong></p><p><span>{l.ops_reference}</span><strong>{s.reference}</strong></p><p><span>{l.parcel_weight}</span><strong>{Number(s.item_weight||0).toFixed(2)}</strong><span>{l.parcel_count}</span><strong>{s.item_quantity}</strong></p>
        {large&&<><p><span>{l.parcel_order_date}</span><strong>{new Date(s.created_at).toLocaleString()}</strong></p>{s.delivery_service&&<p><span>{l.parcel_service}</span><strong>{s.delivery_service}</strong></p>}{s.special_instruction&&<p className="parcel-label-instructions"><span>{l.parcel_instructions}</span>{s.special_instruction}</p>}</>}
      </section>
      {large&&<section className="parcel-label-routing"><Barcode codes={codes} value={s.consignment_id} label={l.courier_consignment}/><div className="parcel-label-id">{s.consignment_id}</div><dl>{[['city','parcel_city'],['zone','parcel_zone'],['area','parcel_area']].filter(([field])=>s[field]).map(([field,label])=><div key={field}><dt>{l[label]}</dt><dd>{s[field]}</dd></div>)}</dl></section>}
    </div>
  </article>
}

export default function ParcelLabel(){
  const [data,setData]=useState(null)
  const [error,setError]=useState('')
  const [format,setFormat]=useState(()=>{const value=new URLSearchParams(window.location.search).get('format');return ['small','sticker','large'].includes(value)?value:'small'})
  const [printing,setPrinting]=useState(false)
  useEffect(()=>{const controller=new AbortController();const id=window.location.pathname.split('/').filter(Boolean)[1];controlRequest(`parcel-label/${encodeURIComponent(id)}/`,{signal:controller.signal}).then(result=>{applyBranding(result.site);document.documentElement.dataset.palette=result.site.palette;document.documentElement.dataset.mode='light';setData(result)}).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>controller.abort()},[])
  const codes=useMemo(()=>{if(!data)return null;try{return consignmentCodes(data.shipment.consignment_id)}catch{return null}},[data])
  async function print(){
    setPrinting(true)
    try{
      await document.fonts.ready;await Promise.all([...document.querySelectorAll('.parcel-label-sheet img')].map(img=>img.decode().catch(()=>{})))
      const sheet=document.querySelector('.parcel-label-sheet')
      if(format==='sticker'&&sheet.scrollHeight>sheet.clientHeight+2){setError(data.labels.parcel_sticker_overflow);return}
      setError('');window.print()
    }finally{setPrinting(false)}
  }
  function changeFormat(value){setFormat(value);setError('');const url=new URL(window.location.href);url.searchParams.set('format',value);window.history.replaceState(null,'',url)}
  if(!data)return <main className="invoice-page"><p role="status">{error}</p></main>
  const l=data.labels
  return <main className={`parcel-label-page parcel-format-${format}`}><div className="parcel-label-toolbar"><label>{l.parcel_format}<select value={format} onChange={event=>changeFormat(event.target.value)}>{data.formats.map(option=><option key={option.key} value={option.key}>{option.label}</option>)}</select></label><button className="control-button primary" disabled={!codes||printing} onClick={print}>{printing?l.loading:l.packaging_label}</button><p>{l.parcel_print_hint}</p>{error&&<p className="control-error" role="alert">{error}</p>}</div>{!codes?<p className="control-error" role="alert">{l.parcel_barcode_error}</p>:<ParcelLabelSheet data={data} format={format} codes={codes}/>}</main>
}
