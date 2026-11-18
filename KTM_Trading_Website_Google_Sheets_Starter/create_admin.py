import os,getpass
from werkzeug.security import generate_password_hash
from app import init_db,conn
init_db()
name=input('Admin username: ').strip()
if not name or len(name)>80:raise SystemExit('Invalid username')
pw=getpass.getpass('New admin password (12+ chars): ')
if len(pw)<12:raise SystemExit('Password must have 12+ characters')
with conn() as c:
 c.execute('INSERT INTO users(username,password_hash,role) VALUES (?,?,?)',(name,generate_password_hash(pw,method='scrypt'),'admin'))
print('Admin created.')
