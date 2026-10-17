import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const fixture = (name: string) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8')
const chunks = JSON.parse(fixture('chunks.json')) as Record<string, unknown>

async function mockApi(page: Page, opts: { invite?: boolean } = {}) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: typeof body === 'string' ? body : JSON.stringify(body) })
    if (url.pathname === '/api/invite') return json({ required: Boolean(opts.invite), ok: !opts.invite })
    if (opts.invite) return json({ detail: 'invite_required' }, 401)
    if (url.pathname === '/api/assess') {
      const q = (url.searchParams.get('q') ?? '').replace(/\D/g, '')
      try {
        return json(fixture(`assess-${q}.json`))
      } catch {
        return json({ detail: 'parcel not found' }, 404)
      }
    }
    const near = url.pathname.match(/^\/api\/parcels\/(\d{10})\/nearby$/)
    if (near) return json(fixture(`nearby-${near[1]}.json`))
    const ch = url.pathname.match(/^\/api\/chunks\/(.+)$/)
    if (ch) {
      const c = chunks[decodeURIComponent(ch[1])]
      return c ? json(c) : json({ detail: 'no such chunk' }, 404)
    }
    return json({ detail: 'not mocked' }, 404)
  })
}

const row = (page: Page, title: string) =>
  page.locator('button.row').filter({ has: page.locator('.rt', { hasText: new RegExp(`^${title}`) }) })

test('a City R1 lot shows its envelope and opens the cited text', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?q=2121005008')
  await expect(page.getByRole('heading', { name: 'R1 envelope' })).toBeVisible()
  const front = row(page, 'Front yard \\(minimum\\)')
  await expect(front).toContainText('20 ft')
  await expect(front).toContainText('Derived from rule')
  await front.click()
  const panel = page.getByRole('complementary', { name: 'Source text' })
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('LAMC 12.08 C.1')
  await expect(page.getByText('confirm with County')).toHaveCount(0)
})

test('an unincorporated County lot names the County and its own envelope', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?q=4142004002')
  await expect(page.getByRole('heading', { name: 'County R-1 envelope' })).toBeVisible()
  await expect(page.getByText('Title 22, from a copy whose edition is not stated')).toBeVisible()
  await expect(row(page, 'Maximum height')).toContainText('35 ft')
  await expect(row(page, 'Front yard \\(minimum\\)').getByText('Interpretation, confirm with County')).toBeVisible()
  await expect(page.getByText('confirm with City')).toHaveCount(0)
  await row(page, 'Front yard \\(minimum\\)').click()
  await expect(page.getByRole('complementary', { name: 'Source text' })).toContainText('LACC 22.18.040')
})

test('stop states show no rules', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?q=4144001800')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('not modeled')
  await expect(page.locator('button.row')).toHaveCount(0)
  await page.goto('/?q=4327028024')
  await expect(page.getByRole('heading', { name: 'Outside the City of Los Angeles' })).toBeVisible()
  await expect(page.locator('button.row')).toHaveCount(0)
})

test('an unknown APN says which areas are loaded', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?q=1234567890')
  await expect(page.getByText('Del Aire in unincorporated LA County')).toBeVisible()
})

test('the invite gate comes before any assessment', async ({ page }) => {
  await mockApi(page, { invite: true })
  await page.goto('/?q=2121005008')
  await expect(page.getByLabel('Invite code')).toBeVisible()
  await expect(page.locator('button.row')).toHaveCount(0)
})

test('a phone-width page does not scroll sideways', async ({ page }) => {
  await mockApi(page)
  await page.setViewportSize({ width: 390, height: 900 })
  await page.goto('/?q=4142004002')
  await expect(page.getByRole('heading', { name: 'County R-1 envelope' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})

test('the source panel can be reached and closed with the keyboard', async ({ page }) => {
  await mockApi(page)
  await page.goto('/?q=2121005008')
  const front = row(page, 'Front yard \\(minimum\\)')
  await front.focus()
  await page.keyboard.press('Enter')
  const panel = page.getByRole('complementary', { name: 'Source text' })
  await expect(panel).toBeVisible()
  await panel.press('Escape')
  await expect(front).toBeFocused()
})
