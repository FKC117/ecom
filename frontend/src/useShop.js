import { useCallback, useEffect, useRef, useState } from 'react'
import { controlRequest } from './control/api'

export default function useShop() {
  const version=useRef(0)
  const [cart,setCart]=useState(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const refresh=useCallback(async()=>{
    const revision=version.current
    const next=await controlRequest('/api/shop/cart/')
    if(revision===version.current)setCart(next)
    return next
  },[])
  useEffect(()=>{Promise.resolve().then(refresh).catch((failure)=>setError(failure.message))},[refresh])
  const mutate=async(path,values)=>{
    version.current+=1
    setBusy(true);setError('')
    const body=new FormData()
    Object.entries(values).forEach(([key,value])=>body.set(key,value??''))
    try {
      const result=await controlRequest(`/api/shop/${path}`,{method:'POST',body})
      if(result.items)setCart((current)=>({...current,...result}))
      if(result.cart)setCart((current)=>({...current,...result.cart}))
      return result
    } catch(failure) {setError(failure.message);throw failure}
    finally {version.current+=1;setBusy(false)}
  }
  return {cart,busy,error,refresh,mutate,setError}
}
