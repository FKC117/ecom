import {useEffect,useState} from 'react'
import {controlRequest} from './api'

export default function CourierDirectory({labels:l,onAuthError}){
  const [accounts,setAccounts]=useState([])
  const [account,setAccount]=useState('')
  const [cities,setCities]=useState([])
  const [zones,setZones]=useState([])
  const [areas,setAreas]=useState([])
  const [city,setCity]=useState('')
  const [zone,setZone]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState(null)
  const selected=accounts.find(row=>String(row.id)===account)
  const sync=selected?.sync
  const active=['queued','running'].includes(sync?.state)
  useEffect(()=>{
    const controller=new AbortController()
    controlRequest('courier-directory/',{signal:controller.signal}).then(data=>{setAccounts(data.accounts);if(data.accounts.length===1)setAccount(String(data.accounts[0].id))}).catch(e=>{if(e.name!=='AbortError'){setError(e);onAuthError(e)}})
    return()=>controller.abort()
  },[onAuthError])
  useEffect(()=>{
    if(!active)return
    const controller=new AbortController()
    const timer=setInterval(()=>controlRequest('courier-directory/',{signal:controller.signal}).then(data=>setAccounts(data.accounts)).catch(e=>{if(e.name!=='AbortError')setError(e)}),2000)
    return()=>{controller.abort();clearInterval(timer)}
  },[active,account])
  // These requests read saved PostgreSQL records only.
  useEffect(()=>{
    if(!account)return
    const controller=new AbortController()
    controlRequest(`couriers/${account}/cities/`,{signal:controller.signal}).then(data=>{setCities(data.choices);setCity(current=>data.choices.some(row=>String(row.id)===current)?current:String(data.choices[0]?.id||''));setError(null)}).catch(e=>{if(e.name!=='AbortError'&&!active)setError(e)})
    return()=>controller.abort()
  },[account,sync?.state,active])
  useEffect(()=>{
    if(!city)return
    const controller=new AbortController()
    controlRequest(`couriers/${account}/zones/?parent=${city}`,{signal:controller.signal}).then(data=>{setZones(data.choices);setZone(String(data.choices[0]?.id||''));setError(null)}).catch(e=>{if(e.name!=='AbortError'&&!active)setError(e)})
    return()=>controller.abort()
  },[account,city,sync?.state,active])
  useEffect(()=>{
    if(!zone)return
    const controller=new AbortController()
    controlRequest(`couriers/${account}/areas/?parent=${zone}`,{signal:controller.signal}).then(data=>{setAreas(data.choices);setError(null)}).catch(e=>{if(e.name!=='AbortError'&&!active)setError(e)})
    return()=>controller.abort()
  },[account,zone,sync?.state,active])
  async function update(){
    if(!window.confirm(l.courier_directory_confirm))return
    setBusy(true);setError(null)
    try{
      const result=await controlRequest(`courier-directory/${account}/refresh/`,{method:'POST',body:new FormData()})
      setAccounts(rows=>rows.map(row=>String(row.id)===account?{...row,sync:result.sync}:row))
    }catch(e){setError(e);onAuthError(e)}finally{setBusy(false)}
  }
  return <><div className="control-page-heading"><div><h1>{l.courier_directory_title}</h1><p className="control-muted">{l.courier_directory_help}</p></div></div>
    {error&&<div className="control-error" role="alert">{Object.values(error.fields||{}).flat().join(' ')||error.message}</div>}
    <section className="control-form-section ops-form"><label>{l.courier_account}<select value={account} disabled={busy} onChange={e=>{setCities([]);setZones([]);setAreas([]);setCity('');setZone('');setError(null);setAccount(e.target.value)}}><option value="">{l.blank}</option>{accounts.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
    {selected?.can_refresh&&<button className="control-button primary" disabled={busy||!account||(active&&!sync?.can_resume)} onClick={update}>{busy?l.loading:l.courier_directory_all}</button>}
    {sync&&<section className={sync.state==='failed'?'control-error':'control-success'} role="status"><strong>{l.courier_directory_progress}: {sync.state_label}</strong><p>{l.courier_cities}: {sync.processed_cities} / {sync.cities} · {l.courier_zones}: {sync.processed_zones} / {sync.zones} · {l.courier_areas}: {sync.areas}</p>{sync.last_error&&<p>{sync.last_error}</p>}{active&&sync.last_error&&<p>{l.courier_directory_next}: {new Date(sync.next_attempt_at).toLocaleString()}</p>}{sync.state!=='completed'&&<p>{l.courier_directory_staging_help} <a href={sync.staging_url} target="_blank" rel="noreferrer">{l.courier_directory_staging}</a></p>}{sync.state==='completed'&&<p>{l.courier_directory_saved}</p>}</section>}
    <label>{l.courier_cities}<select value={city} disabled={busy||!account} onChange={e=>{setZones([]);setAreas([]);setZone('');setCity(e.target.value);setError(null)}}><option value="">{l.blank}</option>{cities.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
    <label>{l.courier_zones}<select value={zone} disabled={busy||!city} onChange={e=>{setAreas([]);setZone(e.target.value);setError(null)}}><option value="">{l.blank}</option>{zones.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
    <label>{l.courier_areas}<select key={`${account}-${zone}-${sync?.state}`} disabled={busy||!zone} defaultValue=""><option value="">{l.blank}</option>{areas.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
    </section></>
}
