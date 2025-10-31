import json
import os
import datetime
import tempfile
import threading
from typing import Dict, Any, List

# Store JSON in the same data directory as this module
DATA_DIR = os.path.join(os.getcwd(), "data")
DATA_FILE = os.path.join(DATA_DIR, "gifts_data.json")

# In-memory structures (match the example style)
gifts: Dict[str, int] = {}       # user_id (str) -> total gifts
history: Dict[str, List[Dict[str, Any]]] = {}  # user_id -> list of event dicts


def _ensure_parent():
    os.makedirs(DATA_DIR, exist_ok=True)


# Lock to serialize saves so two threads don't clobber temp files
_save_lock = threading.Lock()


def save_data():
    """Save directly to the JSON file (thread-safe)."""
    _ensure_parent()
    with _save_lock:
        try:
            formatted = {"gifts": gifts, "history": {}}

            # Build compact JSON lines for each user's history
            for uid, entries in history.items():
                formatted_entries = []
                for e in entries:
                    formatted_entries.append(
                        f'{{ "amount": {e["amount"]}, "drop": "{e["drop"]}" }}'
                    )
                formatted["history"][uid] = formatted_entries

            # Write manually to control formatting
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                f.write('{\n')
                f.write('    "gifts": ')
                json.dump(gifts, f, indent=4, ensure_ascii=False)
                f.write(',\n    "history": {\n')

                for i, (uid, entries) in enumerate(formatted["history"].items()):
                    comma = ',' if i < len(formatted["history"]) - 1 else ''
                    f.write(f'        "{uid}": [ ')
                    f.write(', '.join(entries))
                    f.write(f' ]{comma}\n')
                f.write('    }\n}')
                
            print(f"[data] Saved data directly to {DATA_FILE}")
        except Exception as ex:
            print(f"[data] Failed to save data: {ex}")



def load_data():
    """Load JSON into the in-memory structures. Safe to call on import."""
    global gifts, history
    if not os.path.exists(DATA_FILE):
        gifts = {}
        history = {}
        return

    # If file exists but is empty, treat as fresh (prevents JSONDecodeError on zero-byte files)
    try:
        if os.path.getsize(DATA_FILE) == 0:
            print(f"[data] {DATA_FILE} is empty; initializing fresh structures.")
            gifts = {}
            history = {}
            return
    except Exception:
        # ignore stat errors and continue to try reading
        pass

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as err:
            # Corrupted JSON: move file aside for inspection and start fresh
            try:
                corrupt_path = DATA_FILE + ".corrupt." + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
                os.replace(DATA_FILE, corrupt_path)
                print(f"[data] Corrupted data moved to {corrupt_path}; starting fresh.")
            except Exception:
                print(f"[data] Failed to move corrupted data file: {err}")
            gifts = {}
            history = {}
            return

    # normalize types
    gifts.clear()
    for uid, total in data.get("gifts", {}).items():
        gifts[str(uid)] = int(total)

    history.clear()
    for uid, entries in data.get("history", {}).items():
        history[str(uid)] = [
            {
                "amount": int(e.get("amount", 0)),
                "drop": e.get("drop", ""),
            }
            for e in entries
        ]


def record_gift(user_id: int, amount: int, drop_name: str = None) -> int:
    """Record a gift event and update the user's total in JSON-backed structures.

    Returns the new total for the user.
    """
    uid = str(user_id)
    gifts[uid] = gifts.get(uid, 0) + int(amount)
    entry = {
        f"amount": int(amount),
        "drop": drop_name or ""
    }
    history.setdefault(uid, []).append(entry)
    print(f"[data] record_gift: uid={uid} amount={amount} new_total={gifts[uid]} entries={len(history.get(uid,[]))}")
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
    """Dangerous helper for tests: remove the JSON file and clear memory."""
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
    gifts.clear()
    history.clear()


# load on import
load_data()
