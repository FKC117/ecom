export function applyBranding(site) {
  document.title = site.meta_title
  const meta = (attribute, key, value) => {
    let element = document.head.querySelector(`meta[${attribute}="${key}"]`)
    if (!value) { element?.remove(); return }
    if (!element) {
      element = document.createElement('meta')
      element.setAttribute(attribute, key)
      document.head.append(element)
    }
    element.content = value
  }
  const link = (rel, value) => {
    let element = document.head.querySelector(`link[rel="${rel}"]`)
    if (!value) { element?.remove(); return }
    if (!element) {
      element = document.createElement('link')
      element.rel = rel
      document.head.append(element)
    }
    element.href = value
  }
  for (const [key, value] of Object.entries({
    description: site.meta_description, keywords: site.meta_keywords, robots: site.robots,
    'twitter:card': site.twitter_card, 'twitter:site': site.twitter_site,
    'twitter:title': site.twitter_title, 'twitter:description': site.twitter_description,
    'twitter:image': site.twitter_image, 'twitter:image:alt': site.twitter_image_alt,
  })) meta('name', key, value)
  for (const [key, value] of Object.entries({
    'og:site_name': site.site_name, 'og:title': site.og_title,
    'og:description': site.og_description, 'og:type': site.og_type,
    'og:url': site.site_url, 'og:image': site.og_image, 'og:image:alt': site.og_image_alt,
  })) meta('property', key, value)
  link('icon', site.favicon)
  link('apple-touch-icon', site.apple_touch_icon)
  link('canonical', site.site_url)
}
