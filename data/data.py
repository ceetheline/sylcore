import os
import datetime
import threading
import requests
from typing import Dict, Any, List

# JSONStorage API endpoint
JSON_STORAGE_URL = os.getenv("JSON_STORAGE_URL")

# In-memory structures
gifts: Dict[str, int] = {}
history: Dict[str, List[Dict[str, Any]]] = {}

# Thread lock to prevent race conditions during saves
_save_lock = threading.Lock()

def _fetch_remote_data():
    """Fetch data from JSONStorage (remote persistence)."""
    if not JSON_STORAGE_URL:
        print("[data] JSON_STORAGE_URL not set. Data won't persist remotely.")
        return {"gifts": {}, "history": {}}
    try:
        resp = requests.get(JSON_STORAGE_URL, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"[data] Failed to fetch remote data: HTTP {resp.status_code}")
    except Exception as e:
        print(f"[data] Exception while fetching data: {e}")
    return {"gifts": {}, "history": {}}

def _push_remote_data(data):
    """Push full updated data to JSONStorage (thread-safe)."""
    if not JSON_STORAGE_URL:
        print("[data] JSON_STORAGE_URL not set. Skipping remote save.")
        return
    with _save_lock:
        try:
            resp = requests.put(
                JSON_STORAGE_URL,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            print(f"[data] Saved remotely: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[data] Failed to push data remotely: {e}")

def load_data():
    """Load JSON data from remote into memory."""
    global gifts, history
    data = _fetch_remote_data()
    gifts = {str(uid): int(v) for uid, v in data.get("gifts", {}).items()}
    history = {}
    for uid, entries in data.get("history", {}).items():
        history[str(uid)] = [
            {
                "amount": int(e.get("amount", 0)),
                "drop": e.get("drop", "")
            }
            for e in entries
        ]
    print(f"[data] Loaded {len(gifts)} users from JSONStorage")

def save_data():
    """Save in-memory data to JSONStorage."""
    formatted = {
        "gifts": gifts,
        "history": history
    }
    _push_remote_data(formatted)

def record_gift(user_id: int, amount: int, drop_name: str = None) -> int:
    """Record a gift and save to remote storage."""
    uid = str(user_id)
    gifts[uid] = gifts.get(uid, 0) + int(amount)
    entry = {
        "amount": int(amount),
        "drop": drop_name or ""
    }
    history.setdefault(uid, []).append(entry)
    print(f"[data] record_gift: uid={uid} amount={amount} new_total={gifts[uid]} entries={len(history.get(uid, []))}")
    save_data()
    return gifts[uid]

def get_user_total(user_id: int) -> int:
    return int(gifts.get(str(user_id), 0))

def get_leaderboard(limit: int = 10) -> List[tuple]:
    items = sorted(((int(uid), cnt) for uid, cnt in gifts.items()), key=lambda x: x[1], reverse=True)
    return items[:limit]

def get_user_history(user_id: int, limit: int = None) -> List[Dict[str, Any]]:
    uid = str(user_id)
    entries = history.get(uid, [])
    if limit:
        return entries[-limit:]
    return entries

def reset():
    """Dangerous helper: clear in-memory and reset remote."""
    global gifts, history
    gifts.clear()
    history.clear()
    save_data()
    print("[data] Reset all data")

# Load on import
load_data()
