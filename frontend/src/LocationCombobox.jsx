import {useEffect,useId,useRef,useState} from 'react'
import {controlRequest} from './control/api'

export default function LocationCombobox({name,label,value,onChange,cityId,zoneId,disabled,required=true,labels:l,errors=[],submitName=false}) {
  const id=useId(),input=useRef(null)
  const [draft,setDraft]=useState(null),[open,setOpen]=useState(false),[rows,setRows]=useState([]),[active,setActive]=useState(-1)
  const [state,setState]=useState('idle'),[page,setPage]=useState(1),[more,setMore]=useState(false)
  const text=draft??value?.name??''
  const query=draft??''
  useEffect(()=>{input.current?.setCustomValidity(text&&!value?l.location_select_match:'')},[text,value,l.location_select_match])
  useEffect(()=>{
    if(!open||disabled)return
    const controller=new AbortController()
    const timer=setTimeout(()=>{
      setState('loading')
      controlRequest(`/api/shop/locations/?kind=${name}&q=${encodeURIComponent(query)}&page=${page}${name!=='city'?`&city=${cityId}`:''}${name==='area'?`&zone=${zoneId}`:''}`,{signal:controller.signal}).then(data=>{setRows(current=>page===1?data.results:[...current,...data.results]);setMore(data.has_more===true);setState('ready')}).catch(failure=>{if(failure.name!=='AbortError'){setState('error');setMore(false)}})
    },query?200:0)
    return()=>{clearTimeout(timer);controller.abort()}
  },[query,page,open,disabled,name,cityId,zoneId])
  function choose(row){onChange(row);setDraft(null);setOpen(false);setRows([]);setPage(1);setActive(-1);setState('idle');input.current?.focus()}
  function browse(){if(open){setOpen(false);return}setDraft(null);setRows([]);setPage(1);setActive(-1);setState('idle');setOpen(true);input.current?.focus()}
  function keyDown(event){
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();setOpen(true);setActive(current=>rows.length?(current<0?(event.key==='ArrowDown'?0:rows.length-1):(current+(event.key==='ArrowDown'?1:-1)+rows.length)%rows.length):-1)}
    else if(event.key==='Enter'&&open){event.preventDefault();if(active>=0&&rows[active])choose(rows[active])}
    else if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false)}
  }
  return <div className="location-field"><label htmlFor={id}><span>{label}{required&&<span className="required-marker" aria-hidden="true"> *</span>}</span></label>
    <div className="location-combobox" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setOpen(false)}}>
      <input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open&&!disabled} aria-controls={`${id}-list`} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} aria-describedby={`${id}-hint`} aria-invalid={errors.length>0||undefined} autoComplete="off" value={text} required={required} disabled={disabled} placeholder={l[`search_${name}`]} onFocus={()=>{setOpen(true);setPage(1)}} onChange={event=>{setDraft(event.target.value);onChange(null);setRows([]);setPage(1);setMore(false);setState('idle');setActive(-1);setOpen(true)}} onKeyDown={keyDown}/>
      <button type="button" className="location-browse" disabled={disabled} aria-label={l[`choose_${name}`]} aria-expanded={open&&!disabled} aria-controls={`${id}-list`} onMouseDown={event=>event.preventDefault()} onClick={browse}>▾</button>
      <input type="hidden" name={name} value={submitName?value?.name??'':value?.id??''} disabled={disabled}/>
      {open&&!disabled&&<div className="location-results"><div id={`${id}-list`} role="listbox" aria-label={label}>{rows.map((row,index)=><div key={row.id} id={`${id}-${index}`} role="option" aria-selected={value?.id===row.id||active===index} className={active===index?'location-option active':'location-option'} onMouseDown={event=>event.preventDefault()} onClick={()=>choose(row)}>{row.name}</div>)}</div><div className="location-status" role="status">{state==='error'?l.location_search_error:state==='ready'&&!rows.length?l.location_no_matches:state==='loading'||state==='idle'?l.location_searching:''}</div>{more&&<button type="button" className="control-button small" disabled={state==='loading'} onMouseDown={event=>event.preventDefault()} onClick={()=>setPage(current=>current+1)}>{l.location_more}</button>}</div>}
    </div><span className="control-muted location-hint" id={`${id}-hint`}>{disabled?l[name==='zone'?'location_city_first':'location_zone_first']:l.location_select_hint}</span>{errors.map(message=><span className="control-error" key={message}>{message}</span>)}
  </div>
}
