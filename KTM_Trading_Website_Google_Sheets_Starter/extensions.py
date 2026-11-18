import sqlite3, os, json, tempfile
from flask import request, jsonify, session, Response
from werkzeug.security import generate_password_hash

def register_extensions(app,conn,auth,audit,now,cents,integer,required,apply_stock,transaction,move):
 def body():return request.get_json(silent=True) or {}
 @app.get('/api/finance')
 @auth('admin')
 def finance():
  with conn() as c:
   q=lambda sql:c.execute(sql).fetchone()[0]
   sales=q("SELECT COALESCE(SUM(amount_cents),0) FROM transactions WHERE kind='sale'")
   cogs=q('SELECT COALESCE(SUM(qty*unit_cost_cents),0) FROM sale_items')
   credits=q('SELECT COALESCE(SUM(credit_cents),0) FROM return_items')
   expenses=q('SELECT COALESCE(SUM(amount_cents),0) FROM expenses')
   payroll=q('SELECT COALESCE(SUM(gross_cents),0) FROM payroll')
   return jsonify(sales_cents=sales,returns_cents=credits,net_revenue_cents=sales-credits,cogs_cents=cogs,expenses_cents=expenses,payroll_cents=payroll,indicative_profit_cents=sales-credits-cogs-expenses-payroll,warning='Indicative management P&L only: returns COGS, taxes, inventory valuation, accruals and reconciliation require accounting review')
 @app.post('/api/quotations')
 @auth('admin')
 def quotation():
  d=body();p=integer(d.get('product_id'),'Product',1);supplier=required(d.get('supplier'),'Supplier');qty=integer(d.get('qty'),'Quantity',1);unit=cents(d.get('unit_price'),'Unit price');freight=cents(d.get('freight',0),'Freight')
  with conn() as c:
   c.execute('INSERT INTO quotations(product_id,supplier,qty,unit_cents,freight_cents,valid_until,created_at) VALUES (?,?,?,?,?,?,?)',(p,supplier,qty,unit,freight,str(d.get('valid_until') or ''),now()));audit(c,'quotation.create',supplier)
  return jsonify(ok=True)
 @app.get('/api/quotations')
 @auth('admin')
 def quotations():
  with conn() as c:rows=[dict(x) for x in c.execute('SELECT q.*,p.sku,(q.qty*q.unit_cents+q.freight_cents) landed_cents FROM quotations q JOIN products p ON p.id=q.product_id ORDER BY q.id DESC')]
  return jsonify(rows=rows)
 @app.post('/api/ledgers')
 @auth('admin')
 def ledger():
  d=body();kind=d.get('kind');
  if kind not in ('payable','receivable'):raise ValueError('Invalid ledger type')
  party=required(d.get('party'),'Party');ref=required(d.get('reference'),'Reference');amount=cents(d.get('amount'),'Amount')
  if amount==0:raise ValueError('Amount must be positive')
  with conn() as c:
   c.execute('INSERT INTO ledgers(kind,party,reference,amount_cents,due_date,created_at) VALUES (?,?,?,?,?,?)',(kind,party,ref,amount,str(d.get('due_date') or ''),now()));audit(c,'ledger.create',kind+' '+ref)
  return jsonify(ok=True)
 @app.get('/api/ledgers')
 @auth('admin')
 def ledgers():
  with conn() as c:rows=[dict(x) for x in c.execute('SELECT *,amount_cents-paid_cents balance_cents FROM ledgers ORDER BY id DESC')]
  return jsonify(rows=rows)
 @app.post('/api/ledgers/<int:lid>/payments')
 @auth('admin')
 def ledger_payment(lid):
  d=body();amount=cents(d.get('amount'),'Payment');method=required(d.get('method'),'Method')
  if amount<=0:raise ValueError('Payment must be positive')
  with conn() as c:
   c.execute('BEGIN IMMEDIATE')
   r=c.execute('UPDATE ledgers SET paid_cents=paid_cents+? WHERE id=? AND amount_cents-paid_cents>=?',(amount,lid,amount))
   if r.rowcount!=1:raise ValueError('Payment exceeds balance or ledger not found')
   c.execute('INSERT INTO ledger_payments(ledger_id,amount_cents,method,reference,actor_id,created_at) VALUES (?,?,?,?,?,?)',(lid,amount,method,str(d.get('reference') or '')[:160],session['uid'],now()));audit(c,'ledger.payment',str(lid));c.commit()
  return jsonify(ok=True)
 @app.post('/api/employees')
 @auth('admin')
 def employee():
  d=body();code=required(d.get('code'),'Employee ID');name=required(d.get('name'),'Name');rate=cents(d.get('rate',0),'Rate')
  with conn() as c:c.execute('INSERT INTO employees(code,name,position,rate_cents) VALUES (?,?,?,?)',(code,name,str(d.get('position') or '')[:160],rate));audit(c,'employee.create',code)
  return jsonify(ok=True)
 @app.get('/api/employees')
 @auth('admin')
 def employees():
  with conn() as c:rows=[dict(x) for x in c.execute('SELECT * FROM employees ORDER BY id DESC')]
  return jsonify(rows=rows)
 @app.post('/api/payroll')
 @auth('admin')
 def payroll():
  d=body();eid=integer(d.get('employee_id'),'Employee',1);gross=cents(d.get('gross'),'Gross');deductions=cents(d.get('deductions',0),'Deductions');start=required(d.get('period_start'),'Period start');end=required(d.get('period_end'),'Period end');status=d.get('status','pending')
  if status not in ('pending','paid') or deductions>gross or start>end:raise ValueError('Invalid payroll values')
  with conn() as c:c.execute('INSERT INTO payroll(employee_id,period_start,period_end,gross_cents,deductions_cents,status,created_at) VALUES (?,?,?,?,?,?,?)',(eid,start,end,gross,deductions,status,now()));audit(c,'payroll.create',str(eid))
  return jsonify(ok=True)
 @app.get('/api/payroll')
 @auth('admin')
 def payroll_list():
  with conn() as c:rows=[dict(x) for x in c.execute('SELECT y.*,e.name employee_name FROM payroll y JOIN employees e ON e.id=y.employee_id ORDER BY y.id DESC')]
  return jsonify(rows=rows)
 @app.post('/api/expenses')
 @auth('admin')
 def expense():
  d=body();category=required(d.get('category'),'Category');description=required(d.get('description'),'Description');amount=cents(d.get('amount'),'Amount');status=d.get('status','paid');day=required(d.get('date'),'Date')
  if status not in ('paid','unpaid') or amount<=0:raise ValueError('Invalid expense')
  with conn() as c:c.execute('INSERT INTO expenses(category,description,amount_cents,status,expense_date,actor_id,created_at) VALUES (?,?,?,?,?,?,?)',(category,description,amount,status,day,session['uid'],now()));audit(c,'expense.create',category)
  return jsonify(ok=True)
 @app.get('/api/expenses')
 @auth('admin')
 def expenses():
  with conn() as c:rows=[dict(x) for x in c.execute('SELECT * FROM expenses ORDER BY id DESC')]
  return jsonify(rows=rows)
 @app.post('/api/users')
 @auth('admin')
 def user():
  d=body();username=required(d.get('username'),'Username');password=str(d.get('password') or '');role=d.get('role')
  if role not in ('admin','employee'):raise ValueError('Invalid role')
  if len(password)<12 or len(password)>128:raise ValueError('Password must be 12-128 characters')
  with conn() as c:c.execute('INSERT INTO users(username,password_hash,role,must_change_password) VALUES (?,?,?,1)',(username,generate_password_hash(password),role));audit(c,'user.create',username)
  return jsonify(ok=True)
 @app.get('/api/users')
 @auth('admin')
 def users():
  with conn() as c:rows=[dict(x) for x in c.execute('SELECT id,username,role,active FROM users ORDER BY id')]
  return jsonify(rows=rows)
 @app.get('/api/backup')
 @auth('admin')
 def backup():
  import io
  from flask import send_file
  src=conn();buf=io.BytesIO()
  try:
   dst=sqlite3.connect(':memory:');src.backup(dst)
   # SQLite serialize is supported in Python 3.11+
   buf.write(dst.serialize());dst.close()
  finally:src.close()
  buf.seek(0)
  return send_file(buf,as_attachment=True,download_name='ktm-backup.sqlite3',mimetype='application/vnd.sqlite3')
