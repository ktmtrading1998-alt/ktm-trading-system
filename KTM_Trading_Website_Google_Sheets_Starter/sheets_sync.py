"""One-way reporting snapshot: transactional SQLite -> Google Sheets.
Google Sheets is a reporting mirror, not a transactional database.
Run via an external scheduler, not a public HTTP endpoint.
"""
import json, os, sqlite3, sys
from datetime import datetime, timezone

TABLES = {
    'Products': ('SELECT sku,name,unit,cost_cents,retail_cents,pickup_cents,delivery_cents,reorder_level FROM products ORDER BY sku', ['SKU','Name','Unit','Cost (cents)','SRP (cents)','Pickup (cents)','Delivery (cents)','Reorder level']),
    'Warehouses': ('SELECT id,name FROM warehouses ORDER BY id', ['ID','Warehouse']),
    'Warehouse_Stock': ('''SELECT w.name,p.sku,p.name,s.qty FROM stock s JOIN warehouses w ON w.id=s.warehouse_id JOIN products p ON p.id=s.product_id ORDER BY w.name,p.sku''', ['Warehouse','SKU','Product','Quantity']),
    'Transactions': ('SELECT id,kind,ref,party,amount_cents,created_at FROM transactions ORDER BY id DESC LIMIT 5000', ['ID','Type','Reference','Party','Amount (cents)','UTC timestamp']),
    'Sales_Items': ('''SELECT si.transaction_id,p.sku,w.name,si.qty,si.unit_price_cents,si.unit_cost_cents FROM sale_items si JOIN products p ON p.id=si.product_id JOIN warehouses w ON w.id=si.warehouse_id ORDER BY si.id DESC LIMIT 10000''', ['Transaction ID','SKU','Warehouse','Qty','Sale price (cents)','Cost (cents)']),
    'Expenses': ('SELECT id,category,description,amount_cents,status,expense_date FROM expenses ORDER BY id DESC LIMIT 5000', ['ID','Category','Description','Amount (cents)','Status','Date']),
    'Payables_Receivables': ('SELECT kind,party,reference,amount_cents,paid_cents,due_date FROM ledgers ORDER BY id DESC LIMIT 5000', ['Type','Party','Reference','Amount (cents)','Paid (cents)','Due date']),
}

def get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    raw = os.environ.get('KTM_GOOGLE_SERVICE_ACCOUNT_JSON')
    path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if raw:
        info=json.loads(raw)
        credentials=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
    elif path:
        credentials=service_account.Credentials.from_service_account_file(path,scopes=['https://www.googleapis.com/auth/spreadsheets'])
    else:
        raise RuntimeError('Configure KTM_GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS')
    return build('sheets','v4',credentials=credentials,cache_discovery=False)

def export():
    spreadsheet_id=os.environ.get('KTM_GOOGLE_SHEET_ID','').strip()
    if not spreadsheet_id:raise RuntimeError('Set KTM_GOOGLE_SHEET_ID')
    from app import DB
    if not os.path.isfile(DB):raise RuntimeError('Database file does not exist; initialize server first')
    service=get_service();api=service.spreadsheets()
    metadata=api.get(spreadsheetId=spreadsheet_id,fields='sheets(properties(title))').execute()
    existing={s['properties']['title'] for s in metadata.get('sheets',[])}
    missing=[{'addSheet':{'properties':{'title':title}}} for title in TABLES if title not in existing]
    if missing:api.batchUpdate(spreadsheetId=spreadsheet_id,body={'requests':missing}).execute()
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:
        for tab,(sql,headers) in TABLES.items():
            rows=c.execute(sql).fetchall()
            values=[headers]+[[str(v) if v is not None else '' for v in row] for row in rows]
            # Clear old rows so deleted/shortened snapshots do not leave stale data.
            api.values().clear(spreadsheetId=spreadsheet_id,range=f"'{tab}'!A:Z",body={}).execute()
            api.values().update(spreadsheetId=spreadsheet_id,range=f"'{tab}'!A1",valueInputOption='RAW',body={'values':values}).execute()
            print(f'{tab}: {len(rows)} rows')
    print('Snapshot complete:',datetime.now(timezone.utc).isoformat())

if __name__=='__main__':
    try:export()
    except Exception as exc:
        print('SYNC FAILED:',exc,file=sys.stderr)
        sys.exit(1)
