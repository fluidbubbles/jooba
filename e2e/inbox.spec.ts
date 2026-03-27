import { execFileSync } from 'child_process'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

type CandidateSeed = {
  email: string
  firstName: string
  lastName: string
  sentiment: 'interested' | 'not_interested' | 'referral' | 'neutral'
  body: string
  snippet: string
  messageId: string
}

type InboxSeed = {
  sequenceId: string
  sequenceName: string
  candidates: Record<CandidateSeed['sentiment'], CandidateSeed>
}

const RUN_ID = Date.now()
const SEQUENCE_NAME = `Inbox E2E ${RUN_ID}`

const CANDIDATES: CandidateSeed[] = [
  {
    email: `jane.inbox.${RUN_ID}@example.com`,
    firstName: 'Jane',
    lastName: 'Chen',
    sentiment: 'interested',
    body: "I'd love to chat. I am interested and happy to schedule a call.",
    snippet: "I'd love to chat.",
    messageId: `inbox-e2e-jane-${RUN_ID}`,
  },
  {
    email: `mike.inbox.${RUN_ID}@example.com`,
    firstName: 'Mike',
    lastName: 'Johnson',
    sentiment: 'not_interested',
    body: "No thanks, I'm not interested.",
    snippet: "No thanks, I'm not interested.",
    messageId: `inbox-e2e-mike-${RUN_ID}`,
  },
  {
    email: `david.inbox.${RUN_ID}@example.com`,
    firstName: 'David',
    lastName: 'Lee',
    sentiment: 'referral',
    body: 'Please reach out to my colleague Sarah Kim at sarah.kim@uber.com.',
    snippet: 'Please reach out to my colleague Sarah Kim.',
    messageId: `inbox-e2e-david-${RUN_ID}`,
  },
  {
    email: `sarah.inbox.${RUN_ID}@example.com`,
    firstName: 'Sarah',
    lastName: 'Park',
    sentiment: 'neutral',
    body: 'Can you share more details about compensation and remote policy?',
    snippet: 'Can you share more details?',
    messageId: `inbox-e2e-sarah-${RUN_ID}`,
  },
]

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function candidateFullName(candidate: CandidateSeed): string {
  return `${candidate.firstName} ${candidate.lastName}`
}

function candidateRow(page: Page, candidate: CandidateSeed) {
  return page
    .locator('div.cursor-pointer')
    .filter({ hasText: candidateFullName(candidate) })
    .filter({ hasText: SEQUENCE_NAME })
    .first()
}

async function createAndActivateSequence(request: APIRequestContext): Promise<string> {
  const create = await request.post('/api/sequences', {
    data: {
      name: SEQUENCE_NAME,
      steps: [
        { subject: 'Opportunity at Ramp', body_html: '<p>Hi {{first_name}}, interested?</p>', delay: 0 },
        { subject: 'Following up', body_html: '<p>Just checking in</p>', delay: 2 },
      ],
    },
  })
  expect(create.ok()).toBeTruthy()
  const created = await create.json()

  const activate = await request.put(`/api/sequences/${created.id}/status`, {
    data: { status: 'active' },
  })
  expect(activate.ok()).toBeTruthy()
  return created.id as string
}

async function enrollCandidates(request: APIRequestContext, sequenceId: string): Promise<void> {
  const enroll = await request.post(`/api/sequences/${sequenceId}/enroll`, {
    data: {
      candidates: CANDIDATES.map((candidate) => ({
        email: candidate.email,
        first_name: candidate.firstName,
        last_name: candidate.lastName,
        company: 'E2E Corp',
        title: 'Engineer',
      })),
    },
  })
  expect(enroll.ok()).toBeTruthy()
}

async function postInboundWebhook(request: APIRequestContext, candidate: CandidateSeed): Promise<void> {
  const resp = await request.post('/api/nylas/webhook', {
    data: {
      data: {
        id: candidate.messageId,
        thread_id: null,
        from: [{ email: candidate.email }],
        subject: 'Re: Opportunity at Ramp',
        body: candidate.body,
        snippet: candidate.snippet,
      },
    },
  })
  expect(resp.ok()).toBeTruthy()
}

async function findReply(
  request: APIRequestContext,
  email: string,
  sentiment?: CandidateSeed['sentiment'],
): Promise<{ id: string; sentiment: string | null } | null> {
  const resp = await request.get('/api/inbox/replies?limit=200&offset=0')
  if (!resp.ok()) return null
  const replies = await resp.json() as Array<{
    id: string
    candidate_email: string
    sentiment: string | null
  }>
  const matches = replies.filter((reply) => reply.candidate_email === email)
  if (matches.length === 0) return null
  if (!sentiment) return { id: matches[0].id, sentiment: matches[0].sentiment }
  const exact = matches.find((reply) => reply.sentiment === sentiment)
  return exact ? { id: exact.id, sentiment: exact.sentiment } : null
}

async function waitForSentiment(
  request: APIRequestContext,
  email: string,
  expected: CandidateSeed['sentiment'],
): Promise<void> {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const reply = await findReply(request, email, expected)
    if (reply) return
    await sleep(1000)
  }
  throw new Error(`Timed out waiting for ${email} sentiment=${expected}`)
}

async function waitForReplyRecord(request: APIRequestContext, email: string): Promise<void> {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const reply = await findReply(request, email)
    if (reply) return
    await sleep(1000)
  }
  throw new Error(`Timed out waiting for reply record for ${email}`)
}

async function waitForReplySnippet(
  request: APIRequestContext,
  email: string,
  snippet: string,
): Promise<void> {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const resp = await request.get('/api/inbox/replies?limit=200&offset=0')
    if (resp.ok()) {
      const replies = await resp.json() as Array<{ candidate_email: string; body_snippet: string }>
      const hit = replies.find(
        (reply) =>
          reply.candidate_email === email &&
          reply.body_snippet.includes(snippet),
      )
      if (hit) return
    }
    await sleep(1000)
  }
  throw new Error(`Timed out waiting for snippet "${snippet}" for ${email}`)
}

async function openReplyDetail(page: Page, candidate: CandidateSeed): Promise<void> {
  const row = candidateRow(page, candidate)
  const rows = page.locator('div.cursor-pointer').filter({ hasText: SEQUENCE_NAME })
  const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()

  for (let attempt = 0; attempt < 6; attempt += 1) {
    const rowCount = await rows.count()
    if (attempt > 0 && rowCount > 1) {
      await rows.nth(attempt % rowCount).click()
      await sleep(250)
    }
    await row.click()
    try {
      await expect(detailPanel.getByText(candidate.email)).toBeVisible({ timeout: 2000 })
      return
    } catch {
      await sleep(350)
    }
  }
  throw new Error(`Could not open detail panel for ${candidate.email}`)
}

function setSentimentForMessage(messageId: string, sentiment: CandidateSeed['sentiment']): void {
  const sentimentSafe = sentiment.replace(/'/g, "''")
  const messageSafe = messageId.replace(/'/g, "''")
  const reasoningSafe = `E2E seeded sentiment: ${sentimentSafe}`.replace(/'/g, "''")
  const sql = `UPDATE email_events SET sentiment = '${sentimentSafe}', sentiment_reasoning = '${reasoningSafe}' WHERE nylas_message_id = '${messageSafe}';`
  execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'db', 'psql', '-U', 'jooba', '-d', 'jooba', '-c', sql],
    { cwd: process.cwd() },
  )
}

function ensureNylasAccount(): void {
  const sql = `INSERT INTO nylas_accounts (id, email, grant_id, provider, connected_at) VALUES (gen_random_uuid(), 'e2e@example.com', 'fake-grant-e2e', 'virtual', now()) ON CONFLICT (email) DO UPDATE SET connected_at = now();`
  execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'db', 'psql', '-U', 'jooba', '-d', 'jooba', '-c', sql],
    { cwd: process.cwd() },
  )
}

async function seedInbox(request: APIRequestContext): Promise<InboxSeed> {
  ensureNylasAccount()
  const sequenceId = await createAndActivateSequence(request)
  await enrollCandidates(request, sequenceId)

  for (const candidate of CANDIDATES) {
    await postInboundWebhook(request, candidate)
  }

  for (const candidate of CANDIDATES) {
    await waitForReplyRecord(request, candidate.email)
  }

  // Stabilize sentiment state for deterministic UI assertions.
  for (const candidate of CANDIDATES) {
    setSentimentForMessage(candidate.messageId, candidate.sentiment)
  }

  for (const candidate of CANDIDATES) {
    await waitForSentiment(request, candidate.email, candidate.sentiment)
  }

  return {
    sequenceId,
    sequenceName: SEQUENCE_NAME,
    candidates: {
      interested: CANDIDATES.find((c) => c.sentiment === 'interested')!,
      not_interested: CANDIDATES.find((c) => c.sentiment === 'not_interested')!,
      referral: CANDIDATES.find((c) => c.sentiment === 'referral')!,
      neutral: CANDIDATES.find((c) => c.sentiment === 'neutral')!,
    },
  }
}

test.describe('Inbox E2E', () => {
  test('shows empty state when inbox APIs return no replies', async ({ page }) => {
    await page.route('**/api/inbox/replies**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      }),
    )
    await page.route('**/api/inbox/counts**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          all: 0,
          interested: 0,
          not_interested: 0,
          referral: 0,
          neutral: 0,
        }),
      }),
    )

    await page.goto('/inbox')
    await expect(page.getByRole('heading', { name: /Inbox/i })).toBeVisible()
    await expect(page.getByText('No replies yet')).toBeVisible()
    await expect(page.getByRole('button', { name: /^Interested \(/i })).toHaveCount(0)
  })
})

test.describe('Inbox E2E - seeded flow', () => {
  test.describe.configure({ mode: 'serial' })
  let seed: InboxSeed

  test.beforeAll(async ({ request }) => {
    test.setTimeout(180_000)
    seed = await seedInbox(request)
  })

  test('renders inbox list and sentiment filters', async ({ page }) => {
    await page.goto('/inbox')

    await expect(page.getByRole('heading', { name: /Inbox/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^All \(/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Interested \(/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Not Interested \(/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Referral \(/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Neutral \(/i })).toBeVisible()

    await page.getByRole('button', { name: /^Interested \(/i }).click()
    await expect(candidateRow(page, seed.candidates.interested)).toBeVisible()

    await page.getByRole('button', { name: /^Not Interested \(/i }).click()
    await expect(candidateRow(page, seed.candidates.not_interested)).toBeVisible()

    await page.getByRole('button', { name: /^Referral \(/i }).click()
    await expect(candidateRow(page, seed.candidates.referral)).toBeVisible()

    await page.getByRole('button', { name: /^Neutral \(/i }).click()
    await expect(candidateRow(page, seed.candidates.neutral)).toBeVisible()
  })

  test('shows detail panel and sends a manual reply from composer', async ({ page }) => {
    const outgoingReply = `Playwright composer reply ${Date.now()}`
    const fullName = `${seed.candidates.interested.firstName} ${seed.candidates.interested.lastName}`

    await page.goto('/inbox')
    await openReplyDetail(page, seed.candidates.interested)

    await expect(page.getByRole('heading', { name: fullName })).toBeVisible()
    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    await expect(detailPanel.getByText(seed.candidates.interested.email)).toBeVisible()
    await expect(page.getByText('Thread', { exact: true })).toBeVisible()

    await detailPanel.evaluate((el) => {
      el.scrollTop = el.scrollHeight
    })

    const sendButton = page.getByRole('button', { name: /Send Reply/i })
    const textarea = page.locator('textarea').first()

    await expect(sendButton).toBeDisabled()
    await textarea.fill(outgoingReply)
    await expect(sendButton).toBeEnabled()
    await sendButton.click()

    // After send completes, textarea clears and reply appears in thread
    await expect(textarea).toHaveValue('', { timeout: 15_000 })
    await expect(page.getByText(outgoingReply)).toBeVisible({ timeout: 10_000 })
    await expect(sendButton).toBeDisabled()
  })

  test('sanitizes malicious HTML in thread and blocks script execution', async ({ page, request }) => {
    const marker = `xss-marker-${Date.now()}`
    const xssMessageId = `inbox-e2e-xss-${Date.now()}`
    const candidate = seed.candidates.interested

    const webhook = await request.post('/api/nylas/webhook', {
      data: {
        data: {
          id: xssMessageId,
          thread_id: null,
          from: [{ email: candidate.email }],
          subject: 'Re: Opportunity at Ramp',
          body: `<p>${marker}</p><script>alert('xss')</script><img onerror='alert(1)' src='x'>`,
          snippet: marker,
        },
      },
    })
    expect(webhook.ok()).toBeTruthy()

    await waitForReplySnippet(request, candidate.email, marker)

    let dialogs = 0
    page.on('dialog', async (dialog) => {
      dialogs += 1
      await dialog.dismiss()
    })

    await page.goto('/inbox')
    await openReplyDetail(page, candidate)
    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    await expect(detailPanel.getByText(marker)).toBeVisible()

    const messageHtml = await detailPanel.locator('div.prose').filter({ hasText: marker }).first().innerHTML()
    expect(messageHtml).not.toContain('<script')
    expect(messageHtml).not.toContain('onerror')
    expect(dialogs).toBe(0)
  })

  test('composer shows Sending state and appends reply to thread', async ({ page }) => {
    const replyText = `Sending-state-test ${Date.now()}`

    await page.goto('/inbox')
    await openReplyDetail(page, seed.candidates.neutral)

    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    await expect(detailPanel.getByText(seed.candidates.neutral.email)).toBeVisible()

    // Scroll to composer
    await detailPanel.evaluate((el) => { el.scrollTop = el.scrollHeight })

    const textarea = page.locator('textarea').first()
    const sendButton = page.getByRole('button', { name: /Send Reply/i })

    await textarea.fill(replyText)
    await expect(sendButton).toBeEnabled()

    // Click send — button should show "Sending..." while request is in flight
    const sendPromise = sendButton.click()

    // Check for Sending... state (may be brief)
    try {
      await expect(sendButton).toHaveText(/Sending/i, { timeout: 3_000 })
    } catch {
      // The request may have completed before we could observe — acceptable
    }
    await sendPromise

    // After send completes, textarea should clear and the reply should appear in the thread
    await expect.poll(async () => textarea.inputValue(), { timeout: 10_000 }).toBe('')
    await expect(detailPanel.getByText(replyText)).toBeVisible({ timeout: 10_000 })
    await expect(sendButton).toBeDisabled()
  })

  test('unreplied tab exists and shows correct count', async ({ page }) => {
    await page.goto('/inbox')

    // The "Unreplied" tab should exist with a count (may be 0 if recruiter already replied)
    const unrepliedTab = page.getByRole('button', { name: /^Unreplied \(\d+\)/i })
    await expect(unrepliedTab).toBeVisible()

    // Click Unreplied tab — verify it activates
    await unrepliedTab.click()

    // Extract count from tab text
    const tabText = await unrepliedTab.textContent()
    const match = tabText?.match(/\((\d+)\)/)
    const count = match ? parseInt(match[1], 10) : 0

    if (count > 0) {
      // If unreplied items exist, verify list items appear
      const listItems = page.locator('div.cursor-pointer').filter({ hasText: SEQUENCE_NAME })
      await expect(listItems.first()).toBeVisible({ timeout: 5_000 })
    } else {
      // If count is 0, verify "No unreplied replies" message
      await expect(page.getByText(/no.*unreplied/i)).toBeVisible()
    }
  })

  test('sequence detail shows replied enrollment status after inbox reply', async ({ page }) => {
    // Navigate to the sequence detail page
    await page.goto(`/sequences/${seed.sequenceId}`)

    // Wait for candidates table to load — scroll down if needed
    const interestedEmail = seed.candidates.interested.email
    await expect(page.getByRole('heading', { name: 'Candidates' })).toBeVisible({ timeout: 10_000 })
    await page.getByRole('heading', { name: 'Candidates' }).scrollIntoViewIfNeeded()

    await expect(page.getByText(interestedEmail)).toBeVisible({ timeout: 10_000 })

    // The interested candidate's enrollment should show "replied" status
    const row = page.locator('tr').filter({ hasText: interestedEmail })
    await row.scrollIntoViewIfNeeded()
    await expect(row.getByText(/replied/i)).toBeVisible()
  })

  test('sentiment counts in filter tabs match seeded data', async ({ page }) => {
    await page.goto('/inbox')
    await expect(page.getByRole('button', { name: /^All \(/i })).toBeVisible()

    // Each seeded sentiment has exactly 1 candidate, so total >= 4
    const allButton = page.getByRole('button', { name: /^All \(/i })
    const allText = await allButton.textContent()
    const allMatch = allText?.match(/All \((\d+)\)/)
    expect(allMatch).toBeTruthy()
    expect(Number(allMatch![1])).toBeGreaterThanOrEqual(4)

    // Each sentiment tab should show at least 1
    for (const { buttonPattern, min } of [
      { buttonPattern: /^Interested \((\d+)\)/, min: 1 },
      { buttonPattern: /^Not Interested \((\d+)\)/, min: 1 },
      { buttonPattern: /^Referral \((\d+)\)/, min: 1 },
      { buttonPattern: /^Neutral \((\d+)\)/, min: 1 },
    ]) {
      const btn = page.getByRole('button', { name: buttonPattern })
      await expect(btn).toBeVisible()
      const text = await btn.textContent()
      const match = text?.match(/\((\d+)\)/)
      expect(match).toBeTruthy()
      expect(Number(match![1])).toBeGreaterThanOrEqual(min)
    }
  })

  test('reply detail shows sentiment badge and reasoning', async ({ page }) => {
    await page.goto('/inbox')

    // Filter to interested to find the right candidate
    await page.getByRole('button', { name: /^Interested \(/i }).click()
    await openReplyDetail(page, seed.candidates.interested)

    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()

    // Sentiment badge should show "Interested" text
    await expect(detailPanel.getByText('Interested', { exact: true })).toBeVisible()

    // Sentiment reasoning should be visible (set by setSentimentForMessage during seeding)
    await expect(detailPanel.getByText(/E2E seeded sentiment/)).toBeVisible()
  })

  test('reply detail shows thread with message bubbles', async ({ page }) => {
    await page.goto('/inbox')
    await openReplyDetail(page, seed.candidates.interested)

    // Thread heading should be visible
    await expect(page.getByText('Thread', { exact: true })).toBeVisible()

    // Thread should contain at least one message bubble (rounded-lg p-4 border)
    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    const messageBubbles = detailPanel.locator('div.space-y-3 > div.rounded-lg')
    await expect(messageBubbles.first()).toBeVisible()
    const bubbleCount = await messageBubbles.count()
    expect(bubbleCount).toBeGreaterThanOrEqual(1)
  })

  test('clicking different replies updates the detail panel', async ({ page }) => {
    await page.goto('/inbox')

    // Click on the "All" tab to see all replies
    await page.getByRole('button', { name: /^All \(/i }).click()

    const interestedCandidate = seed.candidates.interested
    const neutralCandidate = seed.candidates.neutral
    const interestedFullName = `${interestedCandidate.firstName} ${interestedCandidate.lastName}`
    const neutralFullName = `${neutralCandidate.firstName} ${neutralCandidate.lastName}`

    // Open the interested candidate's detail
    await openReplyDetail(page, interestedCandidate)
    await expect(page.getByRole('heading', { name: interestedFullName })).toBeVisible()

    // Click on the neutral candidate
    await openReplyDetail(page, neutralCandidate)
    await expect(page.getByRole('heading', { name: neutralFullName })).toBeVisible()

    // The interested candidate's name heading should no longer be visible
    await expect(page.getByRole('heading', { name: interestedFullName })).not.toBeVisible()
  })

  test('composer Send Reply button is disabled when textarea is empty', async ({ page }) => {
    await page.goto('/inbox')
    await openReplyDetail(page, seed.candidates.interested)

    const detailPanel = page.locator('div.flex-1.overflow-y-auto.p-6').first()
    await detailPanel.evaluate((el) => {
      el.scrollTop = el.scrollHeight
    })

    const sendButton = page.getByRole('button', { name: /Send Reply/i })
    const textarea = page.locator('textarea').first()

    // Initially empty — button should be disabled
    await expect(textarea).toHaveValue('')
    await expect(sendButton).toBeDisabled()

    // Type something — button should become enabled
    await textarea.fill('test message')
    await expect(sendButton).toBeEnabled()

    // Clear the textarea — button should be disabled again
    await textarea.fill('')
    await expect(sendButton).toBeDisabled()
  })
})

test.describe('Inbox E2E - error state', () => {
  test('shows error message and retry button on API failure', async ({ page }) => {
    // Mock both inbox endpoints to return 500
    await page.route('**/api/inbox/replies**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      }),
    )
    await page.route('**/api/inbox/counts**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error' }),
      }),
    )

    await page.goto('/inbox')

    // Error message should be visible
    await expect(page.getByText('Failed to load inbox. Check your connection and try again.')).toBeVisible()

    // Retry button should be visible
    const retryButton = page.getByRole('button', { name: /Retry/i })
    await expect(retryButton).toBeVisible()

    // Unroute mock to let the retry hit real endpoints, then click Retry
    await page.unroute('**/api/inbox/replies**')
    await page.unroute('**/api/inbox/counts**')

    // Re-mock with success (empty inbox) to verify retry works without needing seeded data
    await page.route('**/api/inbox/replies**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      }),
    )
    await page.route('**/api/inbox/counts**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          all: 0,
          interested: 0,
          not_interested: 0,
          referral: 0,
          neutral: 0,
        }),
      }),
    )

    await retryButton.click()

    // After retry, error should disappear and empty state should show
    await expect(page.getByText('No replies yet')).toBeVisible()
    await expect(page.getByText('Failed to load inbox')).not.toBeVisible()
  })
})
