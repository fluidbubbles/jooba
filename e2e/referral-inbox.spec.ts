import { execFileSync } from 'child_process'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const RUN_ID = Date.now()
const SEQUENCE_NAME = `Referral E2E ${RUN_ID}`

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function createAndActivateSequence(request: APIRequestContext, name: string): Promise<string> {
  const create = await request.post('/api/sequences', {
    data: {
      name,
      steps: [
        { subject: 'Opportunity', body_html: '<p>Hi {{first_name}}, interested?</p>', delay: 0 },
        { subject: 'Following up', body_html: '<p>Checking in</p>', delay: 2 },
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
      candidates: [{ email, first_name: firstName, last_name: lastName, company: 'E2E Corp', title: 'Engineer' }],
    },
  })
  expect(resp.ok()).toBeTruthy()
}

async function postInboundWebhook(
  request: APIRequestContext,
  messageId: string,
  senderEmail: string,
  body: string,
  snippet: string,
): Promise<void> {
  const resp = await request.post('/api/nylas/webhook', {
    data: {
      data: {
        id: messageId,
        thread_id: null,
        from: [{ email: senderEmail }],
        subject: 'Re: Opportunity',
        body,
        snippet,
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
  runSql(`UPDATE email_events SET sentiment = '${sentiment}', sentiment_reasoning = 'E2E seeded: ${sentiment}' WHERE nylas_message_id = '${messageId}';`)
}

function ensureNylasAccount(): void {
  runSql(`INSERT INTO nylas_accounts (id, email, grant_id, provider, connected_at) VALUES (gen_random_uuid(), 'e2e@example.com', 'fake-grant-e2e', 'virtual', now()) ON CONFLICT (email) DO UPDATE SET connected_at = now();`)
}

async function waitForReplyRecord(request: APIRequestContext, email: string): Promise<void> {
  for (let attempt = 0; attempt < 30; attempt++) {
    const resp = await request.get('/api/inbox/replies?limit=200&offset=0')
    if (resp.ok()) {
      const replies = (await resp.json()) as Array<{ candidate_email: string }>
      if (replies.some((r) => r.candidate_email === email)) return
    }
    await sleep(1000)
  }
  throw new Error(`Timed out waiting for reply record from ${email}`)
}

async function waitForSentiment(
  request: APIRequestContext,
  email: string,
  sentiment: string,
): Promise<string> {
  for (let attempt = 0; attempt < 30; attempt++) {
    const resp = await request.get('/api/inbox/replies?limit=200&offset=0')
    if (resp.ok()) {
      const replies = (await resp.json()) as Array<{ id: string; candidate_email: string; sentiment: string | null }>
      const hit = replies.find((r) => r.candidate_email === email && r.sentiment === sentiment)
      if (hit) return hit.id
    }
    await sleep(1000)
  }
  throw new Error(`Timed out waiting for ${email} sentiment=${sentiment}`)
}

function candidateRow(page: Page, name: string) {
  return page
    .locator('div.cursor-pointer')
    .filter({ hasText: name })
    .filter({ hasText: SEQUENCE_NAME })
    .first()
}

async function openReplyDetail(page: Page, name: string, email: string): Promise<void> {
  const row = candidateRow(page, name)
  const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()

  for (let attempt = 0; attempt < 6; attempt++) {
    await row.click()
    try {
      await expect(detailPanel.getByText(email)).toBeVisible({ timeout: 2000 })
      return
    } catch {
      await sleep(350)
    }
  }
  throw new Error(`Could not open detail panel for ${email}`)
}

test.describe('Referral Inbox E2E', () => {
  test.describe.configure({ mode: 'serial' })

  let sequenceId: string
  let referralReplyId: string
  let interestedReplyId: string

  const referrerEmail = `referrer-${RUN_ID}@example.com`
  const referrerName = 'David Lee'
  const referrerMsgId = `ref-e2e-david-${RUN_ID}`

  const interestedEmail = `interested-${RUN_ID}@example.com`
  const interestedName = 'Jane Chen'
  const interestedMsgId = `ref-e2e-jane-${RUN_ID}`

  test.beforeAll(async ({ request }) => {
    test.setTimeout(180_000)

    // Ensure a Nylas account exists so process_webhook can determine direction
    ensureNylasAccount()

    sequenceId = await createAndActivateSequence(request, SEQUENCE_NAME)

    // Enroll referrer candidate
    await enrollCandidate(request, sequenceId, referrerEmail, 'David', 'Lee')
    await postInboundWebhook(
      request,
      referrerMsgId,
      referrerEmail,
      'Please reach out to my colleague Sarah Kim at sarah.kim@uber.com. She would be a great fit.',
      'Please reach out to my colleague Sarah Kim.',
    )

    // Enroll interested candidate (no referral card expected)
    await enrollCandidate(request, sequenceId, interestedEmail, 'Jane', 'Chen')
    await postInboundWebhook(
      request,
      interestedMsgId,
      interestedEmail,
      "I'd love to chat about this opportunity. Let's schedule a call.",
      "I'd love to chat.",
    )

    await waitForReplyRecord(request, referrerEmail)
    await waitForReplyRecord(request, interestedEmail)

    setSentimentDirect(referrerMsgId, 'referral')
    setSentimentDirect(interestedMsgId, 'interested')

    referralReplyId = await waitForSentiment(request, referrerEmail, 'referral')
    interestedReplyId = await waitForSentiment(request, interestedEmail, 'interested')
  })

  test('referral reply shows extracted referral card', async ({ page }) => {
    await page.goto('/inbox')

    // Filter to Referral tab
    await page.getByRole('button', { name: /^Referral \(/i }).click()

    await openReplyDetail(page, referrerName, referrerEmail)

    // The detail panel should show the SentimentBadge for referral
    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    await expect(detailPanel.getByText('Referral', { exact: true })).toBeVisible()

    // ReferralCard section should appear
    const referralSection = page.locator('section[aria-label="Extracted referral"]')
    await expect(referralSection).toBeVisible({ timeout: 10_000 })
    await expect(referralSection.getByText('Extracted Referral')).toBeVisible()
  })

  test('interested reply does NOT show referral card', async ({ page }) => {
    await page.goto('/inbox')

    await page.getByRole('button', { name: /^Interested \(/i }).click()
    await openReplyDetail(page, interestedName, interestedEmail)

    // Detail panel should load
    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    await expect(detailPanel.getByText(interestedEmail)).toBeVisible()

    // No referral card should be present
    const referralSection = page.locator('section[aria-label="Extracted referral"]')
    await expect(referralSection).toHaveCount(0)
  })

  test('dismiss referral card hides it', async ({ page }) => {
    await page.goto('/inbox')

    await page.getByRole('button', { name: /^Referral \(/i }).click()
    await openReplyDetail(page, referrerName, referrerEmail)

    const referralSection = page.locator('section[aria-label="Extracted referral"]')
    await expect(referralSection).toBeVisible({ timeout: 10_000 })

    // Click dismiss button
    const dismissButton = page.getByRole('button', { name: 'Dismiss referral card' })
    await expect(dismissButton).toBeVisible()
    await dismissButton.click()

    // Card should disappear
    await expect(referralSection).toHaveCount(0)
  })

  test('referral card shows retry when extraction not yet available', async ({ page }) => {
    await page.goto('/inbox')

    await page.getByRole('button', { name: /^Referral \(/i }).click()
    await openReplyDetail(page, referrerName, referrerEmail)

    const referralSection = page.locator('section[aria-label="Extracted referral"]')
    await expect(referralSection).toBeVisible({ timeout: 10_000 })

    // Without an LLM provider, the referral data isn't extracted yet
    // The card should show the "not available" state with a Retry button
    const hasReferredBy = await referralSection.getByText(/Referred by/i).isVisible().catch(() => false)
    if (hasReferredBy) {
      // If extraction worked (e.g., LLM is available), verify referrer info
      await expect(referralSection.getByText(referrerEmail, { exact: false })).toBeVisible()
    } else {
      // No LLM — card shows fallback state with retry
      await expect(referralSection.getByText(/not available/i)).toBeVisible()
      await expect(referralSection.getByRole('button', { name: /Retry/i })).toBeVisible()
    }
  })
})
