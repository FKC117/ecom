import {useEffect,useId,useRef,useState} from 'react'
import {controlRequest} from './control/api'

export default function LocationCombobox({name,label,value,onChange,cityId,disabled,required=true,labels:l,errors=[]}) {
  const id=useId(),input=useRef(null)
  const [draft,setDraft]=useState(null),[open,setOpen]=useState(false),[rows,setRows]=useState([]),[active,setActive]=useState(-1)
  const [state,setState]=useState('idle')
  const text=draft??value?.name??''
  useEffect(()=>{input.current?.setCustomValidity(required&&text&&!value?l.location_select_match:'')},[required,text,value,l.location_select_match])
  useEffect(()=>{
    if(!open||disabled||!text.trim())return
    const controller=new AbortController()
    const timer=setTimeout(()=>{
      setState('loading')
      controlRequest(`/api/shop/locations/?kind=${name}&q=${encodeURIComponent(text)}${name==='area'?`&city=${cityId}`:''}`,{signal:controller.signal}).then((data)=>{setRows(data.results);setActive(-1);setState('ready')}).catch((failure)=>{if(failure.name!=='AbortError'){setRows([]);setState('error')}})
    },200)
    return()=>{clearTimeout(timer);controller.abort()}
  },[text,open,disabled,name,cityId])
  function choose(row){onChange(row);setDraft(null);setOpen(false);setRows([]);setActive(-1);setState('idle');input.current?.focus()}
  function keyDown(event){
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();setOpen(true);setActive((current)=>rows.length?(current<0?(event.key==='ArrowDown'?0:rows.length-1):(current+(event.key==='ArrowDown'?1:-1)+rows.length)%rows.length):-1)}
    else if(event.key==='Enter'&&open){event.preventDefault();if(active>=0&&rows[active])choose(rows[active])}
    else if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false)}
    else if(event.key==='Tab')setOpen(false)
  }
  return <div className="location-field"><label htmlFor={id}><span>{label}{required&&<span className="required-marker" aria-hidden="true"> *</span>}</span></label><div className="location-combobox"><input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={open&&!disabled} aria-controls={`${id}-list`} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} aria-describedby={`${id}-hint`} aria-invalid={errors.length>0||undefined} autoComplete="off" value={text} required={required} disabled={disabled} placeholder={l[name==='city'?'search_city':'search_area']} onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onChange={(event)=>{setDraft(event.target.value);onChange(null);setRows([]);setState('idle');setActive(-1);setOpen(true)}} onKeyDown={keyDown}/><input type="hidden" name={name} value={value?.id??''} disabled={disabled}/>{open&&!disabled&&<div className="location-results" id={`${id}-list`} role="listbox" aria-label={label}>{state==='ready'&&rows.map((row,index)=><div key={row.id} id={`${id}-${index}`} role="option" aria-selected={active===index} className={active===index?'location-option active':'location-option'} onMouseDown={(event)=>event.preventDefault()} onClick={()=>choose(row)}>{row.name}</div>)}<div className="location-status" role="status">{!text.trim()?l.location_type_hint:state==='error'?l.location_search_error:state==='ready'&&!rows.length?l.location_no_matches:state==='loading'||state==='idle'?l.location_searching:''}</div></div>}</div><span className="control-muted location-hint" id={`${id}-hint`}>{disabled&&name==='area'?l.location_city_first:l.location_select_hint}</span>{errors.map((message)=><span className="control-error" key={message}>{message}</span>)}</div>
}
