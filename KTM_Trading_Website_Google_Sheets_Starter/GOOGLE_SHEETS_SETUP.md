# KTM Trading Website + Google Sheets (reporting mirror)

## Architecture and security
The KTM Trading website is the employee-facing application. The **server SQLite database remains the transactional source of truth**. `sheets_sync.py` publishes a **one-way snapshot** of products, warehouses, stock, transactions, sales items, expenses and payables/receivables to a private Google Sheet. This is intentional: Sheets is not a reliable multi-user transactional database for concurrent POS operations. Editing cells in Sheets **does not update the website**.

**Do not share the Sheet with employees.** Only the owner and designated accountants should have access. The export deliberately excludes login users, password hashes, sessions, payroll and employee details. Financial costs are included in the owner-only spreadsheet. Never store the service account private key in a spreadsheet or source repository.

## Setup
1. Extract the ZIP. Follow `README.md` and `ACCOUNT_SECURITY_README.md` to configure the Python website, create an Admin, and run the server locally first. Use strong unique passwords. Do not deploy until access controls have been independently verified.
2. Create a private Google Sheet in your regular Gmail account named `KTM Trading Reports`. Copy its spreadsheet ID from the URL.
3. In Google Cloud Console, create a project, enable **Google Sheets API**, create a **service account**, and create a JSON credential for that service account. Keep the JSON file private and outside the project directory. Restrict the service account to this one Sheet by sharing the Sheet with the service account's email as **Editor**. You do not need Google Workspace.
4. Install dependencies: `pip install -r requirements.txt`.
5. Set `KTM_GOOGLE_SHEET_ID` to the ID. Set `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of your service-account JSON (or use secret env var `KTM_GOOGLE_SERVICE_ACCOUNT_JSON` containing its JSON). Also set `KTM_SECRET_KEY` and `KTM_DB_PATH` as described in `README.md`.
6. Run `python sheets_sync.py`. It will create reporting tabs and overwrite their snapshots. This script must be invoked by an administrator or a private scheduled job, **never by an unauthenticated website endpoint**.
7. Schedule this command every 5–15 minutes using your hosting provider's private cron/worker service if you want periodic updates. Snapshot updates are not real-time. A failed run must be monitored and retried.

## Important production limitations
- This is a **deployment starter**, not a live deployed website, a completed Google Sheets-backed POS, or a security-certified system.
- The website currently uses SQLite. A production multi-instance hosting environment needs a migration to PostgreSQL and transaction tests; do not use ephemeral storage for SQLite.
- Passwords, role authorization and sessions must remain on the server. Review role checks for every endpoint before onboarding employees. Add MFA, rate limiting, managed secrets, monitoring and offsite backups before production.
- A Sheets snapshot is **not a backup**. Set up database backups and test restoration.
- The account-upgrade code may include features beyond the visible browser interface; verify end-to-end workflows, accounting reconciliation, and the exact permissions for every role.
- The sync has not been tested against a live Google Cloud project in this environment. API credentials and network access are needed.
