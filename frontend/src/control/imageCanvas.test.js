import test from 'node:test'
import assert from 'node:assert/strict'
import {moveCrop,resizeCrop} from './imageCanvas.js'

test('dragging keeps the complete crop inside the source image',()=>{
  const crop={x:.2,y:.3,width:.4,height:.5}
  assert.deepEqual(moveCrop(crop,-10,10),{x:0,y:.5,width:.4,height:.5})
  assert.deepEqual(moveCrop(crop,10,-10),{x:.6,y:0,width:.4,height:.5})
})

test('corner resizing cannot invert or escape the image',()=>{
  const crop={x:.2,y:.2,width:.4,height:.4}
  for(const handle of ['nw','ne','sw','se','n','s','w','e']){
    for(const delta of [-10,10]){
      const result=resizeCrop(crop,handle,delta,delta)
      assert.ok(result.x>=0&&result.y>=0)
      assert.ok(result.width>0&&result.height>0)
      assert.ok(result.x+result.width<=1.000001&&result.y+result.height<=1.000001)
    }
  }
})

test('very small numeric crops remain valid when a handle is dragged',()=>{
  const result=resizeCrop({x:0,y:0,width:.001,height:.001},'nw',10,10)
  assert.ok(result.x>=0&&result.y>=0&&result.width>0&&result.height>0)
})
