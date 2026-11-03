import { useEffect, useRef, useState } from 'react'
import { applyBranding } from './branding'
import ResponsiveImage from './ResponsiveImage'
import ProductDetail, { Price } from './ProductDetail'
import { priceText } from './catalogPricing'
import useShop from './useShop'
import ShoppingBag from './ShoppingBag'

const bootstrap = (() => {
  try { return JSON.parse(document.getElementById('storefront-bootstrap')?.textContent || '{}') } catch { return {} }
})()

function Icon({ name, ...props }) {
  const paths = {
    bag: <><path d="M5 7h14l1 14H4ZM9 8V6a3 3 0 0 1 6 0v2" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 1v2m0 18v2M1 12h2m18 0h2M4.2 4.2l1.5 1.5m12.6 12.6 1.5 1.5M4.2 19.8l1.5-1.5M18.3 5.7l1.5-1.5" /></>,
    moon: <path d="M20.5 14A8.8 8.8 0 0 1 10 3.5 8.8 8.8 0 1 0 20.5 14Z" />,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    sparkle: <><path d="m12 2 2.8 7.2L22 12l-7.2 2.8L12 22l-2.8-7.2L2 12l7.2-2.8Z" /><path d="M20 2v4m-2-2h4" /></>,
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>
}

function Modal({ open, onClose, label, closeLabel, children, className = '' }) {
  const ref = useRef(null)
  useEffect(() => {
    const dialog = ref.current
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  useEffect(() => {
    if (!open) return
    document.body.classList.add('modal-open')
    return () => document.body.classList.remove('modal-open')
  }, [open])
  return <dialog ref={ref} className={`dialog ${className}`} aria-label={label} onCancel={onClose} onClose={onClose} onClick={(event) => { if (event.target === ref.current) onClose() }}>
    <button className="icon-button dialog-close" aria-label={closeLabel} onClick={onClose}><Icon name="close" /></button>
    {children}
  </dialog>
}

export default function Home() {
  const shop = useShop()
  const [bagOpen,setBagOpen] = useState(()=>new URLSearchParams(window.location.search).get('bag')==='1')
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [mode, setMode] = useState(null)
  const [menu, setMenu] = useState(false)
  const [search, setSearch] = useState(false)
  const [query, setQuery] = useState('')
  const [collection, setCollection] = useState(null)
  const [category,setCategory]=useState(null)
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    let pending = false
    const refresh = () => {
      if (pending || document.visibilityState === 'hidden') return
      pending = true
      fetch('/api/home/', { signal: controller.signal, cache: 'no-store' })
      .then((response) => { if (!response.ok) throw new Error(response.status); return response.json() })
      .then((result) => {
        applyBranding(result.site)
        let saved
        try { saved = localStorage.getItem('storefront-color-mode') } catch { /* Storage may be disabled. */ }
        setMode(['light', 'dark'].includes(saved) ? saved : result.site.default_color_mode)
        setData(result)
      })
      .catch((error) => { if (error.name !== 'AbortError') setFailed(true) })
      .finally(() => { pending = false })
    }
    const changed = (event) => { if (event.key === 'storefront-content-revision') refresh() }
    refresh()
    window.addEventListener('focus', refresh)
    window.addEventListener('pageshow', refresh)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('storage', changed)
    return () => { controller.abort(); window.removeEventListener('focus', refresh); window.removeEventListener('pageshow', refresh); document.removeEventListener('visibilitychange', refresh); window.removeEventListener('storage', changed) }
  }, [attempt])

  useEffect(() => {
    if (!data || !mode) return
    document.documentElement.dataset.palette = data.site.palette
    document.documentElement.dataset.mode = mode
  }, [data, mode])

  const toggleMode = () => {
    const next = mode === 'dark' ? 'light' : 'dark'
    setMode(next)
    try { localStorage.setItem('storefront-color-mode', next) } catch { /* Optional preference. */ }
  }

  if (!data) return <main className="loading-screen" aria-busy={!failed}>
    <div className="loading-content">{failed ? <><p role="alert">{bootstrap.labels?.load_error}</p><button className="retry-button" onClick={() => { setFailed(false); setAttempt(attempt + 1) }} aria-label={bootstrap.labels?.retry || '↻'}>↻</button></> : <><span className="loading-gem" aria-hidden="true"><Icon name="sparkle" /></span><p role="status">{bootstrap.labels?.loading}</p></>}</div>
  </main>

  const { site, page, categories, collections, products } = data
  const selected = products.find((product) => product.id === selectedId) || null
  const l = page.labels
  const featured = products.filter((product)=>(!category||product.category===category)&&(!collection||product.collections.includes(collection))&&((category||collection)||product.is_featured))
  const results = query.trim() ? products.filter((product) => `${product.name} ${product.subtitle} ${categories.find((item) => item.id === product.category)?.name || ''} ${collections.filter((item)=>product.collections.includes(item.id)).map((item)=>item.name).join(' ')} ${product.sku||''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) : products
  const logo = mode === 'dark' && site.logo_dark ? site.logo_dark : site.logo
  const chooseCategory = (id) => {
    setCategory(id)
    setCollection(null)
    setMenu(false)
    document.getElementById('jewellery')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  const navigation = [
    ['#collections', l.nav_categories], ['#jewellery', l.nav_featured], ['#story', l.nav_story],
  ]

  return <>
    <a className="skip-link" href="#main">{l.skip_content}</a>
    {page.announcement && <div className="announcement"><Icon name="sparkle" /><p>{page.announcement}</p><Icon name="sparkle" /></div>}
    <header className="site-header" id="top">
      <a className="brand" href="#top" aria-label={site.site_name}>
        {logo ? <ResponsiveImage className="brand-logo" src={logo} media={mode === 'dark' && site.logo_dark ? site.logo_dark_media : site.logo_media} sizes="190px" alt={site.logo_alt || site.site_name} /> : <><span className="brand-mark" aria-hidden="true">✳</span><span>{site.site_name}</span></>}
      </a>
      <nav className={`main-nav ${menu ? 'is-open' : ''}`} aria-label={l.navigation}>
        {navigation.map(([url, label]) => <a key={url} href={url} onClick={() => setMenu(false)}>{label}</a>)}
      </nav>
      <div className="header-actions">
        <button className="icon-button bag-open" aria-label={l.cart_open} onClick={()=>{setBagOpen(true);shop.refresh().catch((failure)=>shop.setError(failure.message))}}><Icon name="bag" />{shop.cart?.items.length>0&&<span>{shop.cart.items.reduce((sum,item)=>sum+(item.expired?0:item.quantity),0)}</span>}</button>
        <a className="store-login-link" href="/login/">{l.nav_login}</a>
        <button className="icon-button" onClick={() => setSearch(true)} aria-label={l.search_open}><Icon name="search" /></button>
        <button className="icon-button theme-toggle" onClick={toggleMode} aria-label={mode === 'dark' ? l.mode_light : l.mode_dark} title={mode === 'dark' ? l.mode_light : l.mode_dark} aria-pressed={mode === 'dark'}><Icon name={mode === 'dark' ? 'sun' : 'moon'} /></button>
        <a className="header-contact" href="#contact">{l.nav_contact}<Icon name="arrow" /></a>
        <button className="icon-button mobile-menu" onClick={() => setMenu(!menu)} aria-label={menu ? l.menu_close : l.menu_open} aria-expanded={menu}><Icon name={menu ? 'close' : 'menu'} /></button>
      </div>
    </header>

    <main id="main">
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow"><span className="small-line" />{page.hero_eyebrow}</div>
          <h1 id="hero-title">{page.hero_title}</h1>
          <p className="hero-description">{page.hero_description}</p>
          <a className="button button-primary" href="#jewellery">{page.hero_cta}<Icon name="arrow" /></a>
          <a className="text-link hero-story-link" href="#story">{page.hero_secondary_cta}<span>↗</span></a>
          <div className="hero-signature"><Icon name="sparkle" /><span>{site.tagline || page.hero_caption}</span></div>
        </div>
        <div className="hero-visual">
          {page.hero_image && <ResponsiveImage src={page.hero_image} media={page.hero_image_media} sizes="(max-width: 760px) 100vw, 50vw" alt={page.hero_image_alt} fetchPriority="high" />}
          <div className="hero-photo-label"><span>{page.hero_caption}</span><Icon name="sparkle" /></div>
          <span className="hero-image-frame" aria-hidden="true" />
        </div>
      </section>

      <section className="section collections-section" id="collections" aria-labelledby="collections-title">
        <div className="section-heading"><p className="eyebrow">{page.collections_eyebrow}</p><h2 id="collections-title">{page.collections_title}</h2></div>
        <div className="collection-grid">
          {categories.map((item, index) => <button className="collection-card" key={item.id} onClick={() => chooseCategory(item.id)}>
            <div className="collection-image">{item.image && <ResponsiveImage src={item.image} media={item.image_media} sizes="(max-width: 760px) 50vw, 25vw" alt={item.image_alt || item.name} loading="lazy" />}<span className="collection-number">{String(index + 1).padStart(2, '0')}</span></div>
            <div className="collection-caption"><div><h3>{item.name}</h3><p>{item.description}</p></div><span className="circle-arrow"><Icon name="arrow" /></span></div>
          </button>)}
        </div>
      </section>

      <section className="section featured-section" id="jewellery" aria-labelledby="featured-title">
        <div className="featured-heading"><div><p className="eyebrow">{page.featured_eyebrow}</p><h2 id="featured-title">{page.featured_title}</h2></div><p>{page.featured_description}</p></div>
        <div className="collection-filters" aria-label={l.nav_categories}>
          <button className={category === null ? 'active' : ''} aria-pressed={category === null} onClick={() => setCategory(null)}>{l.all_categories}</button>
          {categories.map((item) => <button key={item.id} className={category === item.id ? 'active' : ''} aria-pressed={category === item.id} onClick={() => setCategory(item.id)}>{item.name}</button>)}
        </div>
        {collections.length>0&&<div className="collection-filters" aria-label={l.nav_collections}><button className={collection===null?'active':''} aria-pressed={collection===null} onClick={()=>setCollection(null)}>{l.all_collections}</button>{collections.map((item)=><button key={item.id} className={collection===item.id?'active':''} aria-pressed={collection===item.id} onClick={()=>setCollection(item.id)}>{item.name}</button>)}</div>}
        <div className="product-grid">
          {featured.map((product) => <button className="product-card" key={product.id} onClick={() => setSelectedId(product.id)} aria-label={`${l.view_piece}: ${product.name}`}>
            <div className="product-image">{product.image && <ResponsiveImage src={product.image} media={product.image_media} sizes="(max-width: 760px) 50vw, 25vw" alt={product.image_alt || product.name} loading="lazy" />}{product.badge && <span className="product-badge">{product.badge}</span>}<span className="product-discover"><Icon name="arrow" /></span></div>
            <div className="product-copy"><h3>{product.name}</h3><p>{product.subtitle}</p><span className="product-price"><Price item={product} labels={l} range /></span></div>
          </button>)}
        </div>
        {!featured.length && <p className="empty-state">{l.collection_empty}</p>}
      </section>

      <section className="story-section" id="story" aria-labelledby="story-title">
        <div className="story-visual">{page.story_image && <ResponsiveImage src={page.story_image} media={page.story_image_media} sizes="(max-width: 760px) 100vw, 50vw" alt={page.story_image_alt} loading="lazy" />}<span className="story-seal" aria-hidden="true"><Icon name="sparkle" /></span></div>
        <div className="story-copy"><p className="eyebrow">{page.story_eyebrow}</p><h2 id="story-title">{page.story_title}</h2><div className="story-body">{page.story_body.split('\n\n').map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div><a className="text-link" href="#collections">{page.story_cta}<Icon name="arrow" /></a></div>
      </section>

      <section className="contact-section section" id="contact" aria-labelledby="contact-title">
        <Icon className="contact-sparkle" name="sparkle" /><p className="eyebrow">{page.contact_eyebrow}</p><h2 id="contact-title">{page.contact_title}</h2><p className="contact-body">{page.contact_body}</p>
        <a className="button button-primary" href={site.contact_email ? `mailto:${site.contact_email}` : '#jewellery'}>{site.contact_email ? l.nav_contact : page.contact_cta}<Icon name="arrow" /></a>
      </section>
    </main>

    <footer className="site-footer">
      <div className="footer-top"><div><a className="brand footer-brand" href="#top">{logo ? <ResponsiveImage className="brand-logo" src={logo} media={mode === 'dark' && site.logo_dark ? site.logo_dark_media : site.logo_media} sizes="190px" alt={site.logo_alt || site.site_name} /> : site.site_name}</a><p>{site.tagline || l.footer_note}</p></div>
        <div><h3>{l.footer_navigation}</h3>{navigation.map(([url, label]) => <a key={url} href={url}>{label}</a>)}</div>
        <div><h3>{l.footer_contact}</h3>{site.contact_email ? <a href={`mailto:${site.contact_email}`}>{site.contact_email}</a> : <a href="#contact">{l.nav_contact}</a>}</div>
      </div>
      <div className="footer-bottom"><p>{site.footer_text}</p><a href="#top">{l.back_top}<span>↑</span></a></div>
    </footer>

    <Modal open={bagOpen} onClose={()=>setBagOpen(false)} label={l.cart} closeLabel={l.cart_close} className="bag-dialog">{bagOpen&&<ShoppingBag shop={shop} labels={l} onChanged={()=>setAttempt((value)=>value+1)} onClose={()=>setBagOpen(false)} />}</Modal>
    <Modal open={search} onClose={() => setSearch(false)} label={l.search_open} closeLabel={l.search_close} className="search-dialog">
      <p className="eyebrow">{l.search_open}</p><h2>{l.search_results}</h2><label className="search-field"><span className="sr-only">{l.search_label}</span><Icon name="search" /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={l.search_placeholder} /></label>
      <div className="search-results">{results.map((product) => <button key={product.id} onClick={() => { setSearch(false); setSelectedId(product.id) }}><ResponsiveImage src={product.image} media={product.image_media} sizes="65px" alt={product.image_alt || product.name} /><span><strong>{product.name}</strong><small>{priceText(product, l)}</small></span><Icon name="arrow" /></button>)}{!results.length && <p>{l.search_empty}</p>}</div>
    </Modal>
    <Modal open={!!selected} onClose={() => setSelectedId(null)} label={selected?.name} closeLabel={l.close_details} className="product-dialog">
      {selected && <ProductDetail key={selected.id} product={selected} categories={categories} site={site} labels={l} onAdd={async(variant,quantity)=>{
        if(!shop.cart?.authenticated){setSelectedId(null);setBagOpen(true);return}
        const existing=shop.cart.items.find((item)=>item.product_id===selected.id&&item.variant_id===(variant?.id||null)&&!item.expired)
        try {await shop.mutate('cart/items/',{product_id:selected.id,variant_id:variant?.id,quantity:(existing?.quantity||0)+quantity});setSelectedId(null);setBagOpen(true)}
        finally {setAttempt((value)=>value+1)}
      }} />}
    </Modal>
  </>
}
