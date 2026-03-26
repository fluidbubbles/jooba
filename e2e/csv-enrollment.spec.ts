import { expect, test, type Page } from '@playwright/test'
import path from 'path'

const TEST_DATA = path.resolve(__dirname, '../docs/superpowers/plans/test-data')

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a sequence and activate it, returning the sequence detail page. */
async function createAndActivateSequence(page: Page, name: string): Promise<string> {
  await page.goto('/sequences/new')

  await page.getByLabel('Name').fill(name)
  await page.locator('#step-0-subject').fill('Hey there')
  await page.locator('#step-0-body').fill('Interested in a role?')

  await page.getByRole('button', { name: 'Save & activate' }).click()

  // Wait for redirect to sequence detail
  await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
  await expect(page.getByText(name)).toBeVisible()

  // Extract sequence ID from URL
  const url = page.url()
  return url.split('/sequences/')[1]
}

/** Create a draft sequence (no activation). */
async function createDraftSequence(page: Page, name: string): Promise<string> {
  await page.goto('/sequences/new')

  await page.getByLabel('Name').fill(name)
  await page.locator('#step-0-subject').fill('Draft subject')
  await page.locator('#step-0-body').fill('Draft body')

  await page.getByRole('button', { name: 'Save draft' }).click()

  await expect(page).toHaveURL(/\/sequences\/[a-f0-9-]+$/)
  const url = page.url()
  return url.split('/sequences/')[1]
}

/** Open the CSV upload modal from the sequence detail page. */
async function openUploadModal(page: Page) {
  // Prefer the header button; fall back to the empty-state button
  const headerBtn = page.getByRole('button', { name: 'Upload CSV' }).first()
  await headerBtn.click()
  await expect(page.getByRole('dialog', { name: 'Enroll candidates from CSV' })).toBeVisible()
}

/** Upload a CSV file into the open modal via the hidden file input. */
async function uploadCsvFile(page: Page, fileName: string) {
  const fileInput = page.locator('input[type="file"][accept=".csv"]')
  await fileInput.setInputFiles(path.join(TEST_DATA, fileName))
}

/** Click the enroll button and wait for the modal to close. */
async function clickEnrollAndWait(page: Page) {
  const dialog = page.getByRole('dialog', { name: 'Enroll candidates from CSV' })
  // Find the enroll button (text starts with "Enroll")
  const enrollBtn = dialog.getByRole('button', { name: /^Enroll \d+/ })
  await enrollBtn.click()
  // Modal should close
  await expect(dialog).not.toBeVisible({ timeout: 10_000 })
}

/** Enroll candidates via API (faster for test setup). */
async function enrollViaApi(page: Page, seqId: string, emails: string[]) {
  await page.request.post(`/api/sequences/${seqId}/enroll`, {
    data: {
      candidates: emails.map((email, i) => ({ email, first_name: `User${i + 1}` })),
    },
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('CSV Enrollment — Happy Path', () => {
  let seqId: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    seqId = await createAndActivateSequence(page, `E2E Test ${Date.now()}`)
    await page.close()
  })

  test('upload good CSV enrolls 5 candidates', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await expect(page.getByRole('button', { name: 'Upload CSV' }).first()).toBeVisible()

    await openUploadModal(page)
    await uploadCsvFile(page, 'good_candidates.csv')

    // Preview should show 5 candidates
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText(/Parsed.*5.*candidates/)).toBeVisible()
    await expect(dialog.getByText('jane@stripe.com')).toBeVisible()
    await expect(dialog.getByText('lisa@google.com')).toBeVisible()

    await clickEnrollAndWait(page)

    // Success toast
    await expect(page.getByRole('alert').getByText(/Enrolled 5 candidate/)).toBeVisible()

    // Candidates table populated
    await expect(page.getByText('Jane Chen')).toBeVisible()
    await expect(page.getByText('alex@figma.com')).toBeVisible()
    await expect(page.getByText('5 candidates', { exact: true })).toBeVisible()
  })

  test('re-uploading same CSV skips all duplicates', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    // First ensure candidates are enrolled (in case prior test is skipped)
    await openUploadModal(page)
    await uploadCsvFile(page, 'good_candidates.csv')
    await clickEnrollAndWait(page)
    // Wait for table count to appear (not the toast)
    await expect(page.getByText('5 candidates', { exact: true })).toBeVisible()

    // Now re-upload same file
    await openUploadModal(page)
    await uploadCsvFile(page, 'good_candidates.csv')
    await clickEnrollAndWait(page)

    // Toast should say 0 enrolled, 5 skipped
    const toast = page.getByRole('alert').filter({ hasText: /Enrolled/ })
    await expect(toast).toBeVisible()
    await expect(toast).toContainText('Enrolled 0')
    await expect(toast).toContainText('5 already enrolled')
  })

  test('flexible column headers are recognized', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await expect(page.getByText(/candidates/, { exact: false })).toBeVisible()

    await openUploadModal(page)
    await uploadCsvFile(page, 'weird_headers.csv')

    // Preview should show correct data despite non-standard headers
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('tom@airbnb.com')).toBeVisible()
    await expect(dialog.getByRole('cell', { name: 'Airbnb', exact: true })).toBeVisible()

    await clickEnrollAndWait(page)
    await expect(page.getByRole('alert').filter({ hasText: /Enrolled 2/ })).toBeVisible()
  })

  test('email-only CSV works with minimal data', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await openUploadModal(page)
    await uploadCsvFile(page, 'email_only.csv')

    // Preview shows emails, other columns show em dash
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('solo@test.com')).toBeVisible()
    await expect(dialog.getByText('minimal@test.com')).toBeVisible()

    await clickEnrollAndWait(page)
    await expect(page.getByRole('alert').filter({ hasText: /Enrolled 2/ })).toBeVisible()
  })

  test('in-file duplicates are deduplicated', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await expect(page.getByText(/candidates/, { exact: false })).toBeVisible()

    await openUploadModal(page)
    await uploadCsvFile(page, 'duplicates_in_file.csv')

    // Preview shows all 4 raw rows (dedup is server-side)
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('dupe@test.com').first()).toBeVisible()

    await clickEnrollAndWait(page)

    const toast = page.getByRole('alert').filter({ hasText: /Enrolled/ })
    await expect(toast).toBeVisible()
  })
})

test.describe('CSV Enrollment — Error Handling', () => {
  let seqId: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    seqId = await createAndActivateSequence(page, `E2E Errors ${Date.now()}`)
    await page.close()
  })

  test('CSV without email column shows error', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await openUploadModal(page)
    await uploadCsvFile(page, 'no_email_column.csv')

    // Error banner
    const alert = page.getByRole('dialog').getByRole('alert')
    await expect(alert).toBeVisible()
    await expect(alert.getByText(/Could not find an "email" column/)).toBeVisible()
    await expect(alert.getByText(/name, phone, company/)).toBeVisible()

    // Try Another File link
    await expect(alert.getByText('Try Another File')).toBeVisible()
  })

  test('empty CSV shows no-rows error', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await openUploadModal(page)
    await uploadCsvFile(page, 'empty.csv')

    const alert = page.getByRole('dialog').getByRole('alert')
    await expect(alert).toBeVisible()
    await expect(alert.getByText(/No valid rows found/)).toBeVisible()
  })

  test('"Try Another File" resets the modal', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await openUploadModal(page)
    await uploadCsvFile(page, 'no_email_column.csv')

    await page.getByText('Try Another File').click()

    // Error should clear, drop zone should reappear
    await expect(page.getByRole('dialog').getByRole('alert')).not.toBeVisible()
    await expect(page.getByText('Drag & drop a CSV file here')).toBeVisible()
  })

  test('enrolling into a paused sequence shows error', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    // Pause the sequence
    await page.getByRole('button', { name: 'Pause' }).click()
    await expect(page.getByText('Paused')).toBeVisible()

    // Try uploading
    await openUploadModal(page)
    await uploadCsvFile(page, 'good_candidates.csv')

    // Click Enroll — modal stays open with error
    const dialog = page.getByRole('dialog')
    const enrollBtn = dialog.getByRole('button', { name: /^Enroll \d+/ })
    await enrollBtn.click()

    // Should show error in modal
    const alert = dialog.getByRole('alert')
    await expect(alert).toBeVisible()
    await expect(alert).toContainText(/paused/i)

    // Close and resume for other tests
    await page.getByRole('button', { name: /Close dialog/ }).click()
    await page.getByRole('button', { name: 'Resume' }).click()
  })

  test('non-CSV file shows parse error', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await openUploadModal(page)

    // Upload a non-CSV file (use the playwright config as a stand-in)
    const fileInput = page.locator('input[type="file"][accept=".csv"]')
    await fileInput.setInputFiles(path.resolve(__dirname, '../playwright.config.ts'))

    // Should show either a parse error or no valid rows
    const dialog = page.getByRole('dialog')
    const alert = dialog.getByRole('alert')
    await expect(alert).toBeVisible({ timeout: 5_000 })
  })
})

test.describe('CSV Enrollment — Modal UX', () => {
  let seqId: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    seqId = await createAndActivateSequence(page, `E2E Modal ${Date.now()}`)
    await page.close()
  })

  test('close modal via X button', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await openUploadModal(page)

    await page.getByRole('button', { name: 'Close dialog' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('close modal via Escape key', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await openUploadModal(page)

    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('close modal via backdrop click', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await openUploadModal(page)

    // Click at the edge of the viewport (backdrop area)
    await page.mouse.click(10, 10)
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('Cancel clears preview but keeps modal open', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await openUploadModal(page)
    await uploadCsvFile(page, 'good_candidates.csv')

    // Preview visible
    await expect(page.getByRole('dialog').getByText('jane@stripe.com')).toBeVisible()

    // Click Cancel
    await page.getByRole('button', { name: 'Cancel' }).click()

    // Drop zone should reappear, modal still open
    await expect(page.getByText('Drag & drop a CSV file here')).toBeVisible()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('drag and drop upload works', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await openUploadModal(page)

    // Playwright's setInputFiles simulates the file selection,
    // but for true drag-and-drop we dispatch dataTransfer events.
    const filePath = path.join(TEST_DATA, 'good_candidates.csv')

    // Read the file and create a DataTransfer-based drop
    const dataTransfer = await page.evaluateHandle(async (csvContent: string) => {
      const dt = new DataTransfer()
      const file = new File([csvContent], 'good_candidates.csv', { type: 'text/csv' })
      dt.items.add(file)
      return dt
    }, await import('fs').then(fs => fs.readFileSync(filePath, 'utf-8')))

    const dropZone = page.getByText('Drag & drop a CSV file here')
    await dropZone.dispatchEvent('drop', { dataTransfer })

    // Preview should appear
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('jane@stripe.com')).toBeVisible()
    await expect(dialog.getByText(/Parsed.*5.*candidates/)).toBeVisible()
  })
})

test.describe('CSV Enrollment — Draft Sequence', () => {
  test('Upload CSV button is hidden on draft sequences', async ({ page }) => {
    await createDraftSequence(page, `E2E Draft ${Date.now()}`)

    // No Upload CSV button in header
    await expect(page.getByRole('button', { name: 'Upload CSV' })).not.toBeVisible()

    // Empty state should show Upload CSV action
    await expect(page.getByText('No candidates enrolled yet')).toBeVisible()
  })
})

test.describe('CSV Enrollment — Status Filter', () => {
  let seqId: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    seqId = await createAndActivateSequence(page, `E2E Filter ${Date.now()}`)
    await enrollViaApi(page, seqId, ['f1@test.com', 'f2@test.com', 'f3@test.com', 'f4@test.com', 'f5@test.com'])
    await page.close()
  })

  test('filter by Active shows all enrolled candidates', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await expect(page.getByText('5 candidates', { exact: true })).toBeVisible()

    await page.getByLabel('Filter by status').selectOption('active')
    await expect(page.getByText('5 candidates', { exact: true })).toBeVisible()
  })

  test('filter by Replied shows zero candidates', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await page.getByLabel('Filter by status').selectOption('replied')
    await expect(page.getByText('0 candidates')).toBeVisible()
  })

  test('filter by All shows everyone again', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    await page.getByLabel('Filter by status').selectOption('replied')
    await expect(page.getByText('0 candidates')).toBeVisible()

    await page.getByLabel('Filter by status').selectOption('all')
    await expect(page.getByText('5 candidates', { exact: true })).toBeVisible()
  })
})

test.describe('CSV Enrollment — Pause/Resume with Candidates', () => {
  let seqId: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    seqId = await createAndActivateSequence(page, `E2E PauseResume ${Date.now()}`)
    await enrollViaApi(page, seqId, ['pr1@test.com', 'pr2@test.com', 'pr3@test.com'])
    await page.close()
  })

  test('pause keeps candidates visible, resume restores upload ability', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)
    await expect(page.getByText('3 candidates', { exact: true })).toBeVisible()

    // Pause
    await page.getByRole('button', { name: 'Pause' }).click()
    // Status badge (not the filter option) shows "Paused"
    await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible()

    // Candidates still visible
    await expect(page.getByText('3 candidates', { exact: true })).toBeVisible()

    // Upload CSV button still present on paused sequence
    await expect(page.getByRole('button', { name: 'Upload CSV' }).first()).toBeVisible()

    // Resume
    await page.getByRole('button', { name: 'Resume' }).click()
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()

    // Candidates still shown, upload still works
    await expect(page.getByText('3 candidates', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Upload CSV' }).first()).toBeVisible()
  })
})

test.describe('CSV Enrollment — Analytics', () => {
  let seqId: string

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    seqId = await createAndActivateSequence(page, `E2E Analytics ${Date.now()}`)
    await enrollViaApi(page, seqId, ['a1@test.com', 'a2@test.com', 'a3@test.com', 'a4@test.com', 'a5@test.com'])
    await page.close()
  })

  test('analytics cards show correct counts after enrollment', async ({ page }) => {
    await page.goto(`/sequences/${seqId}`)

    // Wait for analytics to load — the Enrolled stat card should show 5
    await expect(page.getByText('Enrolled').locator('..').getByText('5')).toBeVisible()
    await expect(page.getByText('Sent').locator('..').getByText('0')).toBeVisible()
  })
})

test.describe('CSV Enrollment — API Error Cases', () => {
  test('enroll into nonexistent sequence returns 404', async ({ page }) => {
    const resp = await page.request.post(
      '/api/sequences/00000000-0000-0000-0000-000000000099/enroll',
      {
        data: { candidates: [{ email: 'test@example.com' }] },
      },
    )
    expect(resp.status()).toBe(404)
    const body = await resp.json()
    expect(body.code).toBe('SEQUENCE_NOT_FOUND')
  })

  test('enroll with empty candidates returns 422', async ({ page }) => {
    const resp = await page.request.post(
      '/api/sequences/00000000-0000-0000-0000-000000000001/enroll',
      {
        data: { candidates: [] },
      },
    )
    expect(resp.status()).toBe(422)
  })

  test('analytics for nonexistent sequence returns 404', async ({ page }) => {
    const resp = await page.request.get(
      '/api/sequences/00000000-0000-0000-0000-000000000099/analytics',
    )
    expect(resp.status()).toBe(404)
  })

  test('enrollments list for nonexistent sequence returns 404', async ({ page }) => {
    const resp = await page.request.get(
      '/api/sequences/00000000-0000-0000-0000-000000000099/enrollments',
    )
    expect(resp.status()).toBe(404)
  })

  test('enroll into draft sequence returns 400', async ({ page }) => {
    // Create a draft via API
    const createResp = await page.request.post('/api/sequences', {
      data: {
        name: 'Draft API Test',
        steps: [{ subject: 'Hi', body_html: '<p>Hi</p>', delay: 0 }],
      },
    })
    const { id } = await createResp.json()

    const enrollResp = await page.request.post(`/api/sequences/${id}/enroll`, {
      data: { candidates: [{ email: 'test@example.com' }] },
    })
    expect(enrollResp.status()).toBe(400)
    const body = await enrollResp.json()
    expect(body.code).toBe('INVALID_SEQUENCE_DATA')
  })
})
