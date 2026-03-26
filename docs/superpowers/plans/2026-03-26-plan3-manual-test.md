# Plan 3 Manual Test Plan — CSV Upload + Candidates

> **Prerequisites:** `docker compose up --build -d` with all services healthy.
> Open http://localhost:3000 in your browser.

---

## Test Data Files

All CSV files are pre-created in `docs/superpowers/plans/test-data/`:

| File | Purpose |
|------|---------|
| `good_candidates.csv` | 5 candidates with all fields populated |
| `weird_headers.csv` | Non-standard column names (E-Mail, FirstName, Organization, Job_Title) |
| `no_email_column.csv` | Missing email column entirely (name, phone, company) |
| `email_only.csv` | Only an email column, no name/company/title |
| `empty.csv` | Headers only, no data rows |
| `duplicates_in_file.csv` | Same email repeated with different casing |
| `invalid_emails.csv` | Mix of valid and invalid email formats |
| `all_invalid_emails.csv` | All rows have invalid email formats |

---

## Test 1: Sequence Setup (prerequisite for all other tests)

### 1.1 Create a sequence
1. Go to http://localhost:3000/sequences
2. Click **Create Sequence**
3. Fill in:
   - Name: `Manual Test Sequence`
   - Step 1 subject: `Hey {{first_name}}`
   - Step 1 body: `<p>Interested in a role at our company?</p>`
   - Delay: `0` (should already be 0 for first step)
4. Click **Save**
5. **Verify:** Redirected to sequence detail page, status shows **Draft**

### 1.2 Check Upload CSV button is hidden on draft
- **Verify:** There is NO "Upload CSV" button in the header actions
- **Verify:** The candidates section shows an empty state: "No candidates enrolled yet" with an "Upload CSV" button
- Click the empty-state "Upload CSV" button
- **Verify:** Nothing happens (the button should be wired but enrollment will fail on a draft sequence — this tests the error path)

### 1.3 Activate the sequence
1. Click **Activate**
2. **Verify:** Status badge changes to **Active**
3. **Verify:** "Upload CSV" button now appears in the header next to "Pause"

---

## Test 2: Happy Path — Upload Good CSV

### 2.1 Open the upload modal
1. Click the **Upload CSV** button in the header
2. **Verify:** Modal opens with:
   - Title: "Enroll Candidates"
   - Drag-and-drop zone with "Drag & drop a CSV file here"
   - Expected columns hint at the bottom
   - X close button in top-right

### 2.2 Upload via file picker
1. Click the drop zone
2. Select `good_candidates.csv`
3. **Verify:** Preview table appears showing:
   - "Parsed **5** candidates from "good_candidates.csv""
   - Table with columns: Email, First, Last, Company, Title
   - All 5 rows visible with correct data
   - Footer buttons: "Cancel" and "Enroll 5"

### 2.3 Enroll candidates
1. Click **Enroll 5**
2. **Verify:** Button changes to "Enrolling..."
3. **Verify:** Modal closes
4. **Verify:** Green success toast appears: "Enrolled 5 candidates."
5. **Verify:** Toast disappears after ~5 seconds
6. **Verify:** Candidates table now shows 5 rows with:
   - Names: Jane Chen, Alex Kumar, Sarah Park, Mike Johnson, Lisa Wang
   - Emails: jane@stripe.com, etc.
   - Step: "0 of 1"
   - Status: Active (blue badge)
   - Sentiment: — (em dash)
7. **Verify:** Count text above table: "5 candidates"
8. **Verify:** Analytics cards update:
   - Enrolled: 5
   - Sent: 0
   - Replied: 0
   - Interested: 0
   - Bounced: 0

---

## Test 3: Duplicate Upload (idempotency)

### 3.1 Re-upload the same file
1. Click **Upload CSV** again
2. Select `good_candidates.csv` again
3. Click **Enroll 5**
4. **Verify:** Success toast shows: "Enrolled 0 candidates. 5 already enrolled (skipped)."
5. **Verify:** Table still shows exactly 5 candidates (no duplicates)
6. **Verify:** Analytics still shows Enrolled: 5

---

## Test 4: Flexible Column Headers

### 4.1 Upload CSV with non-standard headers
1. Click **Upload CSV**
2. Select `weird_headers.csv` (uses "E-Mail", "FirstName", "Last", "Organization", "Job_Title")
3. **Verify:** Preview shows 2 candidates with correct data:
   - Tom Lee, tom@airbnb.com, Airbnb, Backend Lead
   - Nina Patel, nina@uber.com, Uber, Tech Lead
4. Click **Enroll 2**
5. **Verify:** Toast: "Enrolled 2 candidates."
6. **Verify:** Table now shows 7 total candidates

---

## Test 5: Email-Only CSV (minimal data)

### 5.1 Upload CSV with only email column
1. Click **Upload CSV**
2. Select `email_only.csv`
3. **Verify:** Preview shows 2 rows with:
   - Email filled in
   - First, Last, Company, Title all show "—" (em dash)
4. Click **Enroll 2**
5. **Verify:** Toast: "Enrolled 2 candidates."
6. **Verify:** Table shows 9 candidates. The two new ones show email prefix as the name (e.g., "solo", "minimal")

---

## Test 6: In-File Duplicates

### 6.1 Upload CSV with duplicate emails (different casing)
1. Click **Upload CSV**
2. Select `duplicates_in_file.csv`
3. **Verify:** Preview shows 4 rows (the parser shows raw rows, dedup happens server-side)
4. Click **Enroll 4**
5. **Verify:** Toast: "Enrolled 2 candidates." (dupe@test.com counted once + unique@test.com, total=4 in the batch but only 2 new)
6. **Verify:** Table now shows 11 total candidates

---

## Test 7: Error — No Email Column

### 7.1 Upload CSV without an email column
1. Click **Upload CSV**
2. Select `no_email_column.csv`
3. **Verify:** Error banner appears (red) with message like:
   - `Could not find an "email" column. Found columns: name, phone, company`
4. **Verify:** "Try Another File" link appears below the error
5. Click **Try Another File**
6. **Verify:** Error clears, drop zone reappears

---

## Test 8: Error — Empty CSV

### 8.1 Upload CSV with headers but no data rows
1. Click **Upload CSV**
2. Select `empty.csv`
3. **Verify:** Error: "No valid rows found. Make sure the CSV has at least one row with an email."
4. Click **Try Another File**, then close the modal with X

---

## Test 9: Modal Dismissal

### 9.1 Close via X button
1. Open modal, **Verify** it opens
2. Click the X button in the top-right
3. **Verify:** Modal closes

### 9.2 Close via Escape key
1. Open modal
2. Press **Escape** key
3. **Verify:** Modal closes

### 9.3 Close via backdrop click
1. Open modal
2. Click the dark backdrop area outside the white dialog
3. **Verify:** Modal closes

### 9.4 Cancel after parsing
1. Open modal, upload `good_candidates.csv`
2. Preview appears with "Enroll 5"
3. Click **Cancel** (not "Enroll")
4. **Verify:** Preview clears, drop zone reappears (modal stays open)
5. Close via X

---

## Test 10: Status Filter

### 10.1 Filter candidates by status
1. On the sequence detail page with 11 enrolled candidates
2. Use the status filter dropdown (top-right of candidates section)
3. Select **Active**
4. **Verify:** All 11 candidates shown (all are Active)
5. Select **Replied**
6. **Verify:** "0 candidates" shown, table is empty
7. Select **Completed**
8. **Verify:** "0 candidates" shown
9. Select **All**
10. **Verify:** All 11 candidates shown again

---

## Test 11: Enrollment on Draft Sequence (should fail)

### 11.1 Create a new draft sequence and try to enroll
1. Go to /sequences, create a new sequence ("Draft Test"), save it
2. Stay on the draft detail page — note there's no "Upload CSV" button in header
3. Open browser dev tools (Network tab)
4. Manually hit the API: in the browser console, run:
   ```js
   fetch('/api/sequences/PASTE_SEQ_ID/enroll', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({candidates: [{email: 'test@test.com'}]})
   }).then(r => r.json()).then(console.log)
   ```
5. **Verify:** Response is `400` with `{"error": "Cannot enroll into a draft sequence. Activate it first.", "code": "INVALID_SEQUENCE_DATA"}`

---

## Test 12: Enrollment on Nonexistent Sequence

### 12.1 Hit API with fake UUID
In browser console:
```js
fetch('/api/sequences/00000000-0000-0000-0000-000000000099/enroll', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({candidates: [{email: 'test@test.com'}]})
}).then(r => r.json()).then(console.log)
```
**Verify:** Response is `404` with `{"code": "SEQUENCE_NOT_FOUND"}`

---

## Test 13: Analytics Endpoint Directly

### 13.1 Check analytics for active sequence
In browser console (use the active sequence ID from Test 1):
```js
fetch('/api/sequences/PASTE_SEQ_ID/analytics')
  .then(r => r.json()).then(console.log)
```
**Verify:** Response includes `enrolled: 11`, `sent: 0`, `replied: 0`, all sentiment counts at 0

### 13.2 Check analytics for nonexistent sequence
```js
fetch('/api/sequences/00000000-0000-0000-0000-000000000099/analytics')
  .then(r => r.json()).then(console.log)
```
**Verify:** Response is `404`

---

## Test 14: Drag and Drop Upload

### 14.1 Drag a CSV file onto the drop zone
1. Open the Upload CSV modal
2. Drag `good_candidates.csv` from your desktop onto the drop zone
3. **Verify:** File is parsed and preview appears (same as file picker)
4. Close the modal without enrolling

---

## Test 15: Pause and Resume with Candidates

### 15.1 Pause the active sequence
1. On the sequence detail page (active, with candidates)
2. Click **Pause**
3. **Verify:** Status changes to **Paused**
4. **Verify:** "Upload CSV" button is **NOT** visible in header (only active sequences show it)
5. **Verify:** Candidates table still shows all candidates
6. **Verify:** Empty state "Upload CSV" action button is also hidden (no `onUploadCsv` prop)

### 15.2 Resume the sequence
1. Click **Resume**
2. **Verify:** Status returns to **Active**
3. **Verify:** Upload CSV button reappears in header, candidates still shown

---

## Test 16: Non-CSV File

### 16.1 Upload a non-CSV file
1. Open Upload CSV modal
2. The file picker should filter to `.csv` only, but if you can select another file type:
3. **Verify:** Either the file picker blocks it, or the parser shows an error: "Could not parse this file. Make sure it is a valid CSV."

---

## Test 17: Invalid Email Validation

### 17.1 CSV with mix of valid and invalid emails
1. Click **Upload CSV**
2. Select `invalid_emails.csv` (has 2 valid + 3 invalid email rows)
3. **Verify:** Preview shows only the 2 valid candidates (`valid@test.com`, `another@valid.com`)
4. **Verify:** Amber warning banner appears: "3 row(s) were skipped because they had invalid email format."
5. Click **Enroll 2**
6. **Verify:** Success toast: "Enrolled 2 candidates."

### 17.2 CSV with all invalid emails
1. Click **Upload CSV**
2. Select `all_invalid_emails.csv`
3. **Verify:** Error: "No valid rows found. 3 row(s) had invalid email format."

---

## Test 18: Focus Trap and Keyboard Navigation

### 18.1 Focus moves to close button on open
1. Open Upload CSV modal
2. **Verify:** The close (X) button receives focus automatically

### 18.2 Tab cycles within modal
1. With the modal open (drop zone visible), press **Tab** repeatedly
2. **Verify:** Focus cycles through the modal elements (close button, drop zone) and does NOT escape to the page behind
3. Press **Shift+Tab**
4. **Verify:** Focus cycles backwards within the modal

### 18.3 Focus restores on close
1. Click the **Upload CSV** button to open the modal (note: it was the focused button)
2. Close the modal (via X or Escape)
3. **Verify:** Focus returns to the Upload CSV button that was focused before

---

## Test 19: Upload CSV Hidden on Non-Active Sequences

### 19.1 Draft sequence hides upload everywhere
1. Create a new draft sequence
2. **Verify:** No "Upload CSV" button in header
3. **Verify:** Empty state shows "No candidates enrolled yet" but the "Upload CSV" action button is hidden

### 19.2 Paused sequence hides upload everywhere
1. Create and activate a sequence, then pause it
2. **Verify:** No "Upload CSV" button in header
3. **Verify:** If no candidates, empty state shows but "Upload CSV" action button is hidden

---

## Test Summary Checklist

| # | Test | Expected | Pass? |
|---|------|----------|-------|
| 1 | Sequence create + activate | Draft created, activated, Upload CSV appears | |
| 2 | Upload good CSV | 5 candidates enrolled, table + analytics update | |
| 3 | Re-upload same CSV | 0 enrolled, 5 skipped | |
| 4 | Flexible headers | E-Mail/FirstName/Organization all recognized | |
| 5 | Email-only CSV | 2 enrolled with email prefix as name | |
| 6 | In-file duplicates | Deduped by email (case-insensitive) | |
| 7 | No email column | Error with column list shown | |
| 8 | Empty CSV | "No valid rows" error | |
| 9 | Modal dismiss (X / Escape / backdrop / Cancel) | All four dismissal paths work | |
| 10 | Status filter dropdown | Filters all 6 statuses correctly | |
| 11 | Enroll on draft sequence | 400 INVALID_SEQUENCE_DATA | |
| 12 | Enroll on nonexistent sequence | 404 SEQUENCE_NOT_FOUND | |
| 13 | Analytics endpoint | Returns correct counts | |
| 14 | Drag and drop | File parsed same as file picker | |
| 15 | Pause/resume with candidates | Pause hides upload, resume restores | |
| 16 | Non-CSV file | Parse error or file picker blocks | |
| 17 | Invalid email validation | Bad emails skipped with warning, all-bad shows error | |
| 18 | Focus trap + keyboard nav | Focus auto-set, Tab trapped, focus restored on close | |
| 19 | Upload CSV hidden on non-active | Draft + paused hide upload button everywhere | |
