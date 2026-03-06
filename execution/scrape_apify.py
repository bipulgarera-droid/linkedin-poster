"""
Apify LinkedIn Scraper - Execution Script
==========================================
Scrapes LinkedIn posts using Apify actors (no cookies/login required).

Usage:
    python execution/scrape_apify.py --profile_url <url> --client_id <uuid> --competitor_id <uuid>
    python execution/scrape_apify.py --keyword <niche> --client_id <uuid>
    python execution/scrape_apify.py --test  (quick test with a known profile)
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load env
load_dotenv()

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Actor IDs (Apify API uses tilde ~ not slash / in actor names)
PROFILE_POSTS_ACTOR = "Wpp1BZ6yGWjySadk3"
KEYWORD_SEARCH_ACTOR = "curious_coder~linkedin-posts-search-scraper-no-cookies"

APIFY_BASE = "https://api.apify.com/v2"

# ---- Supabase helpers ----
def supabase_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def supabase_insert(table, data):
    """Insert a record into a Supabase table."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.post(url, headers=supabase_headers(), json=data)
    if resp.status_code not in (200, 201):
        print(f"  [ERROR] Supabase insert to {table} failed: {resp.status_code} {resp.text}")
        return None
    return resp.json()

def supabase_update(table, record_id, data):
    """Update a record in a Supabase table."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}"
    resp = requests.patch(url, headers=supabase_headers(), json=data)
    if resp.status_code not in (200, 204):
        print(f"  [ERROR] Supabase update on {table} failed: {resp.status_code} {resp.text}")
    return resp

# ---- Apify helpers ----
def run_apify_actor(actor_id, input_data, max_wait=300):
    """Run an Apify actor and wait for results."""
    print(f"  [APIFY] Starting actor: {actor_id}")
    
    url = f"{APIFY_BASE}/acts/{actor_id}/runs?token={APIFY_API_KEY}"
    resp = requests.post(url, json=input_data)
    
    if resp.status_code != 201:
        raise Exception(f"Failed to start actor: {resp.status_code} {resp.text}")
    
    run_data = resp.json()["data"]
    run_id = run_data["id"]
    print(f"  [APIFY] Run started: {run_id}")
    
    # Poll for completion
    elapsed = 0
    while elapsed < max_wait:
        status_url = f"{APIFY_BASE}/actor-runs/{run_id}?token={APIFY_API_KEY}"
        status_resp = requests.get(status_url).json()
        status = status_resp["data"]["status"]
        
        if status == "SUCCEEDED":
            print(f"  [APIFY] Run completed successfully in {elapsed}s")
            break
        elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise Exception(f"Actor run {status}: {status_resp['data'].get('statusMessage', '')}")
        
        time.sleep(5)
        elapsed += 5
    
    if elapsed >= max_wait:
        raise Exception(f"Actor run timed out after {max_wait}s")
    
    # Get results
    dataset_id = status_resp["data"]["defaultDatasetId"]
    items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={APIFY_API_KEY}"
    items_resp = requests.get(items_url)
    return items_resp.json()

def calculate_engagement(post):
    """Calculate engagement score from post metrics.
    
    apimaestro~linkedin-profile-posts format:
    stats: { total_reactions, like, support, love, insight, celebrate, funny, comments, reposts }
    """
    stats = post.get("stats", {})
    if isinstance(stats, dict) and stats:
        likes = stats.get("like", 0) or stats.get("total_reactions", 0) or 0
        comments = stats.get("comments", 0) or 0
        shares = stats.get("reposts", 0) or 0
    else:
        # Fallback for other actor formats
        likes = post.get("numLikes", 0) or post.get("likes", 0) or 0
        comments = post.get("numComments", 0) or post.get("comments", 0) or 0
        shares = post.get("numShares", 0) or post.get("shares", 0) or 0
    return likes + (comments * 2) + (shares * 3)

def parse_post(raw_post, competitor_id, client_id):
    """Parse a raw Apify post result into our schema.
    
    apimaestro~linkedin-profile-posts output format:
    - text: post content
    - stats: { total_reactions, like, comments, reposts }
    - author: { first_name, last_name, headline, username, profile_url, profile_picture }
    - media: { type, url, thumbnail } or null
    - posted_at, urn, url, post_type
    """
    # Content
    content = (
        raw_post.get("text") or 
        raw_post.get("postContent") or 
        raw_post.get("content") or 
        ""
    )
    
    # Stats (nested dict or direct fields)
    stats = raw_post.get("stats", {}) or {}
    likes = raw_post.get("numLikes") or stats.get("like", 0) or stats.get("total_reactions", 0) or 0
    comments_count = raw_post.get("numComments") or stats.get("comments", 0) or 0
    shares_count = raw_post.get("numShares") or stats.get("reposts", 0) or 0
    
    # Author (nested dict)
    author = raw_post.get("author", {}) or raw_post.get("authorProfile", {}) or {}
    if isinstance(author, dict):
        author_name = author.get("firstName", author.get("first_name", ""))
        last_name = author.get("lastName", author.get("last_name", ""))
        if last_name: author_name += f" {last_name}"
        author_name = author_name.strip()
        author_url = author.get("url") or author.get("profileUrl") or author.get("profile_url", "")
    else:
        author_name = str(author)
        author_url = ""
    
    # Media and Type
    post_type = raw_post.get("type") or raw_post.get("post_type", "text")
    media_url = None
    
    images = raw_post.get("images", [])
    media = raw_post.get("media", {}) or {}
    article = raw_post.get("article", {}) or {}
    linkedin_video = raw_post.get("linkedinVideo", {}) or {}
    
    if images and isinstance(images, list):
        media_url = images[0].get("url") if isinstance(images[0], dict) else images[0]
    elif raw_post.get("resharedPost") and isinstance(raw_post.get("resharedPost"), dict):
        reshared = raw_post.get("resharedPost", {})
        if "linkedinVideo" in reshared:
            try:
                media_url = reshared["linkedinVideo"]["videoPlayMetadata"]["thumbnail"]["artifacts"][0]["fileIdentifyingUrlPathSegment"]
            except Exception:
                pass
    elif linkedin_video:
        try:
            media_url = linkedin_video["videoPlayMetadata"]["thumbnail"]["artifacts"][0]["fileIdentifyingUrlPathSegment"]
        except Exception:
            pass
    elif article and article.get("title"):
        content = content + f"\n\n[Article: {article.get('title')}]" if content else f"[Article: {article.get('title')}]"
    elif isinstance(media, dict) and media:
        media_url = media.get("url") or media.get("thumbnail")
        if not post_type or post_type == "text":
            post_type = media.get("type", "text")
    
    # Handle complex date objects from Apify
    post_date_raw = raw_post.get("postedAtISO") or raw_post.get("posted_at") or raw_post.get("postedAt") or raw_post.get("date")
    post_date_str = None
    if isinstance(post_date_raw, dict):
        post_date_str = post_date_raw.get("date") or post_date_raw.get("timestamp")
        if isinstance(post_date_str, (int, float)):
            # Convert ms timestamp to ISO
            post_date_str = datetime.utcfromtimestamp(post_date_str / 1000.0).isoformat()
    elif isinstance(post_date_raw, (int, float)):
        post_date_str = datetime.utcfromtimestamp(post_date_raw / 1000.0).isoformat()
    else:
        post_date_str = post_date_raw

    return {
        "competitor_id": competitor_id,
        "client_id": client_id,
        "linkedin_post_id": raw_post.get("urn") or raw_post.get("postId") or raw_post.get("id"),
        "author_name": author_name or None,
        "author_url": author_url or raw_post.get("url"),
        "content": content[:5000] if content else None,
        "media_url": media_url,
        "likes": likes,
        "comments": comments_count,
        "shares": shares_count,
        "post_type": post_type,
        "engagement_score": calculate_engagement(raw_post),
        "raw_data": raw_post,
        "post_date": post_date_str,
        "scraped_at": datetime.utcnow().isoformat()
    }

# ---- Main flows ----
def scrape_profile_posts(profile_url, client_id, competitor_id, max_items=20):
    """Scrape posts from a specific LinkedIn profile."""
    print(f"\n{'='*60}")
    print(f"Scraping profile: {profile_url}")
    print(f"{'='*60}")
    
    # Create scrape job record
    job = supabase_insert("scrape_jobs", {
        "client_id": client_id,
        "status": "running",
        "actor_id": PROFILE_POSTS_ACTOR,
        "started_at": datetime.utcnow().isoformat()
    })
    job_id = job[0]["id"] if job else None
    
    try:
        input_data = {
            "urls": [profile_url],
            "deepScrape": False,
            "maxItems": max_items,
            "limit": max_items,
            "maxPosts": max_items,
            "proxyPosition": "RESIDENTIAL"
        }
        
        results = run_apify_actor(PROFILE_POSTS_ACTOR, input_data)
        
        # Enforce exact limit even if Apify fetches more
        if isinstance(results, list):
            results = results[:max_items]
            
        print(f"  [RESULT] Got {len(results)} posts")
        
        # Parse and insert posts
        inserted = 0
        for raw_post in results:
            parsed = parse_post(raw_post, competitor_id, client_id)
            result = supabase_insert("posts", parsed)
            if result:
                inserted += 1
        
        print(f"  [DB] Inserted {inserted} posts into Supabase")
        
        # Update job
        if job_id:
            supabase_update("scrape_jobs", job_id, {
                "status": "completed",
                "posts_found": inserted,
                "completed_at": datetime.utcnow().isoformat()
            })
        
        return results
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        if job_id:
            supabase_update("scrape_jobs", job_id, {
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.utcnow().isoformat()
            })
        raise

def scrape_keyword_posts(keyword, client_id, max_items=20):
    """Search LinkedIn posts by keyword/niche."""
    print(f"\n{'='*60}")
    print(f"Searching keyword: {keyword}")
    print(f"{'='*60}")
    
    input_data = {
        "searchTerms": [keyword],
        "maxResults": max_items,
        "sortBy": "relevance"
    }
    
    results = run_apify_actor(KEYWORD_SEARCH_ACTOR, input_data)
    print(f"  [RESULT] Got {len(results)} posts for keyword '{keyword}'")
    
    return results

def test_scrape():
    """Quick test with a known public LinkedIn profile."""
    print("\n" + "="*60)
    print("TEST MODE: Scraping posts from a test profile")
    print("="*60)
    
    if not APIFY_API_KEY:
        print("[ERROR] APIFY_API_KEY not set in .env")
        sys.exit(1)
    
    # Test with a known public profile (Gary Vaynerchuk)
    test_url = "https://www.linkedin.com/in/garyvaynerchuk/"
    
    input_data = {
        "profileUrls": [test_url],
        "maxItems": 5  # Just 5 posts for testing
    }
    
    try:
        results = run_apify_actor(PROFILE_POSTS_ACTOR, input_data)
        print(f"\n  [SUCCESS] Got {len(results)} posts")
        
        # Print a summary of results
        for i, post in enumerate(results[:3]):
            content = post.get("text") or post.get("content") or "No content"
            stats = post.get("stats", {}) or {}
            author = post.get("author", {}) or {}
            author_name = f"{author.get('first_name', '')} {author.get('last_name', '')}".strip() if isinstance(author, dict) else str(author)
            likes = stats.get("like", 0) or stats.get("total_reactions", 0) or 0
            
            print(f"\n  --- Post {i+1} ---")
            print(f"  Author: {author_name}")
            print(f"  Content: {content[:150]}...")
            print(f"  Likes: {likes} | Comments: {stats.get('comments', 0)} | Reposts: {stats.get('reposts', 0)}")
            print(f"  Engagement Score: {calculate_engagement(post)}")
        
        # Save raw results to .tmp for inspection
        os.makedirs(".tmp", exist_ok=True)
        with open(".tmp/test_scrape_results.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  [SAVED] Raw results to .tmp/test_scrape_results.json")
        
        return results
        
    except Exception as e:
        print(f"\n  [FAILED] {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape LinkedIn posts via Apify")
    parser.add_argument("--profile_url", help="LinkedIn profile URL to scrape")
    parser.add_argument("--keyword", help="Keyword/niche to search")
    parser.add_argument("--client_id", help="Client UUID")
    parser.add_argument("--competitor_id", help="Competitor UUID")
    parser.add_argument("--max_items", type=int, default=20, help="Max posts to fetch")
    parser.add_argument("--test", action="store_true", help="Run a quick test scrape")
    
    args = parser.parse_args()
    
    if args.test:
        test_scrape()
    elif args.profile_url:
        if not args.client_id or not args.competitor_id:
            print("[ERROR] --client_id and --competitor_id required for profile scrape")
            sys.exit(1)
        scrape_profile_posts(args.profile_url, args.client_id, args.competitor_id, args.max_items)
    elif args.keyword:
        if not args.client_id:
            print("[ERROR] --client_id required for keyword search")
            sys.exit(1)
        scrape_keyword_posts(args.keyword, args.client_id, args.max_items)
    else:
        parser.print_help()
