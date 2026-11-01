// Local, bounded-resolution previews. Django remains the final encoding authority.
export const clamp = (value, low, high) => Math.min(high, Math.max(low, value))

export function moveCrop(crop, dx, dy) {
  return {...crop, x:clamp(crop.x+dx,0,1-crop.width), y:clamp(crop.y+dy,0,1-crop.height)}
}

export function resizeCrop(crop, handle, dx, dy) {
  let left=crop.x,top=crop.y,right=crop.x+crop.width,bottom=crop.y+crop.height
  const minWidth=Math.min(.01,crop.width),minHeight=Math.min(.01,crop.height)
  if(handle.includes('w'))left=clamp(left+dx,0,right-minWidth)
  if(handle.includes('e'))right=clamp(right+dx,left+minWidth,1)
  if(handle.includes('n'))top=clamp(top+dy,0,bottom-minHeight)
  if(handle.includes('s'))bottom=clamp(bottom+dy,top+minHeight,1)
  return {x:left,y:top,width:right-left,height:bottom-top}
}

function surface(width,height) {
  const canvas=document.createElement('canvas')
  canvas.width=Math.max(1,Math.round(width));canvas.height=Math.max(1,Math.round(height))
  return canvas
}

function oriented(source,edits) {
  const rotated=edits.rotate%180!==0
  const width=rotated?source.naturalHeight:source.naturalWidth
  const height=rotated?source.naturalWidth:source.naturalHeight
  const scale=Math.min(1,1000/Math.max(width,height))
  const canvas=surface(width*scale,height*scale)
  const context=canvas.getContext('2d')
  context.translate(canvas.width/2,canvas.height/2)
  context.scale(edits.flip_horizontal?-1:1,edits.flip_vertical?-1:1)
  context.rotate(edits.rotate*Math.PI/180)
  context.drawImage(source,-source.naturalWidth*scale/2,-source.naturalHeight*scale/2,source.naturalWidth*scale,source.naturalHeight*scale)
  return canvas
}

function adjustments(canvas,edits) {
  if(edits.brightness===1&&edits.contrast===1)return
  const context=canvas.getContext('2d',{willReadFrequently:true})
  const pixels=context.getImageData(0,0,canvas.width,canvas.height)
  const data=pixels.data
  let sum=0
  // Mirror Pillow's brightness followed by mean-grey contrast, keeping alpha intact.
  for(let i=0;i<data.length;i+=4){
    for(let c=0;c<3;c++)data[i+c]=clamp(Math.floor(data[i+c]*edits.brightness),0,255)
    sum+=Math.floor((19595*data[i]+38470*data[i+1]+7471*data[i+2]+32768)/65536)
  }
  if(edits.contrast!==1){
    const mean=Math.round(sum/(data.length/4))
    for(let i=0;i<data.length;i+=4)for(let c=0;c<3;c++)data[i+c]=clamp(Math.floor(mean+(data[i+c]-mean)*edits.contrast),0,255)
  }
  context.putImageData(pixels,0,0)
}

export function paintLive(canvas,source,edits) {
  const full=oriented(source,edits)
  const crop=edits.crop
  const left=Math.round(crop.x*full.width),top=Math.round(crop.y*full.height)
  const width=Math.max(1,Math.round((crop.x+crop.width)*full.width)-left)
  const height=Math.max(1,Math.round((crop.y+crop.height)*full.height)-top)
  const result=surface(width,height)
  result.getContext('2d').drawImage(full,left,top,width,height,0,0,result.width,result.height)
  adjustments(result,edits)
  const rotated=edits.rotate%180!==0
  const sourceWidth=rotated?source.naturalHeight:source.naturalWidth
  const requested=edits.resize_width>=32?edits.resize_width:Infinity
  const outputWidth=Math.min(1000,sourceWidth*crop.width,requested)
  canvas.width=Math.max(1,Math.round(outputWidth))
  canvas.height=Math.max(1,Math.round(outputWidth*result.height/result.width))
  canvas.getContext('2d').drawImage(result,0,0,canvas.width,canvas.height)
  // Exposed in the DOM for accessibility/debugging without affecting layout.
  canvas.dataset.cropWidth=String(Math.round(sourceWidth*crop.width))
}

export function paintCrop(canvas,source,edits) {
  const full=oriented(source,edits)
  adjustments(full,edits)
  canvas.width=full.width;canvas.height=full.height
  const context=canvas.getContext('2d')
  context.drawImage(full,0,0)
  const {x,y,width,height}=edits.crop
  const left=x*canvas.width,top=y*canvas.height,w=width*canvas.width,h=height*canvas.height
  context.fillStyle='rgba(0,0,0,.55)'
  context.fillRect(0,0,canvas.width,top)
  context.fillRect(0,top,left,h)
  context.fillRect(left+w,top,canvas.width-left-w,h)
  context.fillRect(0,top+h,canvas.width,canvas.height-top-h)
  const ratio=canvas.width/(canvas.getBoundingClientRect().width||canvas.width)
  context.strokeStyle='#fff';context.lineWidth=2*ratio
  context.strokeRect(left,top,w,h)
  context.lineWidth=ratio;context.setLineDash([5*ratio,5*ratio])
  for(const fraction of [1/3,2/3]){
    context.beginPath();context.moveTo(left+w*fraction,top);context.lineTo(left+w*fraction,top+h);context.stroke()
    context.beginPath();context.moveTo(left,top+h*fraction);context.lineTo(left+w,top+h*fraction);context.stroke()
  }
  context.setLineDash([])
  const handle=10*ratio
  for(const px of [left,left+w/2,left+w])for(const py of [top,top+h/2,top+h]){
    if(px===left+w/2&&py===top+h/2)continue
    context.fillStyle='#fff';context.fillRect(px-handle/2,py-handle/2,handle,handle)
    context.strokeStyle='#222';context.lineWidth=ratio;context.strokeRect(px-handle/2,py-handle/2,handle,handle)
  }
}
