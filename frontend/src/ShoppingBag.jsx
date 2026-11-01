import { useEffect, useRef, useState } from 'react'
import { controlRequest } from './control/api'
import { priceText } from './catalogPricing'

function Money({amount,currency,labels}) {return priceText({discounted_price:amount,currency},labels)}

function BagItem({item,labels:l,busy,onUpdate}) {
  const [quantity,setQuantity]=useState(item.quantity)
  return <li className="bag-item">{item.image_url&&<img src={item.image_url} alt={item.product_name} />}<div><h3>{item.product_name}</h3>{item.variant_name&&<p>{item.variant_name}</p>}<p><Money amount={item.unit_price} currency={item.currency} labels={l} /></p><p className={item.expired?'control-error':'control-muted'}>{item.expired?l.reservation_expired:`${l.reservation_until} ${new Date(item.expires_at).toLocaleTimeString(l.currency_locale)}`}</p><label>{l.quantity}<input type="number" min="1" max="999" value={quantity} onChange={(event)=>setQuantity(event.target.value)} disabled={busy} /></label><div className="bag-item-actions"><button type="button" className="control-button" disabled={busy||!quantity} onClick={()=>onUpdate(item,Number(quantity))}>{l.update_quantity}</button><button type="button" className="control-button" disabled={busy} onClick={()=>onUpdate(item,0)}>{l.remove}</button></div></div></li>
}

function OrderSummary({order,labels:l}) {
  return <section className="bag-order"><p>{l.order_number}: <strong>{order.reference}</strong></p><p>{l.order_status}: {l[`shop_${order.status}`]}</p><p>{l[order.payment_status]}</p>{order.simulated&&<p className="bag-advance-status">{l.dummy_payment_completed}</p>}<p>{l.received}: <Money amount={order.received} currency={order.currency} labels={l}/></p>{order.advance_pending&&<p className="bag-advance-status">{l.advance_pending}: {order.advance_reference}<br/>{l.advance_pending_help}</p>}<p>{l.amount_due}: <Money amount={order.amount_due} currency={order.currency} labels={l}/></p>{Number(order.refund_due)>0&&<p>{l.refund_due}: <Money amount={order.refund_due} currency={order.currency} labels={l}/></p>}<ul>{order.items.map((item,index)=><li key={index}>{item.product_name} {item.variant_name} × {item.quantity}</li>)}</ul><p>{l.total}: <Money amount={order.total} currency={order.currency} labels={l} /></p><a className="control-button" href={`/invoice/${order.id}/`} target="_blank" rel="noreferrer">{l.invoice} ↗</a></section>
}

export default function ShoppingBag({shop,labels:l,onChanged,onClose}) {
  const [cancelPending,setCancelPending]=useState(false)
  const [view,setView]=useState('bag')
  const checkoutPanel=useRef(null)
  const [paymentChoice,setPaymentChoice]=useState('cod')
  const [checkout,setCheckout]=useState(false)
  const [key,setKey]=useState(()=>crypto.randomUUID())
  const [order,setOrder]=useState(null)
  const [orders,setOrders]=useState(null)
  const [fields,setFields]=useState({})
  const {cart,busy,error,refresh,mutate,setError}=shop
  useEffect(()=>{
    const update=()=>{if(document.visibilityState==='visible')refresh().catch((failure)=>setError(failure.message))}
    const timer=setInterval(update,15000)
    document.addEventListener('visibilitychange',update)
    return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',update)}
  },[refresh,setError])
  useEffect(()=>{if(checkout){checkoutPanel.current?.querySelector('input')?.focus({preventScroll:true});checkoutPanel.current?.scrollIntoView({block:'start',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})}},[checkout])
  const update=async(item,quantity)=>{
    try {await mutate('cart/items/',{product_id:item.product_id,variant_id:item.variant_id,quantity});onChanged()}
    catch {await refresh().catch(()=>{})}
  }
  const submit=async(event)=>{
    event.preventDefault();setFields({})
    const values=Object.fromEntries(new FormData(event.currentTarget));values.checkout_key=key;values.quote=cart.quote;values.delivery_zone=cart.delivery_zone
    try {const result=await mutate('checkout/',values);setOrder(result.order);setView('confirmation');setCheckout(false);setOrders(null);setKey(crypto.randomUUID());onChanged()}
    catch(failure){setFields(failure.fields||{});await refresh().catch(()=>{})}
  }
  const history=async()=>{
    try {const data=await controlRequest('/api/shop/orders/');setOrders(data.orders);setCancelPending(false);setView('history')}
    catch(failure){setError(failure.message)}
  }
  const cancel=async(id)=>{
    try {const result=await mutate(`orders/${id}/cancel/`,{});setOrder(result.order);setCancelPending(false);setOrders((current)=>current?.map((entry)=>entry.id===id?result.order:entry));onChanged()}
    catch { /* The shared error is rendered below. */ }
  }
  if(!cart)return <div><p role={error?'alert':'status'}>{error||l.cart_loading}</p>{error&&<button className="control-button" onClick={()=>refresh().catch((failure)=>setError(failure.message))}>{l.retry}</button>}</div>
  return <div className="bag-content"><p className="eyebrow">{l.cart}</p><h2>{view==='history'?l.order_history:view==='detail'?l.order_details:view==='confirmation'?l.order_success:l.cart}</h2>
    {error&&<p className="control-error" role="alert">{error}</p>}
    {!cart.authenticated?<><p>{l.cart_sign_in}</p><a href="/login/?next=bag" className="button button-primary">{l.nav_login}</a></>:<>
      {(view==='confirmation'||view==='detail')&&order&&<OrderSummary order={order} labels={l} />}
      {view==='detail'&&order?.status==='placed'&&<button type="button" className="control-button" disabled={busy} onClick={()=>setCancelPending(true)}>{l.cancel_order}</button>}
      {view==='detail'&&order?.status==='placed'&&cancelPending&&<section className="bag-order" role="group" aria-label={l.order_cancel_confirm}><p>{l.order_cancel_confirm}</p><div className="bag-footer-actions"><button type="button" className="control-button" disabled={busy} onClick={()=>setCancelPending(false)}>{l.keep_order}</button><button type="button" className="control-button" disabled={busy} onClick={()=>cancel(order.id)}>{l.confirm_cancel_order}</button></div></section>}
      {view==='bag'&&<>
      {cart.items.length>0?<><p className="control-muted">{l.reservation_note}</p><ul className="bag-items">{cart.items.map((item)=><BagItem key={`${item.id}-${item.quantity}-${item.expires_at}`} item={item} labels={l} busy={busy} onUpdate={update} />)}</ul><label className="bag-delivery-field">{l.delivery_zone}<select value={cart.delivery_zone||'inside'} disabled={busy} onChange={(event)=>mutate('delivery/',{delivery_zone:event.target.value}).catch(()=>{})}>{['inside','outside'].map((zone)=><option key={zone} value={zone}>{l[`delivery_${zone}`]}</option>)}</select></label><dl className="bag-totals">{[['subtotal',cart.subtotal],['shipping',cart.shipping_fee],['total',cart.total]].map(([label,amount])=><div key={label}><dt>{l[label]}</dt><dd><Money amount={amount} currency={cart.currency} labels={l} /></dd></div>)}</dl>
      {!checkout?<button className="button button-primary" disabled={busy||(!cart.cod_enabled&&!cart.advance_enabled&&!cart.pay_now_enabled)||cart.items.some((item)=>item.expired)} onClick={()=>{setPaymentChoice(cart.cod_enabled?'cod':'delivery_advance');setCheckout(true)}}>{l.checkout}</button>:<form ref={checkoutPanel} className="bag-checkout" onSubmit={submit}><h3>{l.checkout_details}</h3>{[['customer_name','customer_name','text'],['email','customer_email','email'],['phone','customer_phone','tel'],['address','customer_address','text'],['area','customer_area','text'],['city','customer_city','text'],['postal_code','customer_postal','text'],['notes','customer_notes','text']].map(([name,label,type])=><label className={['address','notes'].includes(name)?'bag-wide':undefined} key={name}>{l[label]}<input name={name} type={type} required={!['email','postal_code','notes'].includes(name)} maxLength={name==='address'||name==='notes'?1000:name==='phone'?40:name==='postal_code'?30:name==='city'?120:name==='email'?254:150} autoComplete={{customer_name:'name',email:'email',phone:'tel',address:'street-address',city:'address-level2',postal_code:'postal-code'}[name]} />{fields[name]?.map((message)=><span className="control-error" key={message}>{message}</span>)}</label>)}<fieldset className="bag-payment-options"><legend>{l.payment_choice}</legend><label className="bag-payment-option"><input type="radio" name="payment_method" value="cod" checked={paymentChoice==='cod'} disabled={busy||!cart.cod_enabled} onChange={()=>setPaymentChoice('cod')}/><span><strong>{l.cod}</strong><span>{l.cod_help}</span></span></label><label className="bag-payment-option"><input type="radio" name="payment_method" value="delivery_advance" checked={paymentChoice==='delivery_advance'} disabled={busy||!cart.advance_enabled||Number(cart.shipping_fee)<=0} onChange={()=>setPaymentChoice('delivery_advance')}/><span><strong>{l.pay_delivery_now}</strong><span>{cart.advance_enabled?l.pay_delivery_help:l.advance_unavailable}</span></span></label><label className="bag-payment-option"><input type="radio" name="payment_method" value="pay_now" checked={paymentChoice==='pay_now'} disabled={busy||!cart.pay_now_enabled} onChange={()=>setPaymentChoice('pay_now')}/><span><strong>{l.pay_now}</strong><span>{cart.pay_now_enabled?l.pay_now_help:l.pay_now_unavailable}</span></span></label></fieldset>{cart.dummy_enabled&&paymentChoice!=='cod'&&<section className="bag-advance bag-wide"><h4>{l.dummy_payment_title}</h4><p>{l.dummy_payment_help}</p><dl className="bag-totals"><div><dt>{l.pay_today}</dt><dd><Money amount={paymentChoice==='pay_now'?cart.total:cart.shipping_fee} currency={cart.currency} labels={l}/></dd></div><div><dt>{l.remaining_delivery}</dt><dd><Money amount={paymentChoice==='pay_now'?0:cart.subtotal} currency={cart.currency} labels={l}/></dd></div></dl></section>}{!cart.dummy_enabled&&paymentChoice==='delivery_advance'&&<section className="bag-advance bag-wide"><h4>{l.advance_instructions}</h4><p className="bag-transfer-instructions">{cart.advance_instructions}</p><dl className="bag-totals"><div><dt>{l.advance_due_now}</dt><dd><Money amount={cart.shipping_fee} currency={cart.currency} labels={l}/></dd></div><div><dt>{l.advance_remaining}</dt><dd><Money amount={cart.subtotal} currency={cart.currency} labels={l}/></dd></div></dl><label>{l.payment_method}<select name="advance_channel" required disabled={busy}>{cart.advance_methods.map((method)=><option key={method} value={method}>{l[`method_${method}`]}</option>)}</select></label><label>{l.advance_reference}<input name="advance_reference" required maxLength={150} disabled={busy}/></label><p>{l.advance_checkout_help}</p></section>}<button className="button button-primary" disabled={busy||cart.items.some((item)=>item.expired)}>{busy?l.placing_order:cart.dummy_enabled&&paymentChoice!=='cod'?l.dummy_payment_submit:l.place_order}</button></form>}</>:<p>{l.cart_empty}</p>}
      </>}
      {view==='history'&&<section className="bag-history">{orders?.length===0&&<p>{l.orders_empty}</p>}{orders?.map((entry)=><article className="bag-order" key={entry.id}><p>{l.order_number}: <strong>{entry.reference}</strong></p><p>{l.order_status}: {l[`shop_${entry.status}`]}</p>{entry.simulated&&<p>{l.dummy_payment_completed}</p>}<p>{l.total}: <Money amount={entry.total} currency={entry.currency} labels={l} /></p><button type="button" className="control-button" onClick={()=>{setOrder(entry);setCancelPending(false);setView('detail')}}>{l.view_order}</button></article>)}</section>}
      <div className="bag-footer-actions"><button className="control-button" type="button" onClick={onClose}>{l.continue_shopping}</button>{view!=='history'&&<button className="control-button" type="button" onClick={history}>{view==='detail'?l.back_to_orders:l.order_history}</button>}{(view==='history'||view==='detail')&&<button className="control-button" type="button" onClick={()=>setView('bag')}>{l.cart}</button>}</div>
    </>}
  </div>
}
