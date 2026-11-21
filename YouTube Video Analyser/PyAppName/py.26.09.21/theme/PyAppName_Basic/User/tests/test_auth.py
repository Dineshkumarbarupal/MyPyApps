from auth_service import _hash,_verify
def test_secret_hashing():
    s,h=_hash("correct horse battery staple");assert _verify("correct horse battery staple",s,h);assert not _verify("wrong",s,h)
def test_unique_salts():
    a=_hash("same secret");b=_hash("same secret");assert a[0]!=b[0] and a[1]!=b[1]
