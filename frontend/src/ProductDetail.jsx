import { useState } from 'react'
import ResponsiveImage from './ResponsiveImage'

import { priceText } from './catalogPricing'

export function Price({ item, labels, range = false }) {
  return <span className="catalog-price">{range && item.has_price_range && <span>{labels.from_price} </span>}{item.has_discount && <del aria-label={labels.regular_price}>{priceText(item, labels, 'regular_price')}</del>}<strong aria-label={labels.sale_price}>{priceText(item, labels)}</strong></span>
}

export default function ProductDetail({ product, collections, site, labels: l, onAdd }) {
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
  const tags = [...new Map([...(product.tags || []), ...(variant?.tags || [])].map((tag) => [tag.id, tag])).values()]
  const specifications = [['material', variant?.material || product.material], ['gemstone', variant?.gemstone || product.gemstone], ['size', variant?.size], ['color', variant?.color], ['sku', item.sku]].filter(([,value]) => value)
  return <div className="product-detail">
    <div className="catalog-gallery"><div className="detail-image">{image && <ResponsiveImage src={image.image} media={image.image_media} sizes="(max-width: 760px) 100vw, 50vw" alt={image.image_alt || product.name} />}</div>{gallery.length > 1 && <div className="catalog-thumbnails" role="group" aria-label={l.gallery}>{gallery.map((entry) => <button key={entry.id} type="button" aria-pressed={image?.id === entry.id} onClick={() => setGalleryId(entry.id)}><ResponsiveImage src={entry.image} media={entry.image_media} sizes="72px" alt={entry.image_alt || product.name} /></button>)}</div>}</div>
    <div className="detail-copy"><p className="eyebrow">{collections.find((entry) => entry.id === product.collection)?.name}</p><h2>{product.name}</h2><p className="detail-subtitle">{product.subtitle}</p>
      {variants.length > 0 && <label className="catalog-variant-select">{l.variants}<select value={variant?.id || ''} onChange={(event) => {setVariantId(Number(event.target.value));setGalleryId(null)}}>{variants.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {priceText(entry,l)} · {l[entry.availability]}</option>)}</select></label>}
      <p className="detail-price" aria-live="polite"><Price item={item} labels={l} /></p><p className={`catalog-availability ${item.availability === 'sold_out' ? 'is-sold-out' : ''}`} role="status">{l[item.availability]}</p>
      <form className="catalog-add" onSubmit={async(event)=>{event.preventDefault();setBusy(true);setError('');try{await onAdd(variant,Number(quantity))}catch(failure){setError(failure.message)}finally{setBusy(false)}}}><label>{l.quantity}<input type="number" min="1" max="999" step="1" value={quantity} onChange={(event)=>setQuantity(event.target.value)} required disabled={busy||!item.can_purchase} /></label><button className="button button-primary" aria-describedby={!item.can_purchase?`purchase-unavailable-${product.id}`:undefined} disabled={busy||!item.can_purchase}>{busy?l.adding_to_cart:l.add_to_cart}</button>{error&&<p className="control-error" role="alert">{error}</p>}</form>
      {!item.can_purchase&&<p id={`purchase-unavailable-${product.id}`} className="control-muted" role="status">{item.discounted_price===null?l.purchase_price_missing:item.track_stock===false?l.shop_stock_unconfigured:item.available_quantity===0?l.shop_insufficient_stock:l.shop_unavailable}</p>}
      {tags.length > 0 && <div className="catalog-tags">{tags.map((tag) => <span key={tag.id}>{tag.name}</span>)}</div>}
      <p className="detail-description">{product.description}</p>
      {(specifications.length > 0 || product.features?.length > 0) && <section className="catalog-features"><h3>{l.features}</h3><dl>{specifications.map(([key,value]) => <div key={key}><dt>{l[key]}</dt><dd>{value}</dd></div>)}{product.features?.map((feature) => <div key={feature.id}><dt>{feature.name}</dt><dd>{feature.value}</dd></div>)}</dl></section>}
      {product.care_instructions && <section className="catalog-care"><h3>{l.care}</h3><p>{product.care_instructions}</p></section>}
      {site.contact_email && <a className="button button-primary" href={`mailto:${site.contact_email}?subject=${encodeURIComponent([product.name, variant?.name].filter(Boolean).join(' / '))}`}>{l.piece_inquiry}<span aria-hidden="true">→</span></a>}
    </div>
  </div>
}
