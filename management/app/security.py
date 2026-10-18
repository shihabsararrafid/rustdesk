import hashlib
import time
from uuid import uuid4

from argon2 import PasswordHasher

hasher = PasswordHasher()
# Equal-cost verification for unknown users, generated once per process.
dummy_hash = hasher.hash('not-an-account-password')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def create_user(db, username, password, role):
    if not 12 <= len(password) <= 256:
        raise ValueError('Password must contain 12 to 256 characters')
    uid = str(uuid4())
    db.execute('INSERT INTO users VALUES (?,?,?,?,0,?)',
               (uid, username, hasher.hash(password), role, time.time()))
    return uid
