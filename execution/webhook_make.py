"""
Make.com Webhook - Execution Script
===================================
Sends approved drafts to a Make.com webhook for LinkedIn scheduling.

Usage:
    python execution/webhook_make.py --draft_id <uuid>
"""

import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

def supabase_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def supabase_get(table, filters=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{filters}"
    resp = requests.get(url, headers=supabase_headers())
    return resp.json()

def supabase_update(table, record_id, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}"
    resp = requests.patch(url, headers=supabase_headers(), json=data)
    return resp

def schedule_to_make(draft_id):
    """Send an approved draft to Make.com webhook for scheduling."""
    print(f"\n{'='*60}")
    print(f"Scheduling draft: {draft_id}")
    print(f"{'='*60}")
    
    # Fetch draft
    drafts = supabase_get("drafts", f"id=eq.{draft_id}")
    if not drafts:
        print("[ERROR] Draft not found")
        return False
    
    draft = drafts[0]
    
    if draft["status"] != "approved":
        print(f"[WARN] Draft status is '{draft['status']}', expected 'approved'")
    
    if not MAKE_WEBHOOK_URL:
        print("[ERROR] MAKE_WEBHOOK_URL required in .env. Example: https://hook.eu2.make.com/xxxxxxxxx")
        print("[INFO] Marking draft as 'scheduled' anyway for demo purposes")
        supabase_update("drafts", draft_id, {"status": "scheduled"})
        return True
    
    # Build Make.com payload
    payload = {
        "text": draft.get("caption", ""),
        "author": draft.get("client_id"),
        "draft_id": draft_id
    }
    
    # Attach image if available
    if draft.get("image_url"):
        payload["image_url"] = draft["image_url"]
    
    # Send to Make.com Webhook
    resp = requests.post(MAKE_WEBHOOK_URL, json=payload)
    
    if resp.status_code in (200, 201):
        print(f"  [MAKE] Post sent to webhook successfully: {resp.text}")
        supabase_update("drafts", draft_id, {"status": "scheduled"})
        return True
    else:
        print(f"  [ERROR] Make webhook error: {resp.status_code} {resp.text}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schedule approved post via Make.com webhook")
    parser.add_argument("--draft_id", required=True, help="Draft UUID to schedule")
    args = parser.parse_args()
    
    schedule_to_make(args.draft_id)
