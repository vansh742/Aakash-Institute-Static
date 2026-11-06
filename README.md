# Aakash Institute — Khamgaon

A responsive, multi-page branch website with an admission enquiry form, faculty page, scholarship information, live news feed and a PIN-protected administrator workspace.

## Start the website

Requires Python 3.10 or later. No third-party packages are needed.

In PowerShell, open this folder and run:

```powershell
$env:AAKASH_ADMIN_PIN = 'choose-a-private-pin'
python server.py
```

Then open <http://127.0.0.1:8000>. To manage announcements and enquiries, open **Branch admin** in the footer and sign in with the PIN you set. Admission submissions and posts are stored in `data/branch.db`. The admin can export enquiries as CSV.

By default, the server listens only on your own computer (`127.0.0.1`). The deployment settings below allow a hosting provider to serve the site publicly and preserve the database.

## Publishing preparation

The app can run as a Railway Python service. Railway supports deployment from a local folder, so a GitHub repository is optional. Set these service variables and settings:

- `HOST=0.0.0.0`
- `AAKASH_DATA_DIR=/app/data`
- `AAKASH_ADMIN_PIN` to a strong private PIN
- Start command: `python server.py`
- Attach a persistent volume at `/app/data`

The server reads Railway's `PORT` variable. Keep the `data/` folder out of source control; the persistent volume stores the live SQLite database.

To deploy from a regular PowerShell on the same computer:

```powershell
railway login
railway init
railway up
```

Then attach a volume at `/app/data`, set the service variables above, and enable a public domain in Railway. Use `railway link` instead of `railway init` if you already have a Railway project for this site.

Before accepting real student enquiries on a public site, add the branch’s approved privacy notice and retention/contact details. The current form is a prototype and does not send email notifications; staff review enquiries in the administrator page.

## Pages

- Home: `index.html`
- Courses: `courses.html`
- Faculty: `faculty.html`
- Scholarships: `scholarships.html`
- News & updates: `updates.html`
- Admissions: `admissions.html`
- Branch admin: `admin.html`

The faculty page uses clearly marked subject profiles until the Khamgaon branch confirms individual names, experience and assignments. The Aakash logo image is sourced from Wikimedia Commons; that file page identifies Aakash.ac.in as its original source.
