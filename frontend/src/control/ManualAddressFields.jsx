import {useState} from 'react'
import LocationCombobox from '../LocationCombobox'

export default function ManualAddressFields({records={},existing,labels:l,busy}){
  const initial=(name)=>existing?.[name]?{id:records[name]?.id??'',name:existing[name]}:null
  const [city,setCity]=useState(()=>initial('city'))
  const [zone,setZone]=useState(()=>initial('zone'))
  const [area,setArea]=useState(()=>initial('area'))
  const legacy=!!existing&&!existing.zone&&city?.name===existing.city&&!zone&&area?.name===existing.area
  return <>
    <LocationCombobox name="city" label={l.manual_city} value={city} onChange={value=>{setCity(value);setZone(null);setArea(null)}} required={false} disabled={busy} labels={l} submitName/>
    <LocationCombobox key={`zone-${city?.id??''}`} name="zone" label={l.customer_zone} value={zone} onChange={value=>{setZone(value);setArea(null)}} cityId={city?.id} required={!!city&&!legacy} disabled={busy||!city} labels={l} submitName/>
    <LocationCombobox key={`area-${city?.id??''}-${zone?.id??''}`} name="area" label={l.customer_area} value={area} onChange={setArea} cityId={city?.id} zoneId={zone?.id} required={!!city&&!legacy} disabled={busy||!city||(!zone&&!legacy)} labels={l} submitName/>
  </>
}
