import os, sqlite3, secrets, json, csv, io, hmac, time
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, session, redirect, render_template, jsonify, Response, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.environ.get('KTM_DB_PATH',os.path.join(BASE,'ktm_data.sqlite3'))
app=Flask(__name__)
secret=os.environ.get('KTM_SECRET_KEY')
if not secret or len(secret)<32: raise RuntimeError('Set KTM_SECRET_KEY to a random value of at least 32 characters')
app.secret_key=secret
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('KTM_HTTPS','0')=='1',MAX_CONTENT_LENGTH=2*1024*1024,PERMANENT_SESSION_LIFETIME=__import__('datetime').timedelta(hours=8))

def conn():
 c=sqlite3.connect(DB,timeout=20,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=20000');return c

def init_db():
 os.makedirs(os.path.dirname(DB),exist_ok=True)
 with conn() as c:
  c.executescript('''
  PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','employee')), active INTEGER NOT NULL DEFAULT 1, auth_version INTEGER NOT NULL DEFAULT 0, failed_logins INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0, must_change_password INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE IF NOT EXISTS warehouses(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
  CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL DEFAULT 'pcs',cost_cents INTEGER NOT NULL DEFAULT 0,retail_cents INTEGER NOT NULL DEFAULT 0,pickup_cents INTEGER NOT NULL DEFAULT 0,delivery_cents INTEGER NOT NULL DEFAULT 0,reorder_level INTEGER NOT NULL DEFAULT 5);
  CREATE TABLE IF NOT EXISTS stock(warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),product_id INTEGER NOT NULL REFERENCES products(id),qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0),PRIMARY KEY(warehouse_id,product_id));
  CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,ref TEXT,party TEXT,amount_cents INTEGER NOT NULL DEFAULT 0,actor_id INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,transaction_id INTEGER NOT NULL REFERENCES transactions(id),warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),product_id INTEGER NOT NULL REFERENCES products(id),delta INTEGER NOT NULL,unit_cost_cents INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY,transaction_id INTEGER NOT NULL REFERENCES transactions(id),product_id INTEGER NOT NULL REFERENCES products(id),warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),qty INTEGER NOT NULL CHECK(qty>0),unit_price_cents INTEGER NOT NULL,unit_cost_cents INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor_id INTEGER REFERENCES users(id),action TEXT NOT NULL,details TEXT,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS parties(id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('supplier','customer')),name TEXT NOT NULL,contact TEXT DEFAULT '');
  CREATE TABLE IF NOT EXISTS quotations(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),supplier TEXT NOT NULL,qty INTEGER NOT NULL CHECK(qty>0),unit_cents INTEGER NOT NULL CHECK(unit_cents>=0),freight_cents INTEGER NOT NULL DEFAULT 0,valid_until TEXT,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS ledgers(id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('payable','receivable')),party TEXT NOT NULL,reference TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents>0),paid_cents INTEGER NOT NULL DEFAULT 0 CHECK(paid_cents>=0 AND paid_cents<=amount_cents),due_date TEXT,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS ledger_payments(id INTEGER PRIMARY KEY,ledger_id INTEGER NOT NULL REFERENCES ledgers(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),method TEXT NOT NULL,reference TEXT,actor_id INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,position TEXT,rate_cents INTEGER NOT NULL DEFAULT 0 CHECK(rate_cents>=0),active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS payroll(id INTEGER PRIMARY KEY,employee_id INTEGER NOT NULL REFERENCES employees(id),period_start TEXT NOT NULL,period_end TEXT NOT NULL,gross_cents INTEGER NOT NULL CHECK(gross_cents>=0),deductions_cents INTEGER NOT NULL CHECK(deductions_cents>=0 AND deductions_cents<=gross_cents),status TEXT NOT NULL CHECK(status IN ('pending','paid')),created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,category TEXT NOT NULL,description TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents>0),status TEXT NOT NULL CHECK(status IN ('unpaid','paid')),expense_date TEXT NOT NULL,actor_id INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS return_items(id INTEGER PRIMARY KEY,original_sale_item_id INTEGER REFERENCES sale_items(id),transaction_id INTEGER NOT NULL REFERENCES transactions(id),product_id INTEGER NOT NULL REFERENCES products(id),warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),qty INTEGER NOT NULL CHECK(qty>0),disposition TEXT NOT NULL,credit_cents INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS idx_ledger_kind ON ledgers(kind);
  CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date);
  CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);
  ''')
  existing={r[1] for r in c.execute('PRAGMA table_info(users)')}
  for col,typ in [('auth_version','INTEGER NOT NULL DEFAULT 0'),('failed_logins','INTEGER NOT NULL DEFAULT 0'),('locked_until','INTEGER NOT NULL DEFAULT 0'),('must_change_password','INTEGER NOT NULL DEFAULT 0')]:
   if col not in existing:c.execute('ALTER TABLE users ADD COLUMN '+col+' '+typ)
  if not c.execute('SELECT 1 FROM warehouses LIMIT 1').fetchone():
   c.executemany('INSERT INTO warehouses(name) VALUES (?)',[(f'Warehouse {i}',) for i in range(1,6)])

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def audit(c,action,details=''):c.execute('INSERT INTO audit(actor_id,action,details,created_at) VALUES (?,?,?,?)',(session.get('uid'),action,details,now()))
def integer(v,name,minimum=0):
 try:
  if isinstance(v,bool) or str(int(v))!=str(v).strip():raise ValueError()
  n=int(v)
  if n<minimum:raise ValueError()
  return n
 except (TypeError,ValueError):raise ValueError(f'{name} must be an integer >= {minimum}')
def cents(v,name):
 try:
  d=Decimal(str(v)); n=d*100
  if not d.is_finite() or d<0 or n!=n.to_integral_value():raise ValueError()
  return int(n)
 except (InvalidOperation,ValueError):raise ValueError(f'{name} must be a nonnegative amount with up to 2 decimals')
def required(v,name):
 s=str(v or '').strip()
 if not s or len(s)>160:raise ValueError(f'{name} is required (max 160 characters)')
 return s

def auth(role=None):
 def outer(fn):
  @wraps(fn)
  def inner(*a,**kw):
   if not session.get('uid'):return jsonify(error='Login required'),401
   with conn() as c:current=c.execute('SELECT role,active,auth_version FROM users WHERE id=?',(session['uid'],)).fetchone()
   if not current or not current['active'] or current['auth_version']!=session.get('auth_version') or current['role']!=session.get('role'):
    session.clear();return jsonify(error='Session expired or account changed'),401
   if role and session.get('role')!=role:return jsonify(error='Admin permission required'),403
   return fn(*a,**kw)
  return inner
 return outer

@app.before_request
def csrf_guard():
 if request.method in ('POST','PUT','PATCH','DELETE') and request.endpoint not in ('login',):
  if not session.get('uid'):return jsonify(error='Login required'),401
  if not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','')):return jsonify(error='Invalid session token'),403

@app.after_request
def security_headers(resp):
 resp.headers['X-Content-Type-Options']='nosniff';resp.headers['X-Frame-Options']='DENY';resp.headers['Referrer-Policy']='no-referrer';resp.headers['Cache-Control']='no-store';resp.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
 return resp

@app.errorhandler(ValueError)
def bad_input(e):return jsonify(error=str(e)),400
@app.errorhandler(sqlite3.IntegrityError)
def integrity(e):return jsonify(error='Database constraint violated; check SKU, stock, or warehouse'),409

@app.get('/healthz')
def healthz():
 try:
  with conn() as c:c.execute('SELECT 1').fetchone()
  return jsonify(status='ok')
 except sqlite3.Error:
  return jsonify(status='unavailable'),503

@app.get('/')
def index():return render_template('index.html')
@app.post('/api/login')
def login():
 d=request.get_json(silent=True) or {};username=str(d.get('username',''))[:80];password=str(d.get('password',''))
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  u=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
  if not u or not u['active']:
   c.commit();time.sleep(.3);return jsonify(error='Invalid username or password'),401
  if u['locked_until']>int(time.time()):
   c.commit();return jsonify(error='Account temporarily locked; try again later'),429
  if not check_password_hash(u['password_hash'],password):
   failures=u['failed_logins']+1
   lock=int(time.time())+900 if failures>=5 else 0
   c.execute('UPDATE users SET failed_logins=?,locked_until=? WHERE id=?',(0 if lock else failures,lock,u['id']))
   c.commit();time.sleep(.3);return jsonify(error='Invalid username or password'),401
  c.execute('UPDATE users SET failed_logins=0,locked_until=0 WHERE id=?',(u['id'],));c.commit()
 session.clear();session.permanent=True;session['uid']=u['id'];session['role']=u['role'];session['username']=u['username'];session['auth_version']=u['auth_version'];session['csrf']=secrets.token_urlsafe(32)
 return jsonify(username=u['username'],role=u['role'],csrf=session['csrf'],must_change_password=bool(u['must_change_password']))
@app.post('/api/logout')
@auth()
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/me')
@auth()
def me():return jsonify(username=session['username'],role=session['role'],csrf=session['csrf'])
@app.get('/api/state')
@auth()
def state():
 with conn() as c:
  products=[dict(r) for r in c.execute('SELECT id,sku,name,unit,retail_cents,pickup_cents,delivery_cents,reorder_level'+(',cost_cents' if session['role']=='admin' else '')+' FROM products ORDER BY name')]
  warehouses=[dict(r) for r in c.execute('SELECT * FROM warehouses ORDER BY id')]
  stocks=[dict(r) for r in c.execute('SELECT * FROM stock')]
  tx=[dict(r) for r in c.execute('SELECT t.id,t.kind,t.ref,t.party,t.amount_cents,t.created_at,u.username actor FROM transactions t LEFT JOIN users u ON u.id=t.actor_id ORDER BY t.id DESC LIMIT 100')]
 return jsonify(products=products,warehouses=warehouses,stocks=stocks,transactions=tx)
@app.post('/api/warehouses')
@auth('admin')
def warehouse():
 d=request.get_json() or {};name=required(d.get('name'),'Warehouse name')
 with conn() as c:c.execute('INSERT INTO warehouses(name) VALUES (?)',(name,));audit(c,'warehouse.create',name)
 return jsonify(ok=True)
@app.post('/api/products')
@auth('admin')
def product():
 d=request.get_json() or {};sku=required(d.get('sku'),'SKU').upper();name=required(d.get('name'),'Product name');unit=required(d.get('unit') or 'pcs','Unit')
 cost=cents(d.get('cost',0),'Cost');retail=cents(d.get('retail',0),'SRP');pickup=cents(d.get('pickup',0),'Pick-up');delivery=cents(d.get('delivery',0),'Delivery');reorder=integer(d.get('reorder',5),'Reorder level')
 with conn() as c:
  c.execute('INSERT INTO products(sku,name,unit,cost_cents,retail_cents,pickup_cents,delivery_cents,reorder_level) VALUES (?,?,?,?,?,?,?,?)',(sku,name,unit,cost,retail,pickup,delivery,reorder));audit(c,'product.create',sku)
 return jsonify(ok=True)

def apply_stock(c,w,p,delta):
 if not c.execute('SELECT 1 FROM warehouses WHERE id=?',(w,)).fetchone():raise ValueError('Unknown warehouse')
 if not c.execute('SELECT 1 FROM products WHERE id=?',(p,)).fetchone():raise ValueError('Unknown product')
 c.execute('INSERT OR IGNORE INTO stock(warehouse_id,product_id,qty) VALUES (?,?,0)',(w,p))
 if delta<0:
  result=c.execute('UPDATE stock SET qty=qty+? WHERE warehouse_id=? AND product_id=? AND qty>=?',(delta,w,p,-delta))
  if result.rowcount!=1:raise ValueError('Insufficient stock in selected warehouse')
 else:c.execute('UPDATE stock SET qty=qty+? WHERE warehouse_id=? AND product_id=?',(delta,w,p))
def transaction(c,kind,ref='',party='',amount=0):
 cur=c.execute('INSERT INTO transactions(kind,ref,party,amount_cents,actor_id,created_at) VALUES (?,?,?,?,?,?)',(kind,ref,party,amount,session['uid'],now()));return cur.lastrowid
def move(c,tid,w,p,delta):
 cost=c.execute('SELECT cost_cents FROM products WHERE id=?',(p,)).fetchone()['cost_cents'];apply_stock(c,w,p,delta)
 c.execute('INSERT INTO movements(transaction_id,warehouse_id,product_id,delta,unit_cost_cents) VALUES (?,?,?,?,?)',(tid,w,p,delta,cost))
@app.post('/api/stock')
@auth('admin')
def stock():
 d=request.get_json() or {};kind=required(d.get('kind'),'Movement type')
 if kind not in ('receive','transfer','adjust','disposal','return'):raise ValueError('Unsupported movement')
 w=integer(d.get('warehouse_id'),'Warehouse',1);p=integer(d.get('product_id'),'Product',1);qty=integer(d.get('qty'),'Quantity',1);ref=str(d.get('ref') or '')[:160]
 if kind=='adjust' and d.get('direction')=='remove':qty=-qty
 if kind=='disposal':qty=-qty
 if kind=='return' and d.get('condition')!='sellable':raise ValueError('Only sellable returns can increase inventory')
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  tid=transaction(c,kind,ref)
  if kind=='transfer':
   dest=integer(d.get('to_warehouse_id'),'Destination',1)
   if dest==w:raise ValueError('Source and destination must differ')
   move(c,tid,w,p,-qty);move(c,tid,dest,p,qty)
  else:move(c,tid,w,p,qty)
  audit(c,'stock.'+kind,f'transaction={tid} product={p} qty={qty}');c.commit()
 return jsonify(ok=True,transaction_id=tid)
@app.post('/api/sales')
@auth()
def sale():
 d=request.get_json() or {};items=d.get('items')
 if not isinstance(items,list) or not items or len(items)>100:raise ValueError('Sale needs 1–100 items')
 w=integer(d.get('warehouse_id'),'Warehouse',1);price_type=d.get('price_type','retail')
 if price_type not in ('retail','pickup','delivery'):raise ValueError('Invalid price type')
 ref=str(d.get('ref') or '')[:160];party=str(d.get('customer') or 'Walk-in')[:160]
 merged={}
 for item in items:
  p=integer(item.get('product_id'),'Product',1);q=integer(item.get('qty'),'Quantity',1);merged[p]=merged.get(p,0)+q
 with conn() as c:
  c.execute('BEGIN IMMEDIATE');details=[];total=0
  for p,q in merged.items():
   product=c.execute('SELECT * FROM products WHERE id=?',(p,)).fetchone()
   if not product:raise ValueError('Unknown product')
   price=product[price_type+'_cents'];total+=price*q;details.append((p,q,price,product['cost_cents']))
  tid=transaction(c,'sale',ref,party,total)
  for p,q,price,cost in details:
   move(c,tid,w,p,-q)
   c.execute('INSERT INTO sale_items(transaction_id,product_id,warehouse_id,qty,unit_price_cents,unit_cost_cents) VALUES (?,?,?,?,?,?)',(tid,p,w,q,price,cost))
  audit(c,'sale.create',f'transaction={tid} amount={total}');c.commit()
 return jsonify(ok=True,transaction_id=tid,total_cents=total)
@app.get('/api/reports')
@auth('admin')
def reports():
 with conn() as c:
  inventory=[dict(r) for r in c.execute('SELECT w.name warehouse,p.sku,p.name product,s.qty,p.cost_cents,s.qty*p.cost_cents stock_value_cents FROM stock s JOIN warehouses w ON w.id=s.warehouse_id JOIN products p ON p.id=s.product_id ORDER BY w.name,p.name')]
  sales=c.execute('SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE kind="sale"').fetchone()[0]
  cogs=c.execute('SELECT COALESCE(SUM(qty*unit_cost_cents),0) FROM sale_items').fetchone()[0]
 return jsonify(inventory=inventory,sales_cents=sales,cogs_cents=cogs,gross_profit_cents=sales-cogs,warning='Gross margin only; expenses, returns, taxes and collections are not included')
@app.get('/api/audit')
@auth('admin')
def audit_log():
 with conn() as c:rows=[dict(r) for r in c.execute('SELECT a.*,u.username actor FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 200')]
 return jsonify(rows=rows)


@app.post('/api/password')
@auth()
def change_password():
 d=request.get_json(silent=True) or {}
 old=str(d.get('current_password') or '');new=str(d.get('new_password') or '')
 if len(new)<12 or len(new)>128:raise ValueError('New password must be 12-128 characters')
 with conn() as c:
  u=c.execute('SELECT password_hash FROM users WHERE id=?',(session['uid'],)).fetchone()
  if not check_password_hash(u['password_hash'],old):return jsonify(error='Current password incorrect'),403
  c.execute('UPDATE users SET password_hash=?,auth_version=auth_version+1,must_change_password=0 WHERE id=?',(generate_password_hash(new),session['uid']))
  audit(c,'password.change','self')
 session.clear()
 return jsonify(ok=True,message='Password changed; sign in again')

@app.post('/api/users/<int:user_id>/reset-password')
@auth('admin')
def reset_password(user_id):
 d=request.get_json(silent=True) or {};new=str(d.get('password') or '')
 if len(new)<12 or len(new)>128:raise ValueError('Temporary password must be 12-128 characters')
 with conn() as c:
  if not c.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone():return jsonify(error='Unknown user'),404
  c.execute('UPDATE users SET password_hash=?,auth_version=auth_version+1,failed_logins=0,locked_until=0,must_change_password=1 WHERE id=?',(generate_password_hash(new),user_id))
  audit(c,'user.password_reset',str(user_id))
 return jsonify(ok=True)

@app.post('/api/users/<int:user_id>/status')
@auth('admin')
def user_status(user_id):
 d=request.get_json(silent=True) or {}
 if type(d.get('active')) is not bool:raise ValueError('active must be true or false')
 active=d['active']
 with conn() as c:
  c.execute('BEGIN IMMEDIATE')
  u=c.execute('SELECT id,role,active FROM users WHERE id=?',(user_id,)).fetchone()
  if not u:c.rollback();return jsonify(error='Unknown user'),404
  if not active and user_id==session['uid']:c.rollback();return jsonify(error='Cannot disable your own account'),400
  if not active and u['role']=='admin' and u['active'] and c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:
   c.rollback();return jsonify(error='Cannot disable last admin'),400
  c.execute('UPDATE users SET active=?,auth_version=auth_version+1 WHERE id=?',(int(active),user_id))
  audit(c,'user.status',f'{user_id}: active={active}');c.commit()
 return jsonify(ok=True)

from extensions import register_extensions
register_extensions(app, conn, auth, audit, now, cents, integer, required, apply_stock, transaction, move)

if __name__=='__main__':
 init_db();app.run(host='127.0.0.1',port=int(os.environ.get('PORT','8080')),debug=False)
