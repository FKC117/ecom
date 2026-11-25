import {useEffect,useState} from 'react'
import {controlRequest} from './api'

function useLocations(account,kind,parent){
  const [result,setResult]=useState(null)
  const [retry,setRetry]=useState(0)
  const enabled=!!account&&(kind==='cities'||!!parent)
  const key=`${account}/${kind}/${parent||''}/${retry}`
  useEffect(()=>{
    if(!enabled)return
    const controller=new AbortController()
    controlRequest(`couriers/${account}/${kind}/?parent=${encodeURIComponent(parent||'')}`,{signal:controller.signal})
      .then(data=>setResult({key,rows:data.choices,error:null}))
      .catch(error=>{if(error.name!=='AbortError')setResult({key,rows:[],error})})
    return()=>controller.abort()
  },[account,kind,parent,enabled,key])
  const current=result?.key===key?result:null
  return {rows:current?.rows||[],error:current?.error,loading:enabled&&!current,retry:()=>setRetry(value=>value+1)}
}

const normalize=value=>(value||'').normalize('NFKC').trim().toLocaleLowerCase()

export default function CourierLocations({account,fields,order,labels:l,busy,onReady,destination={}}){
  const [chosenCity,setCity]=useState(null)
  const [zone,setZone]=useState(destination.recipient_zone?String(destination.recipient_zone):'')
  const [area,setArea]=useState(destination.recipient_area?String(destination.recipient_area):'')
  const cities=useLocations(account,'cities')
  const matches=cities.rows.filter(row=>normalize(row.name)===normalize(order.city)&&row.available)
  const city=chosenCity??(destination.recipient_city?String(destination.recipient_city):matches.length===1?String(matches[0].id):'')
  const zones=useLocations(account,'zones',city)
  const areas=useLocations(account,'areas',zone)
  const ready=!!city&&!!zone&&!cities.loading&&!zones.loading&&!cities.error&&!zones.error&&(!area||(!areas.loading&&!areas.error))
  useEffect(()=>{onReady(ready)},[ready,onReady])
  const selections=[
    {name:'recipient_city',value:city,list:cities,enabled:!!account,required:true,change:value=>{setCity(value);setZone('');setArea('')}},
    {name:'recipient_zone',value:zone,list:zones,enabled:!!city,required:true,change:value=>{setZone(value);setArea('')}},
    {name:'recipient_area',value:area,list:areas,enabled:!!zone,required:false,change:setArea},
  ]
  return <>{selections.map(field=><label key={field.name}>{fields.find(item=>item.name===field.name)?.label}{field.required?' *':''}
    <select name={field.name} value={field.value} required={field.required} disabled={busy||!field.enabled||field.list.loading||!!field.list.error} onChange={event=>field.change(event.target.value)}>
      <option value="">{field.list.loading?l.loading:l.blank}</option>{field.list.rows.map(row=><option key={row.id} value={row.id} disabled={!row.available}>{row.name}</option>)}
    </select>
    {field.list.error&&<span className="control-error" role="alert">{Object.values(field.list.error.fields||{}).flat().join(' ')||field.list.error.message}<button className="control-button small" type="button" disabled={busy} onClick={field.list.retry}>{l.refresh}</button></span>}
  </label>)}</>
}
