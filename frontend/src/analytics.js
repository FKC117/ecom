// Only catalog and order totals are sent; no contact details or commerce browser IDs.
let config = {}, initialized = false
const sent = new Set()
export function initializeAnalytics(site) {
  try { initializeProviders(site) } catch { /* Tracking must never prevent shopping. */ }
}
function initializeProviders(site) {
  config = site
  if (initialized) return
  initialized = true
  if (site.meta_pixel_enabled && /^\d+$/.test(site.meta_pixel_id || '')) {
    if (!window.fbq) {
      const fbq = function (...args) { if (fbq.callMethod) fbq.callMethod(...args); else fbq.queue.push(args) }
      fbq.queue = []; fbq.loaded = true; fbq.version = '2.0'
      window.fbq = fbq
      if (!window._fbq) window._fbq = fbq
      fbq.push = fbq
      const script = document.createElement('script'); script.async = true
      script.src = 'https://connect.facebook.net/en_US/fbevents.js'; document.head.appendChild(script)
    }
    window.fbq('set', 'autoConfig', false, site.meta_pixel_id)
    window.fbq('init', site.meta_pixel_id)
    window.fbq('trackSingle', site.meta_pixel_id, 'PageView')
  }
  if (site.google_analytics_enabled && /^G-[A-Z0-9]+$/.test(site.google_measurement_id || '')) {
    window.dataLayer = window.dataLayer || []
    window.gtag = function () { window.dataLayer.push(arguments) }
    window.gtag('js', new Date())
    window.gtag('config', site.google_measurement_id, {send_page_view: false})
    // Exclude query strings, which can contain customer-entered search terms.
    window.gtag('event', 'page_view', {page_location: location.origin + location.pathname})
    const script = document.createElement('script'); script.async = true
    script.src = `https://www.googletagmanager.com/gtag/js?id=${site.google_measurement_id}`
    document.head.appendChild(script)
  }
}

export function trackCommerce(metaName, googleName, rows, currency, value, key) {
  try { return sendCommerce(metaName, googleName, rows, currency, value, key) }
  catch { return false /* Tracking must never turn a successful order into a UI error. */ }
}
function sendCommerce(metaName, googleName, rows, currency, value, key) {
  if (!initialized || (key && sent.has(key))) return
  if (!(config.meta_pixel_enabled && window.fbq) && !(config.google_analytics_enabled && window.gtag)) return false
  if (key) sent.add(key)
  const items = rows.map(row => ({item_id: row.sku || String(row.variant_id || row.product_id), item_name: row.product_name, quantity: Number(row.quantity), price: Number(row.unit_price)}))
  if (config.meta_pixel_enabled && window.fbq) window.fbq('trackSingle', config.meta_pixel_id, metaName, {
    content_type: 'product', content_ids: items.map(item => item.item_id),
    contents: items.map(item => ({id: item.item_id, quantity: item.quantity, item_price: item.price})),
    num_items: items.reduce((sum, item) => sum + item.quantity, 0), currency, value: Number(value),
  }, key ? {eventID: key} : {})
  if (config.google_analytics_enabled && window.gtag) window.gtag('event', googleName, {
    currency, value: Number(value), items, ...(googleName === 'purchase' ? {transaction_id: key} : {}),
  })
  return true
}

export function trackPurchase(order) {
  if (order.simulated || order.status === 'cancelled') return
  const key = `purchase-${order.id}`
  try { if (localStorage.getItem(key)) return } catch { /* Memory deduplication remains available. */ }
  const queued = trackCommerce('Purchase', 'purchase', order.items, order.currency, order.total, key)
  if (queued) { try { localStorage.setItem(key, '1') } catch { /* Storage may be disabled. */ } }
}
