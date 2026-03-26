import { execFileSync } from 'child_process'
import { expect, test, type APIRequestContext } from '@playwright/test'

const RUN_ID = Date.now()
const SEQUENCE_NAME = `Timeline E2E ${RUN_ID}`

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function createAndActivateSequence(request: APIRequestContext): Promise<string> {
  const create = await request.post('/api/sequences', {
    data: {
      name: SEQUENCE_NAME,
      steps: [
        { subject: 'Hello', body_html: '<p>Hi there</p>', delay: 0 },
        { subject: 'Follow up', body_html: '<p>Checking in</p>', delay: 2 },
      ],
    },
  })
  expect(create.ok()).toBeTruthy()
  const { id } = await create.json()
  const activate = await request.put(`/api/sequences/${id}/status`, {
    data: { status: 'active' },
  })
  expect(activate.ok()).toBeTruthy()
  return id as string
}

async function enrollCandidate(
  request: APIRequestContext,
  sequenceId: string,
  email: string,
  firstName: string,
  lastName: string,
): Promise<void> {
  const resp = await request.post(`/api/sequences/${sequenceId}/enroll`, {
    data: {
      candidates: [{ email, first_name: firstName, last_name: lastName, company: 'Acme', title: 'SRE' }],
    },
  })
  expect(resp.ok()).toBeTruthy()
}

async function postInboundWebhook(
  request: APIRequestContext,
  messageId: string,
  senderEmail: string,
  body: string,
): Promise<void> {
  const resp = await request.post('/api/nylas/webhook', {
    data: {
      data: {
        id: messageId,
        thread_id: null,
        from: [{ email: senderEmail }],
        subject: 'Re: Hello',
        body,
        snippet: body.slice(0, 50),
      },
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

test.describe('Candidate Timeline Modal E2E', () => {
  test.describe.configure({ mode: 'serial' })

  let sequenceId: string
  const candidateEmail = `timeline-${RUN_ID}@example.com`
  const candidateName = 'Alex Timeline'
  const msgId = `timeline-msg-${RUN_ID}`

  test.beforeAll(async ({ request }) => {
    test.setTimeout(120_000)

    ensureNylasAccount()

    sequenceId = await createAndActivateSequence(request)
    await enrollCandidate(request, sequenceId, candidateEmail, 'Alex', 'Timeline')

    // Post an inbound reply
    await postInboundWebhook(request, msgId, candidateEmail, "Sounds great, let's talk!")

    // Wait for reply to be processed
    for (let attempt = 0; attempt < 30; attempt++) {
      const resp = await request.get('/api/inbox/replies?limit=200&offset=0')
      if (resp.ok()) {
        const replies = (await resp.json()) as Array<{ candidate_email: string }>
        if (replies.some((r) => r.candidate_email === candidateEmail)) break
      }
      await sleep(1000)
    }

    setSentimentDirect(msgId, 'interested')
  })

  test('opens timeline modal from sequence detail candidate row', async ({ page }) => {
    await page.goto(`/sequences/${sequenceId}`)

    // Wait for the candidates table to load
    await expect(page.getByText(candidateEmail)).toBeVisible({ timeout: 10_000 })

    // Click the candidate row to open the modal
    const row = page.locator('tr').filter({ hasText: candidateEmail })
    await row.click()

    // Modal should open with dialog role
    const modal = page.getByRole('dialog', { name: /Candidate activity timeline/i })
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Should show candidate name
    await expect(modal.getByText('Alex Timeline')).toBeVisible()

    // Should show candidate email
    await expect(modal.getByText(candidateEmail)).toBeVisible()

    // Should show "Activity Timeline" heading
    await expect(modal.getByText('Activity Timeline')).toBeVisible()

    // Should show enrollment transition (at minimum "Enrolled in sequence")
    await expect(modal.getByText(/Enrolled in sequence/i)).toBeVisible()
  })

  test('timeline shows at least enrollment and additional events', async ({ page }) => {
    await page.goto(`/sequences/${sequenceId}`)
    await expect(page.getByText(candidateEmail)).toBeVisible({ timeout: 10_000 })

    const row = page.locator('tr').filter({ hasText: candidateEmail })
    await row.click()

    const modal = page.getByRole('dialog', { name: /Candidate activity timeline/i })
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Timeline should have multiple entries (enrolled + at least one more event from webhook processing)
    const timelineEntries = modal.locator('.border-l .flex.items-start')
    await expect(timelineEntries).not.toHaveCount(0)
    const count = await timelineEntries.count()
    expect(count).toBeGreaterThanOrEqual(2)
  })

  test('closes modal via X button', async ({ page }) => {
    await page.goto(`/sequences/${sequenceId}`)
    await expect(page.getByText(candidateEmail)).toBeVisible({ timeout: 10_000 })

    const row = page.locator('tr').filter({ hasText: candidateEmail })
    await row.click()

    const modal = page.getByRole('dialog', { name: /Candidate activity timeline/i })
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Close via X button
    const closeButton = page.getByRole('button', { name: /Close candidate detail/i })
    await closeButton.click()

    await expect(modal).not.toBeVisible()
  })

  test('closes modal via Escape key', async ({ page }) => {
    await page.goto(`/sequences/${sequenceId}`)
    await expect(page.getByText(candidateEmail)).toBeVisible({ timeout: 10_000 })

    const row = page.locator('tr').filter({ hasText: candidateEmail })
    await row.click()

    const modal = page.getByRole('dialog', { name: /Candidate activity timeline/i })
    await expect(modal).toBeVisible({ timeout: 5_000 })

    await page.keyboard.press('Escape')

    await expect(modal).not.toBeVisible()
  })

  test('closes modal via backdrop click', async ({ page }) => {
    await page.goto(`/sequences/${sequenceId}`)
    await expect(page.getByText(candidateEmail)).toBeVisible({ timeout: 10_000 })

    const row = page.locator('tr').filter({ hasText: candidateEmail })
    await row.click()

    const modal = page.getByRole('dialog', { name: /Candidate activity timeline/i })
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Click the backdrop (the fixed overlay behind the modal)
    const backdrop = page.locator('.fixed.inset-0.z-50')
    // Click at the edge where the modal isn't — top-left corner of the overlay
    await backdrop.click({ position: { x: 10, y: 10 } })

    await expect(modal).not.toBeVisible()
  })

  test('modal shows enrollment status badge', async ({ page }) => {
    await page.goto(`/sequences/${sequenceId}`)
    await expect(page.getByText(candidateEmail)).toBeVisible({ timeout: 10_000 })

    const row = page.locator('tr').filter({ hasText: candidateEmail })
    await row.click()

    const modal = page.getByRole('dialog', { name: /Candidate activity timeline/i })
    await expect(modal).toBeVisible({ timeout: 5_000 })

    // Wait for timeline data to load (not just the modal shell)
    await expect(modal.getByText('Activity Timeline')).toBeVisible({ timeout: 10_000 })

    // Should have an enrollment status badge (status depends on classification/scheduler outcome)
    await expect(modal.getByText(/replied|active|paused|completed|bounced/i).first()).toBeVisible()
  })
})
