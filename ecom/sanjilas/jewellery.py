from .shop_copy import shop_labels


def details(product, variant=None, labels=None):
    labels = {**shop_labels(), **(labels or {})}
    rows = []
    for field in ['material','plating','gemstone','stone_origin','stone_colour','color','size','dimensions','weight_grams','adjustable','closure','package_contents','warranty']:
        value = getattr(variant,field,None) if variant else None
        if isinstance(value,str): value=value.strip()
        if value is None or value == '': value = getattr(product,field,None)
        if isinstance(value,str): value=value.strip()
        if value is None or value == '': continue
        if field == 'adjustable': value = labels['detail_yes'] if value else labels['detail_no']
        elif field == 'weight_grams': value = f'{value.normalize():f} {labels["weight_unit"]}'
        rows.append({'key':field,'label':labels.get('detail_'+field,labels.get(field,field)), 'value':str(value)})
    sku = variant.sku if variant else product.sku
    if sku: rows.append({'key':'sku','label':labels.get('sku',labels['invoice_sku']),'value':sku})
    return rows
