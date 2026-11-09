import ResponsiveImage from './ResponsiveImage'
import {Price} from './ProductDetail'

export default function CatalogPage({data}) {
  const l=data.page.labels
  const listing=data.listing
  const params=new URLSearchParams(window.location.search)
  const pageLink=number=>{const next=new URLSearchParams(params);next.set('page',number);return `${window.location.pathname}?${next}`}
  if(!listing)return <section className="section product-missing"><h1>{l.catalog_missing}</h1><a className="button button-primary" href="/shop/">{l.continue_shopping}</a></section>
  return <section className="section catalog-page">
    <nav className="product-breadcrumbs" aria-label={l.breadcrumbs}><a href="/">{l.product_home}</a><span aria-hidden="true">/</span><a href="/shop/">{l.catalog_title}</a>{window.location.pathname!=='/shop/'&&<><span aria-hidden="true">/</span><span aria-current="page">{listing.name}</span></>}</nav>
    <header className="listing-heading"><div><h1>{listing.name}</h1>{listing.description&&<p>{listing.description}</p>}<p role="status">{l.catalog_count.replace('{count}',listing.count)}</p></div></header>
    <div className="listing-layout">
    <aside className="listing-sidebar">
    <form className="listing-filters" method="get" action={window.location.pathname}>
      <label>{l.catalog_search}<input name="q" type="search" defaultValue={params.get('q')||''} maxLength={150}/></label>
      <label>{l.catalog_min}<input name="min_price" type="number" min="0" step="0.01" defaultValue={params.get('min_price')||''}/></label>
      <label>{l.catalog_max}<input name="max_price" type="number" min="0" step="0.01" defaultValue={params.get('max_price')||''}/></label>
      <label>{l.catalog_sort}<select name="sort" defaultValue={params.get('sort')||'featured'}>{['featured','newest','price_asc','price_desc','name'].map(key=><option key={key} value={key}>{l[`catalog_${key}`]}</option>)}</select></label>
      <label className="listing-stock"><input name="in_stock" type="checkbox" value="1" defaultChecked={params.get('in_stock')==='1'}/>{l.catalog_in_stock}</label>
      <div className="listing-filter-actions"><button className="button button-primary">{l.catalog_apply}</button><a className="text-link" href={window.location.pathname}>{l.catalog_reset}</a></div>
    </form>
    <nav className="listing-categories" aria-label={l.nav_categories}><h2>{l.nav_categories}</h2><a href="/shop/">{l.all_categories}</a>{data.categories.map(category=><a href={`/categories/${category.slug}/`} key={category.id}>{category.name}</a>)}</nav>
    {data.collections.length>0&&<nav className="listing-categories" aria-label={l.nav_collections}><h2>{l.nav_collections}</h2>{data.collections.map(collection=><a href={`/collections/${collection.slug}/`} key={collection.id}>{collection.name}</a>)}</nav>}
    </aside>
    <div className="listing-results">
    {data.error&&<p role="alert" className="control-error">{data.error}</p>}
    <div className="product-grid">{data.products.map(product=><a className="product-card" key={product.id} href={`/products/${product.slug}/`} aria-label={`${l.view_piece}: ${product.name}`}><div className="product-image">{product.image&&<ResponsiveImage src={product.image} media={product.image_media} sizes="(max-width: 760px) 50vw, 25vw" alt={product.image_alt||product.name} loading="lazy"/>}{product.badge&&<span className="product-badge">{product.badge}</span>}</div><div className="product-copy"><h2>{product.name}</h2><p>{product.subtitle}</p><Price item={product} labels={l} range/>{product.availability==='sold_out'&&<p>{l.sold_out}</p>}</div></a>)}</div>
    {!data.products.length&&!data.error&&<p className="empty-state">{l.catalog_empty}</p>}
    {listing.pages>1&&<nav className="listing-pagination" aria-label={l.catalog_pagination}>{listing.page>1&&<a className="button" rel="prev" href={pageLink(listing.page-1)}>{l.catalog_previous}</a>}<span>{l.catalog_page.replace('{page}',listing.page).replace('{pages}',listing.pages)}</span>{listing.page<listing.pages&&<a className="button" rel="next" href={pageLink(listing.page+1)}>{l.catalog_next}</a>}</nav>}
    </div>
    </div>
  </section>
}
