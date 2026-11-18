# KTM Trading — Cloud deployment guide

This package is a **cloud-deployable pilot**, not a complete production-certified accounting/ERP system. It is based on the secure server starter. Do not import live company data until a complete security review, end-to-end tests, and backup/restore drill have passed.

## Deploy on Render (paid service with persistent disk)

1. Put this folder in a **private Git repository**. Do not commit database files, `.env` files, backups, or passwords.
2. In Render, choose **New > Blueprint** and connect the repository containing `render.yaml` at its root. If this directory is nested in your repository, make it the root or adjust the blueprint location.
3. Review the Starter service and **persistent disk** charges before confirming. The blueprint creates a web service with a persistent SQLite volume and a generated secret key.
4. Wait for deployment; visit the provided HTTPS URL. `/healthz` should return `{"status":"ok"}`.
5. Create the first admin **using a secure shell on the deployed instance**: `python create_admin.py`. Choose a unique username and password; no demo credentials are provisioned. If shell access is unavailable on your plan, arrange a one-time private admin provisioning procedure before launch. Do not expose a public admin-creation endpoint.
6. Create employees using `python create_employee.py` from the secure server shell. Each employee should have an individual account.
7. Configure **automatic encrypted offsite backups** and practice restoration. The attached persistent disk alone is **not a backup**. Use the SQLite online backup API; schedule backup copies to independent storage.
8. Set up a custom domain, monitoring, incident response, and documented user offboarding. Keep the generated `KTM_SECRET_KEY` stable during upgrades.

## Limitations / safety requirements

- The app currently uses **SQLite**. It is suitable for a modest single-instance pilot but not horizontal scaling or heavy concurrent traffic. Do not run multiple independent instances against the same SQLite file.
- The server supports Admin and Employee roles, but **MFA, login rate limiting, lockouts, password resets, granular permissions, and formal security testing are not implemented**. Restrict access to trusted staff until these are added.
- Full payables, receivables, payroll, expenses, returns accounting, supplier canvassing, maintenance, consolidated P&L, and migration from the old HTML application are not yet implemented.
- Current reports provide **gross profit only**, not reconciled net profit. Do not use them for statutory reporting.
- This bundle is **not deployed** by ChatGPT; the operator must connect a hosting account and configure production operations.
