# KTM Trading Secure Server — operational foundation

**This is a new server-backed application, NOT a drop-in replacement or migration of the old Chrome HTML file.** It includes account authentication, per-user roles, 5 starting warehouses, products and prices, stock receipts, transfers, adjustments, disposals, sellable returns, POS sales, stock balances, audit logs, and basic gross-profit reporting. It does **not** yet implement supplier canvassing, payables, receivables, payroll, vehicle/shop maintenance, expenses, full P&L, refund accounting, or automated migration from the existing HTML data. Do not use it as the sole accounting system.

## Setup (Windows / Mac / Linux)

1. Install Python 3.11+.
2. Open a terminal in this extracted folder.
3. `python -m venv .venv` then activate it (`.venv\\Scripts\\activate` on Windows; `source .venv/bin/activate` on Mac/Linux).
4. `pip install -r requirements.txt`
5. Set `KTM_SECRET_KEY` to a fresh random string of 32+ characters, e.g. generate using `python -c "import secrets; print(secrets.token_urlsafe(48))"`. On Windows PowerShell: `$env:KTM_SECRET_KEY="paste-your-generated-secret"`; on Mac/Linux: `export KTM_SECRET_KEY="paste-your-generated-secret"`.
6. `python create_admin.py` (choose a private password of 12+ characters). Optional: `python create_employee.py`.
7. For local evaluation: `python app.py` and open `http://127.0.0.1:8080`.

## Production hosting

Use a dedicated server and reverse proxy with HTTPS and `KTM_HTTPS=1`, a persistent database volume, firewall rules, monitoring, and automatic encrypted offsite backups. Run `waitress-serve --listen=127.0.0.1:8080 app:app` behind the HTTPS proxy. Initialize database once with `python -c "from app import init_db; init_db()"`. Never expose the local HTTP development server publicly. Keep the secret key stable and out of source control. Use unique employee passwords. SQLite works for a modest single-server installation; larger concurrency should move to PostgreSQL and an audited deployment.

## Critical limitations

- Not penetration-tested, not a certified production deployment; rate limiting/MFA/account lockout, formal backup restoration drills, and operational monitoring remain to be added.
- This release records sales as full sales totals but **does not** implement partial payments, credit ledgers, tax/VAT, discounts, cash drawer, or refunds.
- Stock is tracked in whole-number units only.
- Existing Chrome localStorage data is **not** imported automatically. Export the old JSON backup and reconcile opening stock before using this server.
- The browser must access the same hosted server to share data; opening an HTML file alone will not connect to the database.
- Backup the SQLite file using SQLite's online backup API (do not simply copy the live WAL database files while writes are active).
