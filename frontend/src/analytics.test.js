import { test } from 'node:test'
import assert from 'node:assert/strict'

test('configured pixel sends catalog totals, deduplicates purchases and excludes simulations', async () => {
  const calls = [], scripts = [], saved = new Map()
  globalThis.window = {fbq: (...args) => calls.push(args)}
  globalThis.document = {head: {appendChild: script => scripts.push(script)}, createElement: () => ({})}
  globalThis.location = {origin:'https://example.test', pathname:'/shop/'}
  globalThis.localStorage = {getItem:key=>saved.get(key), setItem:(key,value)=>saved.set(key,value)}
  const {initializeAnalytics,trackCommerce,trackPurchase} = await import('./analytics.js')
  initializeAnalytics({meta_pixel_enabled:true,meta_pixel_id:'644965951111560'})
  initializeAnalytics({meta_pixel_enabled:true,meta_pixel_id:'644965951111560'})
  assert.equal(calls.filter(call=>call[2]==='PageView').length,1)
  const items = [{sku:'RING-1',product_name:'Ring',quantity:2,unit_price:'100.00',email:'secret@example.test'}]
  trackCommerce('AddToCart','add_to_cart',items,'BDT','200.00')
  const add = calls.at(-1)
  assert.equal(add[3].value,200)
  assert.deepEqual(add[3].content_ids,['RING-1'])
  assert.equal(JSON.stringify(add).includes('secret'),false)
  const order = {id:'one',items,currency:'BDT',total:'250.00',status:'placed'}
  trackPurchase({...order,simulated:true})
  trackPurchase(order);trackPurchase(order)
  assert.equal(calls.filter(call=>call[2]==='Purchase').length,1)
  assert.equal(calls.find(call=>call[2]==='Purchase')[4].eventID,'purchase-one')
  assert.equal(scripts.length,0)
})

test('disabled providers load no scripts or events; GA4 uses verified configuration', async () => {
  const scripts = []
  globalThis.window = {}
  globalThis.document = {head:{appendChild:script=>scripts.push(script)},createElement:()=>({})}
  const disabled = await import('./analytics.js?disabled')
  disabled.initializeAnalytics({meta_pixel_enabled:false,google_analytics_enabled:false})
  disabled.trackCommerce('AddToCart','add_to_cart',[],'BDT',0)
  assert.equal(scripts.length,0)
  assert.equal(window.fbq,undefined)
  assert.equal(window.gtag,undefined)
  const google = await import('./analytics.js?google')
  google.initializeAnalytics({google_analytics_enabled:true,google_measurement_id:'G-TEST123'})
  google.trackCommerce('AddToCart','add_to_cart',[{sku:'SKU',quantity:1,unit_price:'20',product_name:'Ring'}],'BDT','20')
  assert.equal(scripts.length,1)
  assert.equal(window.dataLayer.at(-1)[1],'add_to_cart')
  assert.equal(window.dataLayer.at(-1)[2].value,20)
  assert.equal(window.dataLayer[2][2].page_location,'https://example.test/shop/')
})

test('a broken third-party tracker cannot break successful shopping actions', async () => {
  globalThis.window = {fbq:()=>{throw new Error('Blocked tracker')}}
  const tracker = await import('./analytics.js?blocked')
  assert.doesNotThrow(()=>tracker.initializeAnalytics({meta_pixel_enabled:true,meta_pixel_id:'123'}))
  assert.doesNotThrow(()=>tracker.trackCommerce('AddToCart','add_to_cart',[],'BDT',100))
  assert.doesNotThrow(()=>tracker.trackPurchase({id:'blocked',items:[],currency:'BDT',total:100,status:'placed'}))
})
