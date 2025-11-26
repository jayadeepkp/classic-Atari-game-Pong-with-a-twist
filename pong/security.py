# =================================================================================================
# Contributing Authors:     Rudwika Manne, Harshini Ponnam, Jayadeep Kothapalli
# Email Addresses:          rma425@uky.edu, hpo245@uky.edu, jsko232@uky.edu
# Date:                     2025-11-26
# Purpose:                  Provide secure password handling (salted hashing), persistent
#                           user registration/login storage, and symmetric encryption utilities
#                           using Fernet for protecting all player-to-server communication.
#                           This module is imported by both pongClient and pongServer.
# Misc:                     CS 371 Fall 2025 Project — Authentication + Encryption Extension
# =================================================================================================

import json
import os
import hashlib
import base64
from cryptography.fernet import Fernet

USERS_FILE = "users.json"
KEY_FILE = "fernet.key"

# ==========================
# PASSWORD HASHING
# ==========================
# Author:      Harshini Ponnam
# Purpose:     Generate a secure salted hash for a new password using PBKDF2-HMAC (SHA-256).
# Pre:         password is a non-empty UTF-8 string provided during registration.
# Post:        Returns `salt || hash` as raw bytes, where:
#                  salt = 16 random bytes
#                  hash = PBKDF2-HMAC result with 200k iterations
def hash_password(password: str) -> bytes:
    """Return salt || hash for the given password."""
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200000,          # iterations
    )
    return salt + hashed

# ---------------------------------------------------------------------------------------------
# verify_password function
# ---------------------------------------------------------------------------------------------
# Author:      Harshini Ponnam
# Purpose:     Verify a user-entered password by recomputing PBKDF2 and comparing hashes.
# Pre:         stored = salt||hash bytes from users.json,
#              password = plaintext password user tries to log in with.
# Post:        Returns True if password is correct; otherwise False.
def verify_password(stored: bytes, password: str) -> bool:
    """Check password against stored salt||hash."""
    salt = stored[:16]
    stored_hash = stored[16:]
    check_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200000,
    )
    return stored_hash == check_hash


# ==========================
# USER REGISTRATION / LOGIN
# ==========================
# Author:      Rudwika Manne
# Purpose:     Load the persistent users database from disk.
# Pre:         USERS_FILE ("users.json") may or may not exist.
# Post:        Returns a dict: { username: base64(salt||hash) }.
def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# ---------------------------------------------------------------------------------------------
# register_user function
# ---------------------------------------------------------------------------------------------
# Author:      Rudwika Manne
# Purpose:     Register a new user by hashing their password and storing it persistently.
# Pre:         username/password are raw strings from client auth; username must not exist.
# Post:        Writes new entry to users.json and returns True if successful, False otherwise.
def register_user(username: str, password: str) -> bool:
    """
    Register new user. Returns True on success, False if username exists.
    """
    username = username.strip()
    if not username:
        return False
    users = load_users()
    if username in users:
        return False
    salted_hash = hash_password(password)
    users[username] = base64.b64encode(salted_hash).decode("ascii")
    save_users(users)
    return True


def authenticate(username: str, password: str) -> bool:
    """
    Authenticate existing user. Returns True on success.
    """
    username = username.strip()
    users = load_users()
    if username not in users:
        return False
    stored = base64.b64decode(users[username])
    return verify_password(stored, password)


# ==========================
# ENCRYPTION (Fernet)
# ==========================
# Author:      Jayadeep Kothapalli
# Purpose:     Load an existing Fernet key if present; otherwise generate and save a new one.
# Pre:         KEY_FILE ("fernet.key") may or may not exist on disk.
# Post:        Returns a bytes key suitable for Fernet symmetric encryption.
def _load_or_create_key() -> bytes:
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key
    with open(KEY_FILE, "rb") as f:
        return f.read()


_FERNET = Fernet(_load_or_create_key())


def encrypt_data(plaintext: str) -> bytes:
    """Encrypt a text line and return bytes token."""
    return _FERNET.encrypt(plaintext.encode("utf-8"))


def decrypt_data(token: str | bytes) -> str:
    """Decrypt token (str or bytes) and return plaintext string."""
    if isinstance(token, str):
        token = token.encode("utf-8")
    return _FERNET.decrypt(token).decode("utf-8")
