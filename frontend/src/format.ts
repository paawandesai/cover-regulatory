import type { Item, Label } from './types'

export const LABEL_TEXT: Record<Label, string> = {
  verified: 'Verified parcel data',
  derived: 'Derived from rule',
  interpretive: 'Interpretation, confirm with City',
  uncited: 'No cited source',
  withheld: 'Not modeled here',
  approximate: 'Approximate (imagery)',
  mock: 'MOCK data',
}

const num = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })

const UNITS: Record<string, string> = { ft: 'ft', sqft: 'sq ft' }

// Wording for yes/no results, per item. Anything not listed falls back to Yes / No.
const BOOLEAN_TEXT: Record<string, [string, string]> = {
  guest_house: ['Allowed', 'Not allowed'],
  lot_minimums: ['Meets minimums', 'Below minimums'],
}

export function formatValue(item: Item): string {
  const v = item.value
  if (v === null || v === undefined) return 'Not determined'
  if (typeof v === 'boolean') {
    if (item.family === 'flag') return v ? 'May apply' : 'Does not apply'
    const [yes, no] = BOOLEAN_TEXT[item.id] ?? ['Yes', 'No']
    return v ? yes : no
  }
  const unit = item.unit ? ` ${UNITS[item.unit] ?? item.unit}` : ''
  if (typeof v === 'number') {
    const prefix = item.family === 'adu' || item.family === 'jadu' ? 'up to ' : ''
    return `${prefix}${num(v)}${unit}`
  }
  if (typeof v === 'string') return `${v}${unit}`
  return JSON.stringify(v)
}

export function formatExisting(v: unknown): string {
  if (!v || typeof v !== 'object') return 'Not recorded'
  const e = v as Record<string, number | null>
  const parts: string[] = []
  if (e.sqft_main) parts.push(`${num(e.sqft_main)} sq ft`)
  if (e.units) parts.push(`${e.units} unit${e.units === 1 ? '' : 's'}`)
  if (e.bedrooms) parts.push(`${e.bedrooms} bd`)
  if (e.bathrooms) parts.push(`${e.bathrooms} ba`)
  if (e.year_built) parts.push(`built ${e.year_built}`)
  return parts.length ? parts.join(', ') : 'Not recorded'
}

export function formatApn(apn: string): string {
  return /^\d{10}$/.test(apn) ? `${apn.slice(0, 4)}-${apn.slice(4, 7)}-${apn.slice(7)}` : apn
}

export const formatDate = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : 'unknown')

/** "LAMC 12.08 C.1" for the first citation, plus a count when there are several distinct sections. */
export function citeLabel(item: Item): string {
  const sections = [...new Set(item.citations.map((c) => c.section_id))]
  if (!sections.length) return item.label === 'verified' || item.label === 'approximate' ? 'Parcel data' : ''
  return sections.length > 1 ? `${sections[0]} +${sections.length - 1}` : sections[0]
}
