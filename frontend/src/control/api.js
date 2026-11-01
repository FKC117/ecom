let csrfToken = ''

export function setCsrfToken(token) { csrfToken = token || '' }

export async function controlRequest(path, options = {}) {
  const {responseType, ...requestOptions} = options
  const response = await fetch(path.startsWith("/") ? path : `/api/control/${path}`, {
    credentials: 'same-origin',
    ...requestOptions,
    headers: { ...(options.method && options.method !== 'GET' ? { 'X-CSRFToken': csrfToken } : {}), ...options.headers },
  })
  if (response.ok && responseType === 'blob') return response.blob()
  const data = await response.json().catch(() => ({}))
  if (data.csrf_token) setCsrfToken(data.csrf_token)
  if (!response.ok) {
    const error = new Error(data.error || String(response.status))
    error.status = response.status
    error.fields = data.errors || {}
    throw error
  }
  if (response.ok && options.method && options.method !== 'GET' && path.startsWith('models/') && !path.includes('/image/')) {
    try { localStorage.setItem('storefront-content-revision', `${Date.now()}-${Math.random()}`) } catch { /* Returning focus also refreshes the storefront. */ }
  }
  return data
}

export function modelPath(model, suffix = '') {
  return `models/${encodeURIComponent(model.app)}/${encodeURIComponent(model.model)}/${suffix}`
}
