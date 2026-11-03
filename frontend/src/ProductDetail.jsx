import { useEffect, useRef, useState } from 'react'
import ResponsiveImage from './ResponsiveImage'

import { priceText } from './catalogPricing'

export function Price({ item, labels, range = false }) {
  return <span className="catalog-price">{range && item.has_price_range && <span>{labels.from_price} </span>}{item.has_discount && <del aria-label={labels.regular_price}>{priceText(item, labels, 'regular_price')}</del>}<strong aria-label={labels.sale_price}>{priceText(item, labels)}</strong></span>
}

export default function ProductDetail({ product, categories, site, labels: l, onAdd, standalone=false }) {
  const zoom=useRef(null)
  const thumbnails=useRef(null)
  const touch=useRef(null)
  const swiped=useRef(false)
  const [zoomed,setZoomed]=useState(false)
  useEffect(()=>{if(zoomed&&!zoom.current.open)zoom.current.showModal();if(!zoomed&&zoom.current.open)zoom.current.close()},[zoomed])
  const [quantity,setQuantity]=useState(1)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const variants = product.variants || []
  const purchasable = variants.filter((item) => item.can_purchase)
  const available = purchasable.length ? purchasable : variants.filter((item) => item.availability !== 'sold_out')
  const options = available.length ? available : variants
  const lead = options.reduce((best, item) => !best || (item.discounted_price !== null && (best.discounted_price === null || Number(item.discounted_price) < Number(best.discounted_price))) ? item : best, null)
  const [variantId, setVariantId] = useState(lead?.id || null)
  const [galleryId, setGalleryId] = useState(null)
  const variant = variants.find((item) => item.id === variantId) || lead
  const item = variant || product
  const gallery = [{id:'main',image:product.image,image_media:product.image_media,image_alt:product.image_alt}, ...(product.gallery || [])].filter((image) => image.image)
  if (variant?.image) gallery.unshift({id:'variant',image:variant.image,image_media:variant.image_media,image_alt:variant.image_alt})
  const image = gallery.find((entry) => entry.id === galleryId) || gallery[0]
  const imageIndex=gallery.findIndex(entry=>entry.id===image?.id)
  const moveImage=direction=>{if(gallery.length>1)setGalleryId(gallery[(imageIndex+direction+gallery.length)%gallery.length].id)}
  const galleryKeys=event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();event.stopPropagation();moveImage(event.key==='ArrowLeft'?-1:1)}}
  const touchStart=event=>{touch.current={x:event.changedTouches[0].clientX,y:event.changedTouches[0].clientY};swiped.current=false}
  const touchEnd=event=>{if(!touch.current)return;const dx=event.changedTouches[0].clientX-touch.current.x;const dy=event.changedTouches[0].clientY-touch.current.y;if(Math.abs(dx)>40&&Math.abs(dx)>Math.abs(dy)){swiped.current=true;moveImage(dx<0?1:-1)}touch.current=null}
  useEffect(()=>{
    const strip=thumbnails.current
    const active=strip?.querySelector('[aria-pressed="true"]')
    if(galleryId===null||!active)return
    const left=active.getBoundingClientRect().left-strip.getBoundingClientRect().left+strip.scrollLeft
    if(left<strip.scrollLeft)strip.scrollTo({left,behavior:'smooth'})
    else if(left+active.offsetWidth>strip.scrollLeft+strip.clientWidth)strip.scrollTo({left:left+active.offsetWidth-strip.clientWidth,behavior:'smooth'})
  },[galleryId])
  const tags = [...new Map([...(product.tags || []), ...(variant?.tags || [])].map((tag) => [tag.id, tag])).values()]
  const specifications = item.details || []
  const customFeatures=(product.features||[]).filter(feature=>!specifications.some(row=>row.label.toLocaleLowerCase()===feature.name.toLocaleLowerCase()))
  const care=(variant?.care_instructions||product.care_instructions||'').trim()
  const Heading=standalone?'h1':'h2'
  return <div className="product-detail">
    <div className="catalog-gallery" role="group" aria-label={l.gallery} tabIndex={0} onKeyDown={galleryKeys}>
      <div className="detail-image gallery-stage" onTouchStart={touchStart} onTouchEnd={touchEnd} onTouchCancel={()=>{touch.current=null}}>
        {image && <button type="button" className="product-zoom-trigger" onClick={()=>{if(swiped.current){swiped.current=false;return}setZoomed(true)}} aria-label={l.product_zoom}><ResponsiveImage src={image.image} media={image.image_media} sizes="(max-width: 760px) 100vw, 50vw" alt={image.image_alt || product.name} fetchPriority={standalone?'high':undefined}/><span>{l.product_zoom}</span></button>}
        {gallery.length>1&&<><button type="button" className="gallery-arrow gallery-previous" aria-label={l.gallery_previous} onClick={()=>moveImage(-1)}>‹</button><button type="button" className="gallery-arrow gallery-next" aria-label={l.gallery_next} onClick={()=>moveImage(1)}>›</button><span className="gallery-counter" role="status" aria-live="polite">{imageIndex+1} / {gallery.length}</span></>}
      </div>
      {gallery.length > 1 && <div ref={thumbnails} className="catalog-thumbnails" role="group" aria-label={l.gallery}>{gallery.map((entry) => <button key={entry.id} type="button" aria-pressed={image?.id === entry.id} onClick={() => setGalleryId(entry.id)}><ResponsiveImage src={entry.image} media={entry.image_media} sizes="72px" alt={entry.image_alt || product.name} /></button>)}</div>}
    </div>
    <dialog ref={zoom} className="dialog product-zoom-dialog" aria-label={l.product_zoom} onKeyDown={galleryKeys} onCancel={()=>setZoomed(false)} onClose={()=>setZoomed(false)} onClick={event=>{if(event.target===zoom.current)setZoomed(false)}}><button className="icon-button dialog-close" onClick={()=>setZoomed(false)} aria-label={l.close_details}>×</button><div className="gallery-stage" onTouchStart={touchStart} onTouchEnd={touchEnd} onTouchCancel={()=>{touch.current=null}}>{image&&<img src={image.image} alt={image.image_alt||product.name}/>} {gallery.length>1&&<><button type="button" className="gallery-arrow gallery-previous" aria-label={l.gallery_previous} onClick={()=>moveImage(-1)}>‹</button><button type="button" className="gallery-arrow gallery-next" aria-label={l.gallery_next} onClick={()=>moveImage(1)}>›</button><span className="gallery-counter" role="status" aria-live="polite">{imageIndex+1} / {gallery.length}</span></>}</div></dialog>
    <div className="detail-copy"><p className="eyebrow">{categories.find((entry) => entry.id === product.category)?.name}</p><Heading>{product.name}</Heading><p className="detail-subtitle">{product.subtitle}</p>
      {variants.length > 0 && <label className="catalog-variant-select">{l.variants}<select value={variant?.id || ''} onChange={(event) => {setVariantId(Number(event.target.value));setGalleryId(null);setQuantity(1);setError('')}}>{variants.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {priceText(entry,l)} · {l[entry.availability]}</option>)}</select></label>}
      <p className="detail-price" aria-live="polite"><Price item={item} labels={l} /></p><p className={`catalog-availability ${item.availability === 'sold_out' ? 'is-sold-out' : ''}`} role="status">{l[item.availability]}</p>
      <form className="catalog-add" onSubmit={async(event)=>{event.preventDefault();setBusy(true);setError('');try{await onAdd(variant,Number(quantity))}catch(failure){setError(failure.message)}finally{setBusy(false)}}}><label>{l.quantity}<input type="number" min="1" max={item.available_quantity||1} step="1" value={quantity} onChange={(event)=>setQuantity(event.target.value)} required disabled={busy||!item.can_purchase} /></label><button className="button button-primary" aria-describedby={!item.can_purchase?`purchase-unavailable-${product.id}`:undefined} disabled={busy||!item.can_purchase}>{busy?l.adding_to_cart:l.add_to_cart}</button>{error&&<p className="control-error" role="alert">{error}</p>}</form>
      {!item.can_purchase&&<p id={`purchase-unavailable-${product.id}`} className="control-muted" role="status">{item.discounted_price===null?l.purchase_price_missing:item.track_stock===false?l.shop_stock_unconfigured:item.available_quantity===0?l.shop_insufficient_stock:l.shop_unavailable}</p>}
      {tags.length > 0 && <div className="catalog-tags">{tags.map((tag) => <span key={tag.id}>{tag.name}</span>)}</div>}
      <p className="detail-description">{product.description}</p>
      {(specifications.length > 0 || customFeatures.length > 0) && <section className="catalog-features"><h3>{l.features}</h3><dl>{specifications.map(({key,label,value}) => <div key={key}><dt>{label}</dt><dd>{value}</dd></div>)}{customFeatures.map((feature) => <div key={feature.id}><dt>{feature.name}</dt><dd>{feature.value}</dd></div>)}</dl></section>}
      {care && <section className="catalog-care"><h3>{l.care}</h3><p>{care}</p></section>}
      {site.contact_email && <a className="button button-primary" href={`mailto:${site.contact_email}?subject=${encodeURIComponent([product.name, variant?.name].filter(Boolean).join(' / '))}`}>{l.piece_inquiry}<span aria-hidden="true">→</span></a>}
    </div>
  </div>
}
