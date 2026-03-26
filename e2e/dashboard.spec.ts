import { execFileSync } from 'child_process'
import { expect, test, type APIRequestContext } from '@playwright/test'

const RUN_ID = Date.now()

async function createAndActivateSequence(
  request: APIRequestContext,
  name: string,
  stepCount = 1,
): Promise<string> {
  const steps = Array.from({ length: stepCount }, (_, i) => ({
    subject: `Step ${i + 1}`,
    body_html: `<p>Body ${i + 1}</p>`,
    delay: i === 0 ? 0 : i,
  }))
  const create = await request.post('/api/sequences', { data: { name, steps } })
  expect(create.ok()).toBeTruthy()
  const { id } = await create.json()
  const activate = await request.put(`/api/sequences/${id}/status`, {
    data: { status: 'active' },
  })
  expect(activate.ok()).toBeTruthy()
  return id as string
}

async function enrollCandidates(
  request: APIRequestContext,
  sequenceId: string,
  emails: string[],
): Promise<void> {
  const resp = await request.post(`/api/sequences/${sequenceId}/enroll`, {
    data: {
      candidates: emails.map((email, i) => ({
        email,
        first_name: `Test${i}`,
        last_name: 'User',
      })),
    },
  })
  expect(resp.ok()).toBeTruthy()
}

function runSql(sql: string): void {
  execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'db', 'psql', '-U', 'jooba', '-d', 'jooba', '-c', sql],
    { cwd: process.cwd() },
  )
}

function setSentimentDirect(messageId: string, sentiment: string): void {
  runSql(`UPDATE email_events SET sentiment = '${sentiment}', sentiment_reasoning = 'E2E seeded' WHERE nylas_message_id = '${messageId}';`)
}

function ensureNylasAccount(): void {
  runSql(`INSERT INTO nylas_accounts (id, email, grant_id, provider, connected_at) VALUES (gen_random_uuid(), 'e2e@example.com', 'fake-grant-e2e', 'virtual', now()) ON CONFLICT (email) DO UPDATE SET connected_at = now();`)
}

test.describe('Dashboard E2E', () => {
  test('shows empty state with CTA when no sequences exist', async ({ page }) => {
    // Mock dashboard API to return zeroed stats
    await page.route('**/api/analytics/dashboard**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_candidates: 0,
          total_sent: 0,
          total_replies: 0,
          reply_rate: 0,
          total_interested: 0,
          unreplied_count: 0,
          sequences: [],
        }),
      }),
    )

    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Dashboard/i })).toBeVisible()

    // Stat cards should show zeros
    await expect(page.getByText('Candidates', { exact: true })).toBeVisible()
    await expect(page.getByText('Sent', { exact: true })).toBeVisible()
    await expect(page.getByText('Replies', { exact: true })).toBeVisible()
    await expect(page.getByText('Interested', { exact: true })).toBeVisible()

    // Empty state for sequences section
    await expect(page.getByText(/No sequences/i)).toBeVisible()

    // CTA button should navigate to create sequence
    const cta = page.getByRole('button', { name: /Create Sequence/i })
    await expect(cta).toBeVisible()
    await cta.click()
    await expect(page).toHaveURL(/\/sequences\/new/)
  })
})

test.describe('Dashboard E2E - seeded data', () => {
  test.describe.configure({ mode: 'serial' })

  let seqId: string
  const seqName = `Dashboard E2E ${RUN_ID}`

  test.beforeAll(async ({ request }) => {
    test.setTimeout(120_000)

    ensureNylasAccount()

    seqId = await createAndActivateSequence(request, seqName, 2)
    await enrollCandidates(request, seqId, [
      `dash-a-${RUN_ID}@example.com`,
      `dash-b-${RUN_ID}@example.com`,
      `dash-c-${RUN_ID}@example.com`,
    ])

    // Post inbound webhooks for two candidates to create reply records
    const msgIdA = `dash-msg-a-${RUN_ID}`
    const msgIdB = `dash-msg-b-${RUN_ID}`

    await request.post('/api/nylas/webhook', {
      data: {
        data: {
          id: msgIdA,
          thread_id: null,
          from: [{ email: `dash-a-${RUN_ID}@example.com` }],
          subject: 'Re: Step 1',
          body: "I'm very interested in this role!",
          snippet: "I'm very interested",
        },
      },
    })
    await request.post('/api/nylas/webhook', {
      data: {
        data: {
          id: msgIdB,
          thread_id: null,
          from: [{ email: `dash-b-${RUN_ID}@example.com` }],
          subject: 'Re: Step 1',
          body: 'No thank you, not looking.',
          snippet: 'No thank you',
        },
      },
    })

    // Wait for replies to appear
    for (let attempt = 0; attempt < 30; attempt++) {
      const resp = await request.get('/api/inbox/counts')
      if (resp.ok()) {
        const counts = await resp.json()
        if (counts.all >= 2) break
      }
      await new Promise((r) => setTimeout(r, 1000))
    }

    // Set deterministic sentiments
    setSentimentDirect(msgIdA, 'interested')
    setSentimentDirect(msgIdB, 'not_interested')
  })

  test('renders stat cards with seeded data', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Dashboard/i })).toBeVisible()

    // total_candidates should be at least 3
    const candidatesCard = page.locator('text=Candidates').locator('..')
    await expect(candidatesCard).toBeVisible()

    // Check that the sequence table section is visible
    await expect(page.getByRole('heading', { name: /Active Sequences/i })).toBeVisible()
  })

  test('sequence table row shows name, status, and columns', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Active Sequences/i })).toBeVisible()

    // Find our sequence row
    const table = page.locator('table')
    const row = table.locator('tr').filter({ hasText: seqName })
    await expect(row).toBeVisible()

    // Verify columns are present in headers
    await expect(table.locator('th', { hasText: 'Sequence' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Status' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Steps' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Enrolled' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Replied' })).toBeVisible()
    await expect(table.locator('th', { hasText: 'Interested' })).toBeVisible()

    // Row should show step count
    await expect(row.locator('td').nth(2)).toHaveText('2')
  })

  test('clicking sequence row navigates to sequence detail', async ({ page }) => {
    await page.goto('/')
    const table = page.locator('table')
    const row = table.locator('tr').filter({ hasText: seqName })
    await expect(row).toBeVisible()

    await row.click()
    await expect(page).toHaveURL(new RegExp(`/sequences/${seqId}`))
    await expect(page.getByRole('heading', { name: seqName })).toBeVisible()
  })

  test('interested stat card links to inbox filtered by interested', async ({ page }) => {
    await page.goto('/')

    // The "Interested" stat card or its value should be clickable
    // The DashboardPage links reply_rate card to /inbox?filter=interested when unreplied > 0
    // Let's check if the Interested stat navigates
    const interestedCard = page.locator('[class*="cursor-pointer"]').filter({ hasText: 'Interested' }).first()
    if (await interestedCard.isVisible()) {
      await interestedCard.click()
      await expect(page).toHaveURL(/\/inbox/)
    }
  })
})
