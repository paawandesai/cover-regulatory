import { describe, expect, it } from 'vitest'
import { authority, authorityOf, chapterName, citeLabel, formatApn, formatExisting, formatValue, labelText } from '../format'
import type { Assessment, Item } from '../types'

const item = (over: Partial<Item>): Item => ({
  id: 'x',
  family: 'r1_envelope',
  title: 't',
  value: null,
  unit: null,
  label: 'interpretive',
  rule_id: null,
  coverage: null,
  explanation: null,
  citations: [],
  source: null,
  label_text: '',
  ...over,
})

describe('formatValue', () => {
  it('formats numbers with units', () => {
    expect(formatValue(item({ value: 3645, unit: 'sqft' }))).toBe('3,645 sq ft')
    expect(formatValue(item({ value: 20, unit: 'ft' }))).toBe('20 ft')
  })
  it('prefixes ADU limits with "up to"', () => {
    expect(formatValue(item({ family: 'adu', value: 800, unit: 'sqft' }))).toBe('up to 800 sq ft')
  })
  it('never shows a missing value as zero', () => {
    expect(formatValue(item({ value: null, unit: 'ft', label: 'uncited' }))).toBe('Not determined')
  })
  it('uses item-specific wording for yes/no', () => {
    expect(formatValue(item({ id: 'guest_house', family: 'guest_house', value: false }))).toBe('Not allowed')
    expect(formatValue(item({ family: 'flag', value: true }))).toBe('May apply')
  })
})

describe('helpers', () => {
  it('formats APNs', () => expect(formatApn('2121005008')).toBe('2121-005-008'))
  it('reports unrecorded buildings', () =>
    expect(formatExisting({ year_built: null, units: null, sqft_main: null })).toBe('Not recorded'))
  it('labels several distinct sections', () => {
    const c = (section_id: string) => ({
      fragment_id: 1, chunk_id: 'c', section_id, quote: 'q', quote_start: 0, quote_end: 1,
      review_status: 'pending', source_url: null, retrieved_at: null,
    })
    expect(citeLabel(item({ citations: [c('LAMC 12.08 C.2'), c('LAMC 12.08 C.2'), c('LAMC 12.21 C.10')] }))).toBe(
      'LAMC 12.08 C.2 +1',
    )
  })
  it('names the County for an unincorporated parcel', () => {
    const a = (value: string) => ({ parcel: { items: [{ id: 'code_regime', value }] } }) as unknown as Assessment
    expect(authorityOf(a('LA County Title 22'))).toBe('County')
    expect(authorityOf(a('LAMC Chapter I'))).toBe('City')
    authority.value = 'County'
    expect(labelText('interpretive')).toBe('Interpretation, confirm with County')
    authority.value = 'City'
    expect(labelText('interpretive')).toBe('Interpretation, confirm with City')
  })
})

describe('chapterName', () => {
  it('names the County code for Title 22 chunks', () => {
    expect(chapterName('T22')).toBe('LA County Code Title 22')
    expect(chapterName('I')).toBe('LAMC Chapter I')
    expect(chapterName('1A')).toBe('LAMC Chapter 1A')
  })
})
