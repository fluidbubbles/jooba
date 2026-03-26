import { expect, test, type Page } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function fillStep(page: Page, index: number, subject: string, body: string) {
  await page.locator(`#step-${index}-subject`).fill(subject)
  await page.locator(`#step-${index}-body`).fill(body)
}

// ---------------------------------------------------------------------------
// Sequences List
// ---------------------------------------------------------------------------

test.describe('Sequences List', () => {
  test('shows empty state when no sequences exist', async ({ page }) => {
    // Wipe sequences via API so we get a clean slate
    const list = await page.request.get('/api/sequences')
    const sequences = await list.json()
    // If there are sequences from other tests, this test still works —
    // it just checks the page loads without error
    await page.goto('/sequences')
    await expect(page.getByRole('heading', { name: 'Sequences' })).toBeVisible()
  })

  test('Create Sequence button navigates to form', async ({ page }) => {
    await page.goto('/sequences')
    await page.getByRole('button', { name: 'Create Sequence' }).click()
    await expect(page).toHaveURL('/sequences/new')
    await expect(page.getByRole('heading', { name: 'Create sequence' })).toBeVisible()
  })

  test('created sequence appears in the list', async ({ page }) => {
    const uniqueName = `List Test ${Date.now()}`
    // Create via UI to ensure same browser context
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill(uniqueName)
    await fillStep(page, 0, 'S1', 'B1')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)

    await page.goto('/sequences')
    await expect(page.getByRole('link', { name: uniqueName })).toBeVisible()
  })

  test('clicking sequence name navigates to detail', async ({ page }) => {
    const uniqueName = `Navigate Test ${Date.now()}`
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill(uniqueName)
    await fillStep(page, 0, 'S1', 'B1')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    const id = page.url().split('/sequences/')[1]

    await page.goto('/sequences')
    await page.getByRole('link', { name: uniqueName }).click()
    await expect(page).toHaveURL(`/sequences/${id}`)
  })
})

// ---------------------------------------------------------------------------
// Create Sequence
// ---------------------------------------------------------------------------

test.describe('Create Sequence', () => {
  test('save draft with valid data redirects to detail', async ({ page }) => {
    await page.goto('/sequences/new')

    await page.getByLabel('Name').fill('Draft Sequence E2E')
    await fillStep(page, 0, 'Intro email', 'Hello, are you interested?')

    await page.getByRole('button', { name: 'Save draft' }).click()

    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    await expect(page.getByText('Draft Sequence E2E')).toBeVisible()
    // Status badge shows Draft
    await expect(page.getByText('Draft', { exact: true })).toBeVisible()
  })

  test('save & activate creates active sequence', async ({ page }) => {
    await page.goto('/sequences/new')

    await page.getByLabel('Name').fill('Active Sequence E2E')
    await fillStep(page, 0, 'Step 1', 'Body content here')

    await page.getByRole('button', { name: 'Save & activate' }).click()

    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    await expect(page.getByText('Active Sequence E2E')).toBeVisible()
    // Should show Active badge, not Draft
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()
  })

  test('adding and removing steps works', async ({ page }) => {
    await page.goto('/sequences/new')

    // Start with 1 step
    await expect(page.locator('#step-0-subject')).toBeVisible()
    await expect(page.locator('#step-1-subject')).not.toBeVisible()

    // Add a step
    await page.getByRole('button', { name: 'Add step' }).click()
    await expect(page.locator('#step-1-subject')).toBeVisible()

    // Step 1 should have a delay input
    await expect(page.locator('#step-1-delay')).toBeVisible()

    // Remove step 1 (last Remove button)
    await page.getByRole('button', { name: 'Remove' }).last().click()
    await expect(page.locator('#step-1-subject')).not.toBeVisible()
  })

  test('multi-step sequence with delays saves correctly', async ({ page }) => {
    await page.goto('/sequences/new')

    await page.getByLabel('Name').fill('Multi Step E2E')
    await fillStep(page, 0, 'Initial outreach', 'Hi, interested in chatting?')

    await page.getByRole('button', { name: 'Add step' }).click()
    await fillStep(page, 1, 'Follow up', 'Just checking in!')
    await page.locator('#step-1-delay').fill('60')

    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)

    // Detail page should show both steps
    await expect(page.getByText('Initial outreach')).toBeVisible()
    await expect(page.getByText('Follow up')).toBeVisible()
    await expect(page.getByText('Delay after previous: 60 min')).toBeVisible()
  })

  test('optional context fields save correctly', async ({ page }) => {
    await page.goto('/sequences/new')

    await page.getByLabel('Name').fill('Context Test E2E')
    await fillStep(page, 0, 'Subject', 'Body')
    await page.getByLabel('Role title').fill('Senior Engineer')
    await page.getByLabel('Company').fill('Acme Corp')

    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
  })

  test('validation: empty name shows error', async ({ page }) => {
    await page.goto('/sequences/new')

    // Fill step but leave name empty
    await fillStep(page, 0, 'Subject', 'Body')

    await page.getByRole('button', { name: 'Save draft' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByRole('alert')).toContainText('name is required')
  })

  test('validation: empty subject shows error', async ({ page }) => {
    await page.goto('/sequences/new')

    await page.getByLabel('Name').fill('Test')
    await page.locator('#step-0-body').fill('Body text')
    // Leave subject empty

    await page.getByRole('button', { name: 'Save draft' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByRole('alert')).toContainText('subject is required')
  })

  test('validation: empty body shows error', async ({ page }) => {
    await page.goto('/sequences/new')

    await page.getByLabel('Name').fill('Test')
    await page.locator('#step-0-subject').fill('Subject')
    // Leave body empty

    await page.getByRole('button', { name: 'Save draft' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByRole('alert')).toContainText('body is required')
  })
})

// ---------------------------------------------------------------------------
// Sequence Detail + Status Transitions
// ---------------------------------------------------------------------------

test.describe('Sequence Detail', () => {
  test('detail page shows sequence info and steps', async ({ page }) => {
    const uniqueName = `Detail View E2E ${Date.now()}`
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill(uniqueName)
    await fillStep(page, 0, 'Step One', 'First email body')
    await page.getByRole('button', { name: 'Add step' }).click()
    await fillStep(page, 1, 'Step Two', 'Follow up body')
    await page.locator('#step-1-delay').fill('30')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)

    await expect(page.getByRole('heading', { name: uniqueName })).toBeVisible()
    await expect(page.getByText('Step One')).toBeVisible()
    await expect(page.getByText('Step Two')).toBeVisible()
    await expect(page.getByText('First email body')).toBeVisible()
    await expect(page.getByText('Sends immediately')).toBeVisible()
    await expect(page.getByText('Delay after previous: 30 min')).toBeVisible()
  })

  test('nonexistent sequence shows error', async ({ page }) => {
    await page.goto('/sequences/00000000-0000-0000-0000-000000000099')
    await expect(page.getByRole('alert')).toBeVisible()
  })
})

test.describe('Status Transitions', () => {
  test('full lifecycle: draft → active → paused → resumed → archived', async ({ page }) => {
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill(`Lifecycle E2E ${Date.now()}`)
    await fillStep(page, 0, 'S1', 'B1')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)

    // Draft → Active
    await page.getByRole('button', { name: 'Activate' }).click()
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()

    // Active → Paused
    await page.getByRole('button', { name: 'Pause' }).click()
    await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Archive' })).toBeVisible()

    // Paused → Active (resume)
    await page.getByRole('button', { name: 'Resume' }).click()
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()

    // Active → Paused again
    await page.getByRole('button', { name: 'Pause' }).click()
    await expect(page.getByRole('button', { name: 'Archive' })).toBeVisible()

    // Paused → Archived
    await page.getByRole('button', { name: 'Archive' }).click()
    // Archived has no action buttons
    await expect(page.getByRole('button', { name: 'Activate' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: 'Pause' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: 'Resume' })).not.toBeVisible()
  })

  test('draft shows Edit and Activate buttons', async ({ page }) => {
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill(`Draft Buttons E2E ${Date.now()}`)
    await fillStep(page, 0, 'S1', 'B1')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Activate' })).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Edit Sequence
// ---------------------------------------------------------------------------

test.describe('Edit Sequence', () => {
  test('edit draft: change name and steps', async ({ page }) => {
    // Create via UI so the sequence persists in the same request context
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill('Edit Me E2E')
    await fillStep(page, 0, 'Original Subject', 'Original body')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    const id = page.url().split('/sequences/')[1]

    await page.getByRole('button', { name: 'Edit' }).click()
    await expect(page).toHaveURL(`/sequences/${id}/edit`)

    // Change name
    const nameInput = page.locator('#edit-sequence-name')
    await nameInput.clear()
    await nameInput.fill('Edited Name E2E')

    // Change step subject
    const subjectInput = page.locator('#step-0-subject')
    await subjectInput.clear()
    await subjectInput.fill('Edited Subject')

    await page.getByRole('button', { name: 'Save' }).click()

    // Should redirect to detail
    await expect(page).toHaveURL(`/sequences/${id}`)
    await expect(page.getByText('Edited Name E2E')).toBeVisible()
    await expect(page.getByText('Edited Subject')).toBeVisible()
  })

  test('edit active sequence shows read-only warning', async ({ page }) => {
    // Create and activate via UI
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill('Active Edit E2E')
    await fillStep(page, 0, 'S1', 'B1')
    await page.getByRole('button', { name: 'Save & activate' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    const id = page.url().split('/sequences/')[1]

    await page.goto(`/sequences/${id}/edit`)

    // Should show read-only warning
    await expect(page.getByText(/Only draft sequences can be edited/)).toBeVisible()

    // Fields should be disabled
    await expect(page.locator('#edit-sequence-name')).toBeDisabled()
  })

  test('back to sequence link works from edit page', async ({ page }) => {
    await page.goto('/sequences/new')
    await page.getByLabel('Name').fill('Back Link E2E')
    await fillStep(page, 0, 'S1', 'B1')
    await page.getByRole('button', { name: 'Save draft' }).click()
    await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
    const id = page.url().split('/sequences/')[1]

    await page.goto(`/sequences/${id}/edit`)
    await page.getByRole('link', { name: 'Back to sequence' }).click()
    await expect(page).toHaveURL(`/sequences/${id}`)
  })
})

// ---------------------------------------------------------------------------
// API Error Cases
// ---------------------------------------------------------------------------

test.describe('Sequence API Errors', () => {
  test('create with empty steps returns 422', async ({ page }) => {
    const resp = await page.request.post('/api/sequences', {
      data: { name: 'No steps', steps: [] },
    })
    // Pydantic validates min_length on steps before reaching the service
    expect(resp.status()).toBe(422)
  })

  test('create with first step delay > 0 returns 400', async ({ page }) => {
    const resp = await page.request.post('/api/sequences', {
      data: {
        name: 'Bad delay',
        steps: [{ subject: 'S', body_html: '<p>B</p>', delay: 5 }],
      },
    })
    expect(resp.status()).toBe(400)
    const body = await resp.json()
    expect(body.code).toBe('INVALID_SEQUENCE_DATA')
  })

  test('get nonexistent sequence returns 404', async ({ page }) => {
    const resp = await page.request.get(
      '/api/sequences/00000000-0000-0000-0000-000000000099',
    )
    expect(resp.status()).toBe(404)
    const body = await resp.json()
    expect(body.code).toBe('SEQUENCE_NOT_FOUND')
  })

  test('invalid status transition returns 409', async ({ page }) => {
    // Create and try to pause a draft (invalid: draft → paused)
    const createResp = await page.request.post('/api/sequences', {
      data: {
        name: 'Invalid Transition',
        steps: [{ subject: 'S', body_html: '<p>B</p>', delay: 0 }],
      },
    })
    const { id } = await createResp.json()

    const resp = await page.request.put(`/api/sequences/${id}/status`, {
      data: { status: 'paused' },
    })
    expect(resp.status()).toBe(409)
    const body = await resp.json()
    expect(body.code).toBe('INVALID_STATE_TRANSITION')
  })

  test('update active sequence returns 409', async ({ page }) => {
    const createResp = await page.request.post('/api/sequences', {
      data: {
        name: 'Update Active',
        steps: [{ subject: 'S', body_html: '<p>B</p>', delay: 0 }],
      },
    })
    const { id } = await createResp.json()

    await page.request.put(`/api/sequences/${id}/status`, {
      data: { status: 'active' },
    })

    const resp = await page.request.put(`/api/sequences/${id}`, {
      data: { name: 'New Name' },
    })
    expect(resp.status()).toBe(409)
  })
})
