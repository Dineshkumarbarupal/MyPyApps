from threading import RLock
_lock=RLock();_user=None
def set_user(user):
    global _user
    with _lock:_user=dict(user) if user else None
def get_user():
    with _lock:return dict(_user) if _user else None
def require_user():
    user=get_user()
    if not user:raise PermissionError("Please sign in to continue.")
    return user
