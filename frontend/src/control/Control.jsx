import { useCallback, useEffect, useRef, useState } from 'react'
import { applyBranding } from '../branding'
import { controlRequest } from './api'
import Workspace from './Workspace'
import Operations from './Operations'
import ManualInvoice from './ManualInvoice'

export function ControlIcon({ name }) {
  const paths = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    diamond: <><path d="m12 2 9 10-9 10L3 12Z" /><path d="M3 12h18M12 2l4 10-4 10-4-10Z" /></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    moon: <path d="M20.5 14A8.8 8.8 0 0 1 10 3.5 8.8 8.8 0 1 0 20.5 14Z" />,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 1v2m0 18v2M1 12h2m18 0h2M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2" /></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    logout: <><path d="M10 4H4v16h6M9 12h12m-5-5 5 5-5 5" /></>,
  }
  return <svg viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.diamond}</svg>
}

function Brand({ site, mode, suffix = false, labels }) {
  const logo = mode === 'dark' && site.logo_dark ? site.logo_dark : site.logo
  return <a className="control-brand" href="/control/">{logo ? <img src={logo} alt={site.logo_alt || site.site_name} /> : <><ControlIcon name="diamond" /><span>{site.site_name}</span></>}{suffix && <small>{labels.panel_name}</small>}</a>
}

export function Login({ session, mode, onLogin, loginPath = "login/" }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const l = session.labels
  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try { await controlRequest(loginPath, { method: 'POST', body: new FormData(event.currentTarget) }); await onLogin() }
    catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <main className="control-login">
    <aside className="control-login-story"><Brand site={session.site} mode={mode} labels={l} /><div><p className="eyebrow">{l.panel_eyebrow}</p><h1>{l.login_title}</h1><p>{l.login_description}</p></div><ControlIcon name="diamond" /></aside>
    <section className="control-login-form"><a className="control-back-store" href="/">← {l.storefront}</a><div className="control-login-box"><span className="control-emblem"><ControlIcon name="diamond" /></span><p className="eyebrow">{session.site.site_name} / {l.panel_name}</p><h2>{l.sign_in}</h2><p className="control-muted">{l.login_description}</p><form onSubmit={submit}>
      <label>{l.username}<input name="username" autoComplete="username" required maxLength={254} /></label>
      <label>{l.password}<input name="password" type="password" autoComplete="current-password" required /></label>
      {error && <p role="alert" className="control-error">{error}</p>}
      <button className="button button-primary" disabled={busy}>{busy ? l.loading : l.sign_in}<ControlIcon name="arrow" /></button>
    </form><p className="control-login-note">{l.roles_note}</p></div></section>
  </main>
}

export default function Control() {
  const [session, setSession] = useState(null)
  const [mode, setMode] = useState(null)
  const [route, setRoute] = useState(() => window.location.hash.slice(1))
  const [menu, setMenu] = useState(false)
  const [error, setError] = useState('')
  const [dirty, setDirty] = useState(false)
  const [notice, setNotice] = useState('')
  const sidebar = useRef(null)
  const menuButton = useRef(null)

  const acceptSession = useCallback((data) => {
    applyBranding(data.site)
    setSession(data)
    if (!data.authenticated) {setMenu(false); setDirty(false)}
    setMode((current) => {
      if (current) return current
      let stored
      try { stored = localStorage.getItem('storefront-color-mode') } catch { /* Optional preference. */ }
      return ['light', 'dark'].includes(stored) ? stored : data.site.default_color_mode
    })
    return data
  }, [])
  const refreshSession = useCallback(() => controlRequest('session/').then(acceptSession), [acceptSession])

  useEffect(() => { controlRequest('session/').then(acceptSession).catch((failure) => setError(failure.message)) }, [acceptSession])
  useEffect(() => {
    const change = () => { setRoute(window.location.hash.slice(1)); setMenu(false); setNotice('') }
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])
  useEffect(() => {
    if (!session || !mode) return
    document.documentElement.dataset.palette = session.site.palette
    document.documentElement.dataset.mode = mode
    document.title = `${session.site.site_name} · ${session.labels.panel_name}`
  }, [session, mode])
  useEffect(() => {
    if (!dirty) return
    const leave = (event) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', leave)
    return () => window.removeEventListener('beforeunload', leave)
  }, [dirty])
  useEffect(() => {
    if (!menu) return
    const nodes = sidebar.current.querySelectorAll('a[href], button:not([disabled])')
    const opener = menuButton.current
    nodes[0]?.focus()
    document.body.classList.add('modal-open')
    const trap = (event) => {
      if (event.key === 'Escape') setMenu(false)
      if (event.key !== 'Tab' || !nodes.length) return
      if (event.shiftKey && document.activeElement === nodes[0]) {event.preventDefault(); nodes[nodes.length-1].focus()}
      else if (!event.shiftKey && document.activeElement === nodes[nodes.length-1]) {event.preventDefault(); nodes[0].focus()}
    }
    window.addEventListener('keydown',trap)
    return () => {window.removeEventListener('keydown',trap); document.body.classList.remove('modal-open'); opener?.focus()}
  }, [menu])

  const navigate = (target) => {
    if (dirty && !window.confirm(session.labels.changes_unsaved)) return
    setDirty(false)
    setMenu(false)
    setNotice('')
    window.location.hash = target
  }
  const toggle = () => {
    const next = mode === 'dark' ? 'light' : 'dark'
    setMode(next)
    try { localStorage.setItem('storefront-color-mode', next) } catch { /* Optional preference. */ }
  }
  const handleError = useCallback((failure) => {
    if (failure.status === 401 || failure.status === 403) refreshSession().catch(() => {})
  }, [refreshSession])
  const signOut = async () => {
    if (dirty && !window.confirm(session.labels.changes_unsaved)) return
    try { await controlRequest('logout/', {method:'POST'}); setDirty(false); await refreshSession() }
    catch (failure) { setError(failure.message) }
  }

  if (!session) return <main className="loading-screen"><div className="loading-content"><ControlIcon name="diamond" />{error && <button className="retry-button" onClick={() => refreshSession().catch((failure) => setError(failure.message))}>↻</button>}</div></main>
  const l = session.labels
  if (!session.authenticated) return <div className="control-root"><Login session={session} mode={mode} onLogin={refreshSession} /></div>

  const selectedKey = route.split('/').filter(Boolean)[0]
  const model = session.models.find((item) => item.key === selectedKey)
  const workspaces = session.workspaces || []
  const operation = workspaces.find((item)=>`operations.${item.key}`===selectedKey)
  const directory = session.models.filter((item) => item.menu_visible !== false && !item.workspace)
  const groups = [...new Set(directory.map((item) => item.app_name))]
  return <div className="control-root control-layout">
    {menu && <button className="control-scrim" aria-label={l.menu_close} onClick={() => setMenu(false)} />}
    <aside ref={sidebar} className={`control-sidebar ${menu ? 'is-open' : ''}`} role={menu ? 'dialog' : undefined} aria-modal={menu || undefined} aria-label={l.models}>
      <button className="icon-button control-nav-close" aria-label={l.menu_close} onClick={() => setMenu(false)}><ControlIcon name="close" /></button>
      <div className="control-sidebar-brand"><Brand site={session.site} mode={mode} suffix labels={l} /></div>
      <nav aria-label={l.models}><button className={`control-nav-item ${!selectedKey ? 'selected' : ''}`} onClick={() => navigate('')}><ControlIcon name="grid" />{l.dashboard}</button>{workspaces.map((item)=><button key={item.key} className={`control-nav-item ${operation?.key===item.key?'selected':''}`} onClick={()=>navigate(`/operations.${item.key}`)}><ControlIcon name="grid" />{item.name}</button>)}<p className="control-nav-caption">{l.models}</p>
        {groups.map((group) => <div key={group} className="control-nav-group"><p>{group}</p>{directory.filter((item) => item.app_name === group).map((item) => <button className={`control-nav-item ${model?.key === item.key ? 'selected' : ''}`} key={item.key} onClick={() => navigate(`/${item.key}${item.permissions.view ? '' : '/new'}`)}><ControlIcon name="diamond" /><span>{item.name_plural}</span>{item.count !== null && <small>{item.count}</small>}</button>)}</div>)}
      </nav>
      <div className="control-user"><div className="control-avatar">{session.user.name.slice(0,1).toLocaleUpperCase()}</div><div><strong>{session.user.name}</strong><span>{session.user.superuser ? l.superuser : session.user.roles.join(', ') || l.staff}</span></div><button className="icon-button" onClick={signOut} aria-label={l.sign_out}><ControlIcon name="logout" /></button></div>
    </aside>
    <div className="control-main">
      <header className="control-topbar"><div><button ref={menuButton} className="icon-button control-mobile-menu" aria-label={menu ? l.menu_close : l.menu} aria-expanded={menu} onClick={() => setMenu(!menu)}><ControlIcon name="menu" /></button><span>{l.panel_name}</span><span className="control-muted">/</span><strong>{operation?.name || model?.name_plural || l.dashboard}</strong></div><div><button className="icon-button" aria-label={mode === 'dark' ? l.mode_light : l.mode_dark} title={mode === 'dark' ? l.mode_light : l.mode_dark} onClick={toggle}><ControlIcon name={mode === 'dark' ? 'sun' : 'moon'} /></button><a className="control-store-link" href="/">{l.storefront}<ControlIcon name="arrow" /></a></div></header>
      <main className="control-content">
        {error && <p className="control-error" role="alert">{error}</p>}{notice && <p className="control-success" role="status">{notice}</p>}
        {operation?.key==='orders'&&route.split('/').filter(Boolean)[2]==='edit' ? <ManualInvoice key={route} orderId={route.split('/').filter(Boolean)[1]} labels={l} navigate={navigate} setDirty={setDirty} onRefresh={refreshSession}/> : operation?.key==='orders'&&route.split('/').filter(Boolean)[1]==='new' ? operation.can_create ? <ManualInvoice labels={l} navigate={navigate} setDirty={setDirty} onRefresh={refreshSession}/> : <p className="control-error">{l.permission_denied}</p> : operation ? <Operations key={route} kind={operation.key} canCreate={operation.can_create} route={route} labels={l} navigate={navigate} setDirty={setDirty} onAuthError={handleError} onRefresh={refreshSession}/> : selectedKey && model ? <Workspace key={route} model={model} route={route} labels={l} navigate={navigate} setDirty={setDirty} onSaved={async (message, target) => {setDirty(false); if (target !== undefined) window.location.hash = target; await refreshSession(); setNotice(message)}} onAuthError={handleError} /> : selectedKey ? <p className="control-error" role="alert">{l.permission_denied}</p> : <>
          <div className="control-welcome"><p className="eyebrow">{session.site.site_name} / {l.panel_name}</p><h1>{l.dashboard_title}</h1><p>{l.dashboard_description}</p><span className="control-welcome-gem"><ControlIcon name="diamond" /></span></div>
          <div className="control-toolbar control-dashboard-actions">{workspaces.map((item)=><button className="control-button primary" key={item.key} onClick={()=>navigate(`/operations.${item.key}`)}>{item.name} →</button>)}</div>
          <div className="control-section-title"><h2>{l.models}</h2><span>{directory.length}</span></div>
          <div className="control-model-grid">{directory.map((item) => <button className="control-model-card" key={item.key} onClick={() => navigate(`/${item.key}${item.permissions.view ? '' : '/new'}`)}><span className="control-model-icon"><ControlIcon name="diamond" /></span><span className="control-model-app">{item.app_name}</span><h3>{item.name_plural}</h3><div><span>{item.count ?? l.blank} <small>{l.records}</small></span><ControlIcon name="arrow" /></div><p>{item.permissions.change ? l.edit : item.permissions.add ? l.add : l.view_only}</p></button>)}</div>
          {!directory.length && <p className="control-empty">{l.no_models}</p>}
          <div className="control-access-note"><ControlIcon name="grid" /><div><h3>{l.access}</h3><p>{l.roles_note}</p></div>{session.user.superuser && <a href="/admin/" target="_blank" rel="noreferrer">{l.django_admin} ↗</a>}</div>
        </>}
      </main>
    </div>
  </div>
}
