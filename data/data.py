import os
import datetime
from typing import Dict, Any, List
from supabase import create_client, Client

# ────────────────────────────────
# Setup Supabase client
# ────────────────────────────────

SUPABASE_URL = os.getenv("PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials not set in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ────────────────────────────────
# In-memory cache (optional)
# ────────────────────────────────
gifts: Dict[str, int] = {}
history: Dict[str, List[Dict[str, Any]]] = {}


# ────────────────────────────────
# Database Operations
# ────────────────────────────────

def load_data():
    """Load all users and history from Supabase."""
    global gifts, history
    print("[data] Loading data from Supabase...")

    users_resp = supabase.table("users").select("*").execute()
    hist_resp = supabase.table("gift_history").select("*").execute()

    if users_resp.data:
        gifts = {str(u["user_id"]): int(u["total"]) for u in users_resp.data}
    else:
        gifts = {}

    history.clear()
    if hist_resp.data:
        for e in hist_resp.data:
            uid = str(e["user_id"])
            entry = {
                "amount": e["amount"],
                "drop": e.get("drop_name", ""),
                "created_at": e.get("created_at", "")
            }
            history.setdefault(uid, []).append(entry)

    print(f"[data] Loaded {len(gifts)} users and {len(hist_resp.data)} history entries.")


def save_data():
    """Push current in-memory data to Supabase (sync back)."""
    print("[data] Saving all users to Supabase...")

    for uid, total in gifts.items():
        supabase.table("users").upsert({
            "user_id": uid,
            "total": total,
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).execute()

    print("[data] Users upserted successfully.")


def record_gift(user_id: int, amount: int, drop_name: str = None) -> int:
    """Record a gift for a user and persist immediately."""
    uid = str(user_id)
    gifts[uid] = gifts.get(uid, 0) + int(amount)

    # Insert into gift_history
    supabase.table("gift_history").insert({
        "user_id": uid,
        "amount": amount,
        "drop_name": drop_name or "",
        "created_at": datetime.datetime.utcnow().isoformat()
    }).execute()

    # Update users table
    supabase.table("users").upsert({
        "user_id": uid,
        "total": gifts[uid],
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).execute()

    # Update in-memory cache
    entry = {
        "amount": int(amount),
        "drop": drop_name or "",
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    history.setdefault(uid, []).append(entry)

    print(f"[data] record_gift: uid={uid} amount={amount} new_total={gifts[uid]}")
    return gifts[uid]


def get_user_total(user_id: int) -> int:
    uid = str(user_id)
    if uid in gifts:
        return gifts[uid]
    resp = supabase.table("users").select("total").eq("user_id", uid).execute()
    if resp.data:
        gifts[uid] = int(resp.data[0]["total"])
        return gifts[uid]
    return 0


def get_leaderboard(limit: int = 10) -> List[tuple]:
    resp = supabase.table("users").select("user_id, total").order("total", desc=True).limit(limit).execute()
    if not resp.data:
        return []
    return [(int(row["user_id"]), row["total"]) for row in resp.data]


def get_user_history(user_id: int, limit: int = None) -> List[Dict[str, Any]]:
    uid = str(user_id)
    query = supabase.table("gift_history").select("*").eq("user_id", uid).order("created_at", desc=True)
    if limit:
        query = query.limit(limit)
    resp = query.execute()
    return resp.data or []


def reset():
    """Dangerous helper: clear all data in Supabase tables."""
    supabase.table("gift_history").delete().neq("id", 0).execute()
    supabase.table("users").delete().neq("user_id", "").execute()
    gifts.clear()
    history.clear()
    print("[data] Reset all Supabase data.")


# Load once on import
load_data()
