import { reactive } from 'vue'
import type { Assessment, Chunk, Fragment } from './types'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

// Hosted demo gate state; App.vue shows the invite form while `needed` is true.
export const invite = reactive({ checked: false, required: false, needed: false })

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { Accept: 'application/json', ...init?.headers } })
  if (!res.ok) {
    if (res.status === 401 && res.headers.get('content-type')?.includes('json')) {
      const body = await res.clone().json().catch(() => null)
      if (body?.detail === 'invite_required') invite.needed = true
    }
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const assess = (q: string) => request<Assessment>(`/api/assess?q=${encodeURIComponent(q)}`)

export const chunk = (id: string) => request<Chunk>(`/api/chunks/${encodeURIComponent(id)}`)

export const nearby = (apn: string) => request<GeoJSON.FeatureCollection>(`/api/parcels/${apn}/nearby`)

export const sendFeedback = (body: { apn: string | null; item_id: string | null; kind: string; comment: string | null }) =>
  request<{ id: number; status: string }>('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

// Admin calls use HTTP Basic credentials held in memory only (never written to storage).
let basic: string | null = null
export const setCredentials = (user: string, password: string) => {
  basic = 'Basic ' + btoa(unescape(encodeURIComponent(`${user}:${password}`)))
}
export const clearCredentials = () => {
  basic = null
}
export const hasCredentials = () => basic !== null
const auth = (): Record<string, string> => (basic ? { Authorization: basic } : {})

export const fragments = (status: string) =>
  request<Fragment[]>(`/api/admin/fragments?status=${encodeURIComponent(status)}`, { headers: auth() })

export const decide = (id: number, decision: 'approved' | 'rejected', note: string | null) =>
  request<{ id: number; status: string }>(`/api/admin/fragments/${id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth() },
    body: JSON.stringify({ decision, note }),
  })

export async function checkInvite() {
  const r = await request<{ required: boolean; ok: boolean }>('/api/invite')
  Object.assign(invite, { checked: true, required: r.required, needed: r.required && !r.ok })
}

export async function submitInvite(code: string) {
  await request<{ ok: boolean }>('/api/invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  invite.needed = false
}
