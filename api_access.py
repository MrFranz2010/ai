"""Chiavi e limiti per l'API HTTP pubblica di NOKK.

Le chiavi vengono mostrate una sola volta, al momento della creazione: qui se ne
conserva solo l'impronta SHA-256 e un suggerimento di quattro caratteri, così un
backup della configurazione non contiene chiavi utilizzabili.
"""

import hashlib
import hmac
import re
import secrets
import threading
import time

API_KEY_PREFIX = "nokk_"
API_KEY_PATTERN = re.compile(r"^nokk_[A-Za-z0-9_-]{32}$")
API_KEY_NAME_PATTERN = re.compile(r"^[\w .\-]{1,40}$", re.UNICODE)
API_KEY_ID_PATTERN = re.compile(r"^[a-f0-9]{16}$")
MAX_API_KEYS = 5

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 60


def default_api_config():
    return {"enabled": False, "keys": []}


def generate_api_key():
    return API_KEY_PREFIX + secrets.token_urlsafe(24)


def hash_api_key(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_hint(key):
    return key[-4:]


def make_api_key_record(name):
    """Create the stored record and the one-time secret for a new key."""
    clean_name = (name or "").strip() or "Chiave API"
    if not API_KEY_NAME_PATTERN.fullmatch(clean_name):
        raise ValueError("Il nome della chiave non è valido.")
    secret = generate_api_key()
    record = {
        "id": secrets.token_hex(8),
        "name": clean_name,
        "hash": hash_api_key(secret),
        "hint": key_hint(secret),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return record, secret


def validate_api_config(saved):
    if saved is None:
        return default_api_config()
    if not isinstance(saved, dict):
        raise ValueError("Configurazione API non valida.")
    enabled = saved.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("Stato dell'API non valido.")
    keys = saved.get("keys", [])
    if not isinstance(keys, list) or len(keys) > MAX_API_KEYS:
        raise ValueError("Elenco chiavi API non valido.")
    clean_keys = []
    seen = set()
    for key in keys:
        if not isinstance(key, dict):
            raise ValueError("Chiave API non valida.")
        key_id = key.get("id")
        name = key.get("name")
        digest = key.get("hash")
        hint = key.get("hint")
        created_at = key.get("created_at", "")
        if (
            not isinstance(key_id, str)
            or not API_KEY_ID_PATTERN.fullmatch(key_id)
            or key_id in seen
            or not isinstance(name, str)
            or not API_KEY_NAME_PATTERN.fullmatch(name)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or not isinstance(hint, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{4}", hint)
            or not isinstance(created_at, str)
            or len(created_at) > 32
        ):
            raise ValueError("Chiave API non valida.")
        seen.add(key_id)
        clean_keys.append({
            "id": key_id,
            "name": name,
            "hash": digest,
            "hint": hint,
            "created_at": created_at,
        })
    return {"enabled": enabled, "keys": clean_keys}


def find_api_key(api_config, presented):
    """Return the record whose key matches, comparing digests in constant time."""
    if not isinstance(presented, str) or not presented:
        return None
    digest = hash_api_key(presented)
    for record in api_config.get("keys", []):
        if hmac.compare_digest(digest, record["hash"]):
            return record
    return None


def public_api_keys(api_config):
    return {
        "enabled": bool(api_config.get("enabled")),
        "keys": [
            {
                "id": record["id"],
                "name": record["name"],
                "hint": record["hint"],
                "created_at": record["created_at"],
            }
            for record in api_config.get("keys", [])
        ],
    }


class RateLimiter:
    """Sliding-window limiter, one bucket per API key."""

    def __init__(self, limit=RATE_LIMIT_MAX_REQUESTS, window=RATE_LIMIT_WINDOW_SECONDS, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.lock = threading.Lock()
        self.hits = {}

    def allow(self, bucket):
        now = self.clock()
        with self.lock:
            stamps = [stamp for stamp in self.hits.get(bucket, []) if now - stamp < self.window]
            if len(stamps) >= self.limit:
                self.hits[bucket] = stamps
                return False
            stamps.append(now)
            self.hits[bucket] = stamps
            return True

    def reset(self, bucket=None):
        with self.lock:
            if bucket is None:
                self.hits.clear()
            else:
                self.hits.pop(bucket, None)
