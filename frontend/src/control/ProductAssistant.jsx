import { useEffect, useState } from 'react'
import { controlRequest } from './api'

export default function ProductAssistant({ labels: l, navigate, setDirty, onAuthError }) {
  const [config, setConfig] = useState(null)
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [draft, setDraft] = useState(null)
  const [order, setOrder] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(null)
  useEffect(() => {
    const controller = new AbortController()
    controlRequest('assistant/', { signal: controller.signal }).then(setConfig).catch(e => {
      if (e.name !== 'AbortError') { setError(e.message); onAuthError(e) }
    })
    return () => controller.abort()
  }, [onAuthError])
  useEffect(() => () => previews.forEach(url => URL.revokeObjectURL(url)), [previews])
  async function prepare(event) {
    event.preventDefault(); setBusy(true); setError('')
    const body = new FormData(event.currentTarget)
    files.forEach(file => body.append('images', file))
    try {
      const result = await controlRequest('assistant/draft/', { method: 'POST', body })
      setDraft(result); setOrder(result.draft.image_order); setDirty(true)
    } catch (e) { setError(e.message); onAuthError(e) }
    finally { setBusy(false) }
  }
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('')
    const body = new FormData(event.currentTarget)
    files.forEach(file => body.append('images', file))
    body.set('image_order', JSON.stringify(order))
    try {
      const result = await controlRequest(`assistant/drafts/${draft.id}/save/`, { method: 'POST', body })
      setSaved(result); setDirty(false)
      try { localStorage.setItem('storefront-content-revision', String(Date.now())) } catch { /* Optional refresh signal. */ }
    } catch (e) { setError([e.message, ...Object.values(e.fields || {}).flat()].join(' ')); onAuthError(e) }
    finally { setBusy(false) }
  }
  function move(index, offset) {
    const next = [...order]
    ;[next[index], next[index + offset]] = [next[index + offset], next[index]]
    setOrder(next); setDirty(true)
  }
  return <section className="control-records-panel ai-admin">
    <h1>{l.ai_product_title}</h1><p>{l.ai_product_help}</p>
    {error && <p className="control-error" role="alert">{error}</p>}
    {!config && !error && <p role="status">{l.loading}</p>}
    {config && !config.enabled && <p>{l.ai_unavailable}</p>}
    {saved ? <div role="status"><p>{l.ai_saved}</p><button className="control-button primary" onClick={() => navigate(`/sanjilas.product/${saved.id}`)}>{l.edit}</button><button className="control-button" onClick={() => { setSaved(null); setDraft(null); setFiles([]); setPreviews([]) }}>{l.ai_new}</button></div> : config?.enabled && <>
      <form onSubmit={prepare} className="ai-form" onChange={() => setDirty(true)}>
        <label className="ai-field">{l.ai_photos}<input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple required disabled={busy} onChange={e => { const selected = Array.from(e.target.files); setFiles(selected); setPreviews(selected.map(file => URL.createObjectURL(file))); setDraft(null) }} /></label>
        <div className="ai-two-fields"><label className="ai-field">{l.ai_price}<input name="price" type="number" min="0" max="9999999999.99" step="0.01" required disabled={busy} /></label><label className="ai-field">{l.ai_stock}<input name="stock_quantity" type="number" min="0" max="99999999" step="1" disabled={busy} /></label></div>
        <label className="ai-field">{l.ai_notes}<textarea name="notes" rows={3} maxLength={2000} disabled={busy} /></label>
        <button className="control-button primary" disabled={busy || !files.length || files.length > 4}>{busy ? l.ai_busy : l.ai_generate}</button>
      </form>
      {draft && <form key={draft.id} onSubmit={save} className="ai-form ai-review" onChange={() => setDirty(true)}>
        <h2>{l.ai_review}</h2>
        {!!draft.draft.unknowns.length && <aside className="ai-notice"><strong>{l.ai_unknowns}</strong><ul>{draft.draft.unknowns.map((text, i) => <li key={i}>{text}</li>)}</ul></aside>}
        {['name', 'subtitle', 'description', 'color', 'image_alt'].map(name => <label className="ai-field" key={name}>{config.field_labels[name]}{name === 'description' ? <textarea name={name} defaultValue={draft.draft[name]} rows={6} /> : <input name={name} defaultValue={draft.draft[name]} required={name === 'name'} />}</label>)}
        <label className="ai-field">{config.field_labels.category}<select name="category" required defaultValue={draft.draft.category || ''}><option value="">{l.select_empty}</option>{config.choices.category.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        {['tags', 'collections'].map(name => <fieldset key={name}><legend>{config.field_labels[name]}</legend><div className="ai-choices">{config.choices[name].map(item => <label className="control-checkbox" key={item.id}><input type="checkbox" name={name} value={item.id} defaultChecked={draft.draft[name].includes(item.id)} />{item.name}</label>)}</div></fieldset>)}
        <div className="ai-two-fields"><label className="ai-field">{l.ai_price}<input name="price" type="number" min="0" max="9999999999.99" step="0.01" defaultValue={draft.draft.price} required /></label><label className="ai-field">{l.ai_stock}<input name="stock_quantity" type="number" min="0" max="99999999" step="1" defaultValue={draft.draft.stock_quantity} /></label></div>
        <h3>{l.ai_gallery}</h3><div className="ai-photo-grid">{order.map((index, position) => <article key={index}><img src={previews[index]} alt={draft.draft.image_alt} /><p>{position === 0 ? l.ai_main : `${l.ai_gallery} ${position}`}</p><div className="control-toolbar"><button type="button" className="control-button" aria-label={l.ai_move_up} disabled={position === 0 || busy} onClick={() => move(position, -1)}>↑</button><button type="button" className="control-button" aria-label={l.ai_move_down} disabled={position === order.length - 1 || busy} onClick={() => move(position, 1)}>↓</button></div></article>)}</div>
        <label className="control-checkbox"><input type="checkbox" name="is_active" />{l.ai_active}</label>
        <button className="control-button primary" disabled={busy}>{busy ? l.ai_busy : l.ai_save}</button>
      </form>}
    </>}
  </section>
}
