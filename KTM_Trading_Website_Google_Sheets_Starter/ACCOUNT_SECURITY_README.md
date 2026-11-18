# KTM Trading — Admin User Management and Secure Login

This package adds account creation, temporary passwords, password resets, disabling/reactivating users, password changes, account lockout after five failures (15 minutes), session invalidation after resets and deactivation, server-side authorization, and audit entries.

## Run locally

1. Install Python 3.11+ and `pip install -r requirements.txt`.
2. Set `KTM_SECRET_KEY` to a unique random secret of at least 32 characters.
3. Run `python create_admin.py` (follow prompts), then `python app.py`.
4. Open `http://127.0.0.1:8080` and sign in.
5. In Accounts & Backup, create individual employee accounts and temporary passwords.
6. Require staff to change their temporary password; this package marks the account for a change but DOES NOT enforce a password change before business operations. Admin should instruct employees to change it immediately.

## Important architecture clarification

This is the secure Flask server edition using SQLite, NOT a Google Apps Script deployment and NOT connected to Google Sheets. The earlier Apps Script pilot uses Workspace identity and is NOT safe for personal-Gmail username/password use as-is. To retain Google Sheets, the next development stage must implement a controlled Google Sheets sync/reporting integration or an external authentication backend. Do not publish the Apps Script pilot publicly.

## Before production

Move transaction storage to PostgreSQL for multi-instance cloud deployment; configure HTTPS, rate limiting at proxy, monitoring, offsite encrypted backups, restore tests, and end-to-end POS/financial tests. The existing SQLite Render disk configuration is for a single-instance pilot. Password reset is admin-driven; do not send passwords by unsecured channels.
