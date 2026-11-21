from __future__ import annotations
import hashlib,hmac,secrets,uuid
from database import query_one,execute
ITERATIONS=310000
def _hash(value,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt,hashlib.pbkdf2_hmac("sha256",value.encode(),bytes.fromhex(salt),ITERATIONS).hex()
def _verify(value,salt,expected):
    return hmac.compare_digest(_hash(value,salt)[1],expected)
def register(name,email,password):
    name=" ".join((name or "").split());email=(email or "").strip().lower()
    if not 2<=len(name)<=60:raise ValueError("Name must contain 2 to 60 characters.")
    if len(email)>254 or "@" not in email or "." not in email.rsplit("@",1)[-1]:raise ValueError("Enter a valid email address.")
    if not 10<=len(password or "")<=128:raise ValueError("Password must contain 10 to 128 characters.")
    if query_one("SELECT id FROM users WHERE email=?",(email,)):raise ValueError("An account with this email already exists.")
    ps,ph=_hash(password);code=secrets.token_urlsafe(24);rs,rh=_hash(code);uid=str(uuid.uuid4())
    execute("INSERT INTO users(id,display_name,email,password_salt,password_hash,recovery_salt,recovery_hash) VALUES(?,?,?,?,?,?,?)",(uid,name,email,ps,ph,rs,rh))
    return {"id":uid,"display_name":name,"email":email},code
def login(email,password):
    row=query_one("SELECT * FROM users WHERE email=?",((email or "").strip().lower(),))
    if not row or not _verify(password or "",row["password_salt"],row["password_hash"]):raise ValueError("Email or password is incorrect.")
    return {"id":row["id"],"display_name":row["display_name"],"email":row["email"]}
def reset_password(email,code,new_password):
    if not 10<=len(new_password or "")<=128:raise ValueError("New password must contain 10 to 128 characters.")
    row=query_one("SELECT * FROM users WHERE email=?",((email or "").strip().lower(),))
    if not row or not _verify(code or "",row["recovery_salt"],row["recovery_hash"]):raise ValueError("Email or recovery code is incorrect.")
    salt,digest=_hash(new_password);execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?",(salt,digest,row["id"]))
