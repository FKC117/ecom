import { useEffect, useRef, useState } from 'react'

export default function FashionAssistant() {
  const [config, setConfig] = useState(null)
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef(null)
  const opener = useRef(null)
  const bottom = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/shop/assistant/', { credentials: 'same-origin', signal: controller.signal })
      .then(r => r.ok ? r.json() : null).then(setConfig).catch(() => {})
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!dialog.current) return
    if (open) dialog.current.showModal()
    else { dialog.current.close(); opener.current?.focus() }
  }, [open])
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }) }, [turns, busy])
  async function send(event) {
    event.preventDefault()
    const form = event.currentTarget
    const body = new FormData(form)
    if (!body.get('image')?.size) body.delete('image')
    setBusy(true); setError('')
    try {
      const response = await fetch('/api/shop/assistant/chat/', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': config.csrf_token }, body })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || config.labels.ai_failed)
      setTurns(previous => [...previous, { user: body.get('message'), ...result }].slice(-10))
      form.reset()
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  if (!config?.enabled) return null
  const l = config.labels
  return <>
    <button ref={opener} className="ai-chat-launch" onClick={() => setOpen(true)} aria-haspopup="dialog">✧ {l.ai_open}</button>
    <dialog ref={dialog} className="ai-chat-dialog" aria-labelledby="ai-chat-heading" onCancel={() => setOpen(false)} onClose={() => setOpen(false)}>
      <header className="ai-chat-heading"><h2 id="ai-chat-heading">{l.ai_title}</h2><button className="icon-button" aria-label={l.ai_close} onClick={() => setOpen(false)}>×</button></header>
      <div className="ai-chat-messages" role="log" aria-live="polite"><p>{l.ai_intro}</p>{turns.map((turn, i) => <article key={i}><p className="ai-chat-user">{turn.user}</p><p className="ai-chat-reply">{turn.reply}</p><div className="ai-recommendations">{turn.products.map(product => <a key={product.id} href={product.url}>{product.image && <img src={product.image} alt={product.image_alt} loading="lazy" />}<span>{product.name}</span><strong>{product.currency} {product.price}</strong></a>)}</div></article>)}{busy && <p role="status">{l.ai_busy}</p>}<div ref={bottom} /></div>
      {error && <p className="ai-chat-error" role="alert">{error}</p>}
      <form onSubmit={send} className="ai-chat-form"><label className="ai-field">{l.ai_message}<textarea name="message" rows={2} maxLength={2000} required disabled={busy} /></label><label className="ai-field">{l.ai_photo}<input name="image" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} /></label><label className="ai-consent"><input name="photo_consent" value="yes" type="checkbox" disabled={busy} />{l.ai_consent}</label><p className="ai-privacy">{l.ai_privacy}</p><button className="button button-primary" disabled={busy}>{l.ai_send}</button><a className="text-link" href="/shop/catalog/">{l.ai_catalog}</a></form>
    </dialog>
  </>
}
