import { reactive } from 'vue'
import type { Assessment, Chunk, Fragment, ProjectInputs, Report, ReportRow, ChatAnswer, Me, AuditRow, SourceRow } from './types'

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
      const body = await res
        .clone()
        .json()
        .catch(() => null)
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

export const assess = (q: string, project: Partial<ProjectInputs> = {}) => {
  const params = new URLSearchParams({ q })
  for (const [k, v] of Object.entries(project)) if (v !== undefined && v !== null) params.set(k, String(v))
  return request<Assessment>(`/api/assess?${params}`)
}

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

export interface FeedbackRow {
  id: number
  created_at: string
  apn: string | null
  item_id: string | null
  kind: string
  comment: string | null
  status: 'new' | 'reviewed' | 'dismissed'
  reviewed_by: string | null
  reviewed_at: string | null
}

export const feedbackList = (status: FeedbackRow['status']) =>
  request<FeedbackRow[]>(`/api/admin/feedback?status=${status}`, { headers: auth() })

export const decideFeedback = (id: number, status: 'reviewed' | 'dismissed') =>
  request<{ id: number; status: string }>(`/api/admin/feedback/${id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth() },
    body: JSON.stringify({ status }),
  })

// Client reports: created by anyone with the invite, readable by link only after a reviewer signs.
export const createReport = (apn: string, project: Partial<ProjectInputs>) =>
  request<{ token: string; status: string }>('/api/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apn, project }),
  })

export const getReport = (token: string) => request<Report>(`/api/reports/${encodeURIComponent(token)}`)

export const reportList = (status: Report['status']) => request<ReportRow[]>(`/api/admin/reports?status=${status}`, { headers: auth() })

export const previewReport = (token: string) => request<Report>(`/api/admin/reports/${encodeURIComponent(token)}`, { headers: auth() })

export const signReport = (
  token: string,
  body: { signer_name: string; signer_license: string; note: string | null; statement_accepted: boolean },
) =>
  request<{ token: string; status: string }>(`/api/admin/reports/${encodeURIComponent(token)}/sign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth() },
    body: JSON.stringify(body),
  })

export const withdrawReport = (token: string) =>
  request<{ token: string; status: string }>(`/api/admin/reports/${encodeURIComponent(token)}/withdraw`, {
    method: 'POST',
    headers: auth(),
  })

// Follow-up question: answered only from cited text, quotes checked on the server. Nothing is stored.
export const askChat = (apn: string, question: string) =>
  request<ChatAnswer>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apn, question }),
  })

export const whoAmI = () => request<Me>('/api/admin/me', { headers: auth() })

export const auditLog = (objectType: AuditRow['object_type'] | '') =>
  request<AuditRow[]>(`/api/admin/audit${objectType ? `?object_type=${objectType}` : ''}`, { headers: auth() })

export const sourceChecks = () => request<SourceRow[]>('/api/admin/sources', { headers: auth() })
