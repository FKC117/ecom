import JsBarcode from 'jsbarcode'
import QRCode from 'qrcode'

export function consignmentCodes(value){
  if(!value||!/^[\x20-\x7e]+$/.test(value))throw new Error('Invalid consignment')
  const barcode={}
  JsBarcode(barcode,value,{format:'CODE128',displayValue:false})
  const bits=barcode.encodings.map(encoding=>encoding.data).join('')
  let bars=''
  for(let index=0;index<bits.length;){
    if(bits[index]!=='1'){index++;continue}
    const start=index
    while(bits[index]==='1')index++
    bars+=`M${start+10} 5h${index-start}v50h-${index-start}z`
  }
  const qr=QRCode.create(value,{errorCorrectionLevel:'M'})
  let modules=''
  for(let y=0;y<qr.modules.size;y++)for(let x=0;x<qr.modules.size;x++)if(qr.modules.get(y,x))modules+=`M${x+4} ${y+4}h1v1h-1z`
  return {barcodePath:bars,barcodeWidth:bits.length+20,qrPath:modules,qrSize:qr.modules.size+8}
}
