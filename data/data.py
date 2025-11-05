import os
import datetime
from typing import Dict, Any, List
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL: str = os.getenv("PUBLIC_SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials not set in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

gifts: Dict[str, int] = {}
history: Dict[str, List[Dict[str, Any]]] = {}

def load_data():
    global gifts, history
    print("[data] Loading data from Supabase...")

    users_resp = supabase.table("users").select("*").execute()
    hist_resp = supabase.table("gift_history").select("*").execute()

    users = users_resp.data or []
    hist = hist_resp.data or []

    gifts = {str(u["user_id"]): int(u["total"]) for u in users}
    history.clear()

    for e in hist:
        uid = str(e["user_id"])
        entry = {
            "amount": e["amount"],
            "drop": e.get("drop_name", ""),
            "created_at": e.get("created_at", "")
        }
        history.setdefault(uid, []).append(entry)

    print(f"[data] Loaded {len(gifts)} users and {len(hist)} history entries.")


def save_data():
    print("[data] Saving all users to Supabase...")

    for uid, total in gifts.items():
        resp = supabase.table("users").upsert({
            "user_id": uid,
            "total": total,
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).execute()
        if resp.error is not None:
            print(f"Error upserting user {uid}: {resp.error}")

    print("[data] Users upserted successfully.")


def record_gift(user_id: int, amount: int, drop_name: str = None) -> int:
    uid = str(user_id)

    upsert_user_resp = supabase.table("users").upsert({
        "user_id": uid,
        "total": gifts.get(uid, 0),
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).execute()

    if upsert_user_resp.data and "error" in upsert_user_resp.data:
        print(f"Failed to upsert user {uid}: {upsert_user_resp.data['error']}")
        return None

    insert_resp = supabase.table("gift_history").insert({
        "user_id": uid,
        "amount": amount,
        "drop_name": drop_name or "",
        "created_at": datetime.datetime.utcnow().isoformat()
    }).execute()

    if insert_resp.data and "error" in insert_resp.data:
        print(f"Insert gift error: {insert_resp.data['error']}")
        return None

    resp = supabase.table("gift_history").select("amount").eq("user_id", uid).execute()
    total = sum(r["amount"] for r in resp.data) if resp.data else 0

    upsert_resp = supabase.table("users").update({
        "total": total,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("user_id", uid).execute()

    if upsert_resp.data and "error" in upsert_resp.data:
        print(f"Failed to update user total for {uid}: {upsert_resp.data['error']}")
        return None

    # Update caches
    gifts[uid] = total
    entry = {
        "amount": amount,
        "drop": drop_name or "",
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    history.setdefault(uid, []).append(entry)

    return total


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
    """Clear all data in Supabase tables safely using filters to satisfy API."""
    supabase.table("gift_history").delete().not_.is_("id", None).execute()
    supabase.table("users").delete().not_.is_("user_id", None).execute()
    gifts.clear()
    history.clear()
    print("[data] Reset all Supabase data.")


# Load once on import
load_data()
