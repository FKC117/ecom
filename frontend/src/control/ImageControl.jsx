import { useCallback, useEffect, useRef, useState } from 'react'
import { controlRequest, modelPath } from './api'
import LiveImageCanvas from './LiveImageCanvas'

const defaults = () => ({crop:{x:0,y:0,width:1,height:1},rotate:0,flip_horizontal:false,flip_vertical:false,brightness:1,contrast:1,resize_width:0})

function ImageEditor({labels:l, field, initialEdits, initialPreview, previewImage, onApply, onClose}) {
  const dialog = useRef(null)
  const [edits,setEdits] = useState(initialEdits || defaults)
  const [source,setSource] = useState(null)
  const [cropping,setCropping] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  useEffect(() => {
    dialog.current.showModal()
    document.body.classList.add('modal-open')
    return ()=>document.body.classList.remove('modal-open')
  },[])
  useEffect(()=>{
    let cancelled=false
    // Always use the unedited source, even when reopening already-staged edits.
    previewImage({}).then((url)=>{
      if(cancelled)return
      const image=new Image()
      image.onload=()=>{if(!cancelled)setSource(image)}
      image.onerror=()=>{if(!cancelled)setError(l.error)}
      image.src=url
    }).catch((failure)=>{if(!cancelled&&failure.name!=='AbortError')setError(failure.message)})
    return ()=>{cancelled=true}
  },[previewImage,l.error])
  const change = (next) => {setEdits(next);setError('')}
  const cropChange = (key,value) => {
    const maximum=key==='x'||key==='y'?99.9:100
    const minimum=key==='x'||key==='y'?0:.1
    const crop = {...edits.crop,[key]:Math.max(minimum,Math.min(maximum,Number(value)))/100}
    crop.width = Math.min(crop.width,1-crop.x)
    crop.height = Math.min(crop.height,1-crop.y)
    change({...edits,crop})
  }
  const apply = async () => {
    setBusy(true);setError('')
    try {
      const url = await previewImage(edits)
      onApply(edits,url)
    } catch(failure) {setError(failure.message)}
    finally {setBusy(false)}
  }
  return <dialog ref={dialog} className="dialog control-image-dialog" aria-labelledby={`image-editor-${field.name}`} onKeyDown={(event)=>{if(event.key==='Enter')event.preventDefault()}} onCancel={(event)=>{event.preventDefault();if(!busy)onClose()}}>
    <div className="control-image-dialog-heading"><div><p className="eyebrow">{field.label}</p><h2 id={`image-editor-${field.name}`}>{l.image_editor}</h2></div><button className="icon-button" type="button" onClick={onClose} disabled={busy} aria-label={l.close}>×</button></div>
    <div className="control-image-editor-layout"><div className="control-image-workspace"><div className="control-live-toolbar"><span>{l.image_live_preview}</span><button type="button" className="control-button small" aria-pressed={cropping} disabled={!source||busy} onClick={()=>setCropping(!cropping)}>{cropping?l.image_finish_crop:l.image_adjust_crop}</button></div><div className="control-image-stage">{source ? <LiveImageCanvas source={source} edits={edits} cropping={cropping} onChange={change} labels={l} /> : initialPreview ? <img src={initialPreview} alt={l.image_preview} /> : <p>{l.image_empty}</p>}{(!source||busy)&&!error && <p role="status">{l.image_processing}</p>}</div>{cropping&&<p className="control-field-help">{l.image_drag_crop}</p>}</div>
      <fieldset className="control-image-adjustments" disabled={busy||!source}>
        <legend>{l.image_crop}</legend><p className="control-field-help">{l.image_crop_help}</p>
        <div className="control-image-crop-grid">{[['x',l.image_x],['y',l.image_y],['width',l.image_width],['height',l.image_height]].map(([key,label])=><label key={key}>{label}<input type="number" min={key==='x'||key==='y'?0:0.1} max={key==='x'||key==='y'?99.9:100} step="0.1" value={Math.round(edits.crop[key]*1000)/10} onChange={(event)=>cropChange(key,event.target.value)} /></label>)}</div>
        <label>{l.image_rotate}<select value={edits.rotate} onChange={(event)=>change({...edits,rotate:Number(event.target.value)})}>{[0,90,180,270].map((value)=><option value={value} key={value}>{value}°</option>)}</select></label>
        <label className="control-checkbox"><input type="checkbox" checked={edits.flip_horizontal} onChange={(event)=>change({...edits,flip_horizontal:event.target.checked})} /><span>{l.image_flip_horizontal}</span></label>
        <label className="control-checkbox"><input type="checkbox" checked={edits.flip_vertical} onChange={(event)=>change({...edits,flip_vertical:event.target.checked})} /><span>{l.image_flip_vertical}</span></label>
        {['brightness','contrast'].map((key)=><label key={key}>{l[`image_${key}`]} <output>{edits[key].toFixed(2)}</output><input type="range" aria-label={l[`image_${key}`]} min="0.5" max="1.5" step="0.05" value={edits[key]} onChange={(event)=>change({...edits,[key]:Number(event.target.value)})} /></label>)}
        <label>{l.image_resize}<input type="number" min="0" max={field.image_options.max_edge} step="1" value={edits.resize_width} onChange={(event)=>change({...edits,resize_width:Number(event.target.value)})} /></label><p className="control-field-help">{l.image_resize_help}</p>
        <button type="button" className="control-button" onClick={()=>change(defaults())}>{l.image_reset}</button>
      </fieldset>
    </div>
    {error && <p className="control-error" role="alert">{error}</p>}
    <div className="control-image-dialog-footer"><p className="control-muted">{l.image_saved_later}</p><div className="control-toolbar"><button type="button" className="control-button" disabled={busy} onClick={onClose}>{l.cancel}</button><button type="button" className="control-button primary" disabled={busy||!source} onClick={apply}>{busy?l.image_processing:l.image_apply}</button></div></div>
  </dialog>
}

export default function ImageControl({field:f,labels:l,model,recordId,attrs,editable,onDirty}) {
  const [file,setFile] = useState(null)
  const [preview,setPreview] = useState(f.file_url)
  const [applied,setApplied] = useState(null)
  const [open,setOpen] = useState(false)
  const [clear,setClear] = useState(false)
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const urls = useRef(new Set())
  const active = useRef(null)
  const uploadRevision = useRef(0)
  const imageEndpoint=modelPath(model,`image/${encodeURIComponent(f.name)}/`)
  useEffect(()=>()=>{active.current?.abort();urls.current.forEach((url)=>URL.revokeObjectURL(url))},[])
  const makePreview = useCallback(async (edits,source=file) => {
    active.current?.abort()
    const controller=new AbortController();active.current=controller
    const body=new FormData()
    if(recordId)body.set('pk',recordId)
    if(source)body.set('image',source)
    body.set('edits',JSON.stringify(edits || {}))
    const blob=await controlRequest(imageEndpoint,{method:'POST',body,responseType:'blob',signal:controller.signal})
    const url=URL.createObjectURL(blob);urls.current.add(url)
    return url
  },[file,recordId,imageEndpoint])
  const chooseFile=async(event)=>{
    const revision=++uploadRevision.current
    const chosen=event.target.files[0] || null
    setFile(chosen);setApplied(null);setClear(false);setError('');setOpen(false)
    if(!chosen){active.current?.abort();setPreview(f.file_url);setBusy(false);return}
    setBusy(true)
    try {const url=await makePreview({},chosen);if(revision===uploadRevision.current)setPreview(url)}
    catch(failure){if(failure.name!=='AbortError'&&revision===uploadRevision.current){setError(failure.message);setPreview('')}}
    finally {if(revision===uploadRevision.current)setBusy(false)}
  }
  return <>
    <div className="control-image-field">
      {!clear && preview && <a className="control-image-current" href={preview} target="_blank" rel="noreferrer"><img src={preview} alt={f.label} /></a>}
      <div className="control-image-field-controls"><input {...attrs} type="file" accept={f.image_options.accept} required={f.required&&!f.file_url} onChange={chooseFile} />
        <p className="control-field-help">{l.image_upload_help}</p><p className="control-field-help">{l.image_upload_limit}: {f.image_options.max_bytes/(1024*1024)} {l.image_megabytes}</p>
        {editable && <div className="control-toolbar"><button type="button" className="control-button" disabled={attrs.disabled||busy||clear||(!file&&!f.file_url)} onClick={()=>setOpen(true)}>{l.edit_image}</button>{f.file_url&&!f.required&&<label className="control-checkbox"><input type="checkbox" name={`${f.name}-clear`} checked={clear} disabled={attrs.disabled} onChange={(event)=>{setClear(event.target.checked);if(event.target.checked)setApplied(null)}} /><span>{l.remove_file}</span></label>}</div>}
        {busy&&<p role="status">{l.image_processing}</p>}{applied&&<p className="control-image-pending" role="status">{l.image_pending}</p>}{error&&<p className="control-field-error" role="alert">{error}</p>}
      </div>
    </div>
    <input type="hidden" name={`${f.name}__edits`} value={applied?JSON.stringify(applied):''} disabled={attrs.disabled} />
    {open&&<ImageEditor labels={l} field={f} initialEdits={applied} initialPreview={preview} previewImage={makePreview} onClose={()=>setOpen(false)} onApply={(edits,url)=>{setApplied(edits);setPreview(url);setOpen(false);onDirty()}} />}
  </>
}
