import { useEffect, useRef } from 'react'
import { clamp, moveCrop, paintCrop, paintLive, resizeCrop } from './imageCanvas'

export default function LiveImageCanvas({source,edits,cropping,onChange,labels:l}) {
  const main=useRef(null)
  const result=useRef(null)
  const drag=useRef(null)
  useEffect(()=>{
    const frame=requestAnimationFrame(()=>{
      if(!main.current)return
      if(cropping){paintCrop(main.current,source,edits);if(result.current)paintLive(result.current,source,edits)}
      else paintLive(main.current,source,edits)
    })
    return ()=>cancelAnimationFrame(frame)
  },[source,edits,cropping])
  const point=(event)=>{
    const rect=main.current.getBoundingClientRect()
    return {x:clamp((event.clientX-rect.left)/rect.width,0,1),y:clamp((event.clientY-rect.top)/rect.height,0,1),rect}
  }
  const start=(event)=>{
    if(!cropping||event.button!==0)return
    event.preventDefault()
    const p=point(event),c=edits.crop
    const nearX=20/p.rect.width,nearY=20/p.rect.height
    const inX=p.x>=c.x-nearX&&p.x<=c.x+c.width+nearX
    const inY=p.y>=c.y-nearY&&p.y<=c.y+c.height+nearY
    let handle=''
    if(inX&&inY){
      if(Math.abs(p.y-c.y)<nearY)handle+='n'
      else if(Math.abs(p.y-c.y-c.height)<nearY)handle+='s'
      if(Math.abs(p.x-c.x)<nearX)handle+='w'
      else if(Math.abs(p.x-c.x-c.width)<nearX)handle+='e'
    }
    const inside=p.x>=c.x&&p.x<=c.x+c.width&&p.y>=c.y&&p.y<=c.y+c.height
    drag.current={start:p,crop:{...c},handle:handle||(inside?'move':'new')}
    main.current.setPointerCapture(event.pointerId)
  }
  const move=(event)=>{
    if(!drag.current)return
    event.preventDefault()
    const p=point(event),d=drag.current,dx=p.x-d.start.x,dy=p.y-d.start.y
    let crop
    if(d.handle==='move')crop=moveCrop(d.crop,dx,dy)
    else if(d.handle==='new'){
      const x=clamp(Math.min(d.start.x,p.x),0,.99),y=clamp(Math.min(d.start.y,p.y),0,.99)
      crop={x,y,width:clamp(Math.abs(dx),.01,1-x),height:clamp(Math.abs(dy),.01,1-y)}
    }else crop=resizeCrop(d.crop,d.handle,dx,dy)
    onChange({...edits,crop})
  }
  const stop=(event)=>{drag.current=null;if(main.current.hasPointerCapture(event.pointerId))main.current.releasePointerCapture(event.pointerId)}
  const key=(event)=>{
    if(!cropping||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return
    event.preventDefault()
    const step=event.shiftKey ? .1 : .01
    onChange({...edits,crop:moveCrop(edits.crop,event.key==='ArrowLeft'?-step:event.key==='ArrowRight'?step:0,event.key==='ArrowUp'?-step:event.key==='ArrowDown'?step:0)})
  }
  return <div className="control-live-canvases">
    <div className="control-canvas-frame"><canvas ref={main} className={cropping?'control-crop-canvas':'control-live-canvas'} role="img" aria-label={cropping?l.image_crop_selection:l.image_live_preview} tabIndex={cropping?0:undefined} onPointerDown={start} onPointerMove={move} onPointerUp={stop} onPointerCancel={stop} onKeyDown={key} /></div>
    {cropping&&<div className="control-crop-result"><p>{l.image_live_preview}</p><canvas ref={result} role="img" aria-label={l.image_live_preview} /></div>}
  </div>
}
