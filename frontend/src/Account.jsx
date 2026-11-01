import { useEffect, useState } from 'react'
import { applyBranding } from './branding'
import { Login, ControlIcon } from './control/Control'
import { controlRequest } from './control/api'

export default function Account() {
  const [session, setSession] = useState(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState('')
  const [mode, setMode] = useState('light')
  async function refresh() {
    const data = await controlRequest('/api/account/session/')
    if (data.authenticated && data.destination === '/control/') {
      window.location.replace(data.destination)
      return
    }
    if (data.authenticated && new URLSearchParams(window.location.search).get('next') === 'bag') {
      window.location.replace('/?bag=1')
      return
    }
    applyBranding(data.site)
    let saved
    try { saved = localStorage.getItem('storefront-color-mode') } catch { /* Optional preference. */ }
    const next = ['light', 'dark'].includes(saved) ? saved : data.site.default_color_mode
    setMode(next)
    document.documentElement.dataset.palette = data.site.palette
    document.documentElement.dataset.mode = next
    document.title = `${data.site.site_name} · ${data.labels.account_name}`
    setSession(data)
  }
  useEffect(() => { Promise.resolve().then(refresh).catch(() => setFailed(true)) }, [attempt])
  if (!session) return <main className="loading-screen"><div className="loading-content"><ControlIcon name="diamond" />{failed && <button className="retry-button" onClick={() => { setFailed(false); setAttempt(attempt + 1) }}>↻</button>}</div></main>
  const l = session.labels
  if (!session.authenticated) return <div className="control-root"><Login session={session} mode={mode} onLogin={refresh} loginPath="/api/account/login/" /></div>
  async function logout() {
    try { await controlRequest('/api/account/logout/', { method: 'POST' }); await refresh() }
    catch (failure) { setError(failure.message) }
  }
  return <main className="control-root account-page"><section className="control-login-box"><p className="eyebrow">{session.site.site_name} / {l.account_name}</p><h1>{l.account_title}</h1><p>{session.user.name}</p><p>{l.account_description}</p><a className="button button-primary" href="/">{l.storefront}<ControlIcon name="arrow" /></a><button className="button" onClick={logout}>{l.sign_out}</button>{error && <p className="control-error" role="alert">{error}</p>}</section></main>
}
