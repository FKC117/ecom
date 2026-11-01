export function priceText(item, labels, field = 'discounted_price') {
  const amount = item[field] === undefined ? item.price : item[field]
  if (amount === null) return labels.price_on_request
  try {
    return new Intl.NumberFormat(labels.currency_locale, { style: 'currency', currency: item.currency, minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(Number(amount))
  } catch { return `${item.currency} ${amount}` }
}

