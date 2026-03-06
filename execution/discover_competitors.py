"""
Competitor Discovery Engine
============================
Discovers high-quality LinkedIn competitors via Google Search + Apify.

Pattern adapted from DIFFERENT AUDITS/execution/instagram_scraper.py

Flow:
  1. Gemini analyzes client niche + sample posts → generates search keywords
  2. Google Search "site:linkedin.com/in {keyword}" → extract profile URLs
  3. Present candidates to user for selection
  4. On "Analyse All" → scrape selected profiles' posts via Apify
  5. Quality validation + scoring
"""

import os
import re
import sys
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

APIFY_BASE = "https://api.apify.com/v2"
GOOGLE_SEARCH_ACTOR = "apify~google-search-scraper"


# ---- Helpers ----
def supabase_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def supabase_insert(table, data):
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(),
        json=data
    )
    if resp.status_code in (200, 201):
        return resp.json()
    print(f"  [DB ERROR] {table}: {resp.status_code} {resp.text[:200]}")
    return None


def run_apify_actor(actor_id, input_data, timeout_secs=300):
    """Run an Apify actor and return dataset items."""
    url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_API_KEY, "timeout": timeout_secs}
    resp = requests.post(url, params=params, json=input_data, timeout=timeout_secs + 30)
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 402:
        print(f"  [APIFY] Insufficient credits")
        return []
    else:
        print(f"  [APIFY ERROR] {resp.status_code}: {resp.text[:300]}")
        return []


# ---- Step 1: Gemini → Exact Google Queries ----
def generate_google_queries(niche):
    """Use Gemini to generate exactly 2 targeted Google search queries for this niche."""
    
    prompt = f"""You are an expert at Boolean search and Google dorks. A client's niche is "{niche}".
I need to find their top competitors on LinkedIn.

Generate exactly 2 Google search queries using the "site:linkedin.com/in" operator.
Query 1 should be highly specific to their exact niche.
Query 2 should be a slightly broader version (e.g. broader industry or role).

Return ONLY a JSON array of strings, nothing else. 
Example format:
[
  "site:linkedin.com/in \\"{niche}\\"",
  "site:linkedin.com/in \\"broader term\\""
]"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3}
    })
    
    fallback = [f"site:linkedin.com/in {niche}", f"site:linkedin.com/in {niche.split()[0]}"]
    
    if resp.status_code != 200:
        print(f"  [GEMINI ERROR] {resp.status_code}, using fallback queries")
        return fallback
    
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    
    try:
        queries = json.loads(text.strip())
        print(f"  [GEMINI] Generated {len(queries)} Google queries: {queries}")
        return queries[:2]  # Ensure max 2
    except json.JSONDecodeError:
        print(f"  [GEMINI] Failed to parse queries, using fallback")
        return fallback


# ---- Step 2: Google Search → LinkedIn Profile URLs ----
def google_search_linkedin_profiles(queries, max_per_query=15):
    """Search Google for LinkedIn profiles using targeted queries and extract/dedupe usernames."""
    
    all_profiles = []
    seen_usernames = set()
    
    for query in queries:
        print(f"  [GOOGLE] Searching: {query}")
        
        results = run_apify_actor(GOOGLE_SEARCH_ACTOR, {
            "queries": query,
            "maxPagesPerQuery": 1,
            "resultsPerPage": max_per_query
        }, timeout_secs=120)
        
        for page in results:
            for result in page.get("organicResults", []):
                url = result.get("url", "")
                title = result.get("title", "")
                description = result.get("description", "")
                
                # Extract LinkedIn username from URL
                match = re.search(r'linkedin\.com/in/([a-zA-Z0-9\-_]+)', url)
                if match:
                    username = match.group(1)
                    
                    # Skip common non-profile paths
                    skip = {"login", "signup", "help", "feed", "company", "jobs", "pulse", "learning"}
                    if username.lower() in skip:
                        continue
                    
                    if username not in seen_usernames:
                        seen_usernames.add(username)
                        all_profiles.append({
                            "linkedin_username": username,
                            "linkedin_url": f"https://www.linkedin.com/in/{username}",
                            "title_from_google": title,
                            "description_from_google": description,
                            "source_query": query
                        })
    
    print(f"  [GOOGLE] Found {len(all_profiles)} unique LinkedIn profiles")
    return all_profiles


# ---- Step 3: Quality Validation ----
def score_competitor_quality(profile):
    """Score a discovered profile based on available Google data.
    
    Returns a dict with:
      - quality: 'high', 'medium', 'low'
      - score: 0-100
      - reasons: list of signal descriptions
    """
    score = 50  # Base score
    reasons = []
    
    title = (profile.get("title_from_google") or "").lower()
    desc = (profile.get("description_from_google") or "").lower()
    
    # Positive signals from Google snippet
    authority_keywords = ["founder", "ceo", "cto", "cmo", "author", "speaker", 
                          "coach", "consultant", "expert", "head of", "director",
                          "vp ", "vice president", "creator", "influencer"]
    for kw in authority_keywords:
        if kw in title or kw in desc:
            score += 10
            reasons.append(f"Authority signal: '{kw}'")
            break  # Only count once
    
    # Follower hints in description
    follower_patterns = [
        (r'(\d+)k\+?\s*followers', 1000),
        (r'(\d+),(\d+)\s*followers', lambda m: int(m.group(1)) * 1000 + int(m.group(2))),
        (r'(\d+)\s*followers', 1),
    ]
    for pattern, multiplier in follower_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                if callable(multiplier):
                    followers_hint = multiplier(match)
                else:
                    followers_hint = int(match.group(1)) * multiplier
                if followers_hint > 10000:
                    score += 20
                    reasons.append(f"~{followers_hint:,} followers (Google snippet)")
                elif followers_hint > 5000:
                    score += 10
                    reasons.append(f"~{followers_hint:,} followers")
            except Exception:
                pass
            break
    
    # Connection count hints
    if "500+" in desc or "500+ connections" in desc:
        score += 5
        reasons.append("500+ connections")
    
    # Content signals — they post regularly
    content_keywords = ["posts about", "writes about", "shares insights", "thought leader"]
    for kw in content_keywords:
        if kw in desc:
            score += 10
            reasons.append(f"Content signal: '{kw}'")
            break
    
    # Verified or notable  
    if any(x in title for x in ["✅", "🔵", "verified"]):
        score += 15
        reasons.append("Verified badge")
    
    # Cap score
    score = min(100, max(0, score))
    
    # Quality tier
    if score >= 70:
        quality = "high"
    elif score >= 50:
        quality = "medium"
    else:
        quality = "low"
    
    return {
        "quality": quality,
        "score": score,
        "reasons": reasons
    }


# ---- Step 4: Voice Analysis ----
def analyze_voice(sample_posts):
    """Analyze a creator's writing voice from their sample posts using Gemini."""
    
    posts_text = "\n\n---POST---\n\n".join(sample_posts)
    
    prompt = f"""Analyze the writing voice and style of this LinkedIn creator based on their posts.

POSTS:
{posts_text}

Return a JSON object with these fields:
- "tone": one-word descriptor (e.g. "casual", "professional", "witty", "inspirational")
- "style_notes": 2-3 sentence description of their unique style
- "vocabulary_level": "simple" | "moderate" | "advanced"
- "emoji_usage": "none" | "minimal" | "moderate" | "heavy"
- "formatting": describe their use of line breaks, bullet points, hashtags
- "signature_phrases": list of 2-3 recurring phrases or patterns
- "rewrite_instructions": a single prompt paragraph that captures how to write in their voice

Return ONLY valid JSON, no markdown formatting."""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3}
    })
    
    if resp.status_code != 200:
        return {"error": f"Gemini API error: {resp.status_code}"}
    
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"rewrite_instructions": text, "error": "Could not parse as JSON"}


# ---- Step 5: Design Template Generation ----
def generate_design_templates(niche, voice_summary=None, client_id=None):
    """Generate 3 design template previews using Gemini image generation."""
    import base64
    
    styles = [
        {
            "name": "Bold Dark",
            "prompt": f"Professional dark navy LinkedIn post graphic with bold white typography, purple and teal gradient accents. Topic: {niche}. Clean modern layout with geometric shapes. Social media post format 1:1 ratio."
        },
        {
            "name": "Minimalist Light",
            "prompt": f"Clean minimalist white LinkedIn post graphic with subtle gray accents and one pop of blue color. Topic: {niche}. Elegant serif typography, lots of white space. Social media post format 1:1 ratio."
        },
        {
            "name": "Vibrant Gradient",
            "prompt": f"Eye-catching LinkedIn post graphic with vibrant orange-to-purple gradient background. Topic: {niche}. Bold sans-serif white text, modern glass-morphism card overlay. Social media post format 1:1 ratio."
        }
    ]
    
    templates = []
    
    for style in styles:
        print(f"  [TEMPLATE] Generating: {style['name']}...")
        
        # Generate image with Gemini
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(url, json={
            "contents": [{"parts": [{"text": style["prompt"]}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"]
            }
        })
        
        preview_url = None
        if resp.status_code == 200:
            data = resp.json()
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    img_b64 = part["inlineData"]["data"]
                    # Save preview to .tmp
                    os.makedirs(".tmp", exist_ok=True)
                    filename = f"template_{style['name'].lower().replace(' ', '_')}.png"
                    filepath = os.path.join(".tmp", filename)
                    with open(filepath, "wb") as f:
                        f.write(base64.b64decode(img_b64))
                    print(f"  [TEMPLATE] Saved: {filepath}")
                    
                    # Upload to Supabase Storage
                    storage_url = f"{SUPABASE_URL}/storage/v1/object/generated-images/templates/{filename}"
                    upload_resp = requests.post(storage_url, 
                        headers={
                            "apikey": SUPABASE_ANON_KEY,
                            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                            "Content-Type": "image/png",
                            "x-upsert": "true"
                        },
                        data=base64.b64decode(img_b64)
                    )
                    if upload_resp.status_code in (200, 201):
                        preview_url = f"{SUPABASE_URL}/storage/v1/object/public/generated-images/templates/{filename}"
                    break
        
        template_data = {
            "client_id": client_id,
            "name": style["name"],
            "style_prompt": style["prompt"],
            "preview_url": preview_url
        }
        
        # Insert into DB
        result = supabase_insert("design_templates", template_data)
        if result:
            template_data["id"] = result[0]["id"]
        
        templates.append(template_data)
    
    return templates


# ---- Main: Full Discovery Pipeline ----
def discover_competitors_full(niche, sample_posts=None, limit=10):
    """Full competitor discovery pipeline.
    
    Returns list of candidate profiles with quality scores.
    These are NOT scraped yet — user selects which ones to analyse.
    """
    print(f"\n{'='*60}")
    print(f"COMPETITOR DISCOVERY: {niche}")
    print(f"{'='*60}")
    
    # Step 1: Generate Google queries
    print("\n[1/3] Generating Google search queries...")
    queries = generate_google_queries(niche)
    
    # Step 2: Google search
    print("\n[2/3] Searching Google for LinkedIn profiles...")
    profiles = google_search_linkedin_profiles(queries)
    
    # Step 3: Quality scoring
    print("\n[3/3] Scoring competitor quality...")
    for profile in profiles:
        quality = score_competitor_quality(profile)
        profile.update(quality)
    
    # Sort by score descending
    profiles.sort(key=lambda p: p.get("score", 0), reverse=True)
    
    # Return top N
    top = profiles[:limit]
    
    # Summary
    high = sum(1 for p in top if p.get("quality") == "high")
    med = sum(1 for p in top if p.get("quality") == "medium")
    low = sum(1 for p in top if p.get("quality") == "low")
    print(f"\n[RESULT] {len(top)} candidates: {high} 🟢 high, {med} 🟡 medium, {low} 🔴 low")
    
    return top


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Discover LinkedIn competitors")
    parser.add_argument("--niche", required=True, help="Client niche/industry")
    parser.add_argument("--test", action="store_true", help="Test with keyword generation only (no Apify)")
    args = parser.parse_args()
    
    if args.test:
        queries = generate_google_queries(args.niche)
        print(f"\nQueries: {json.dumps(queries, indent=2)}")
    else:
        results = discover_competitors_full(args.niche)
        print(f"\nResults: {json.dumps(results, indent=2)}")
