"""
LinkedInOS API Server
======================
Serves the dashboard UI AND exposes API endpoints so the entire
pipeline (scrape → generate → approve) runs from the browser.

Usage:
    python execution/api_server.py            # starts on port 5003
    python execution/api_server.py --port 8080
"""

import os
import sys
import json
import threading
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from dotenv import load_dotenv

# Ensure we can import sibling modules
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

# Import execution functions
from scrape_apify import (
    run_apify_actor, calculate_engagement, parse_post,
    PROFILE_POSTS_ACTOR, KEYWORD_SEARCH_ACTOR,
    supabase_insert, supabase_update, supabase_headers,
    SUPABASE_URL, SUPABASE_ANON_KEY, APIFY_API_KEY
)
from generate_content import (
    rewrite_with_gemini, generate_image_gemini,
    supabase_get, GEMINI_API_KEY
)
from discover_competitors import (
    discover_competitors_full, analyze_voice,
    generate_design_templates, generate_google_queries
)

import requests


class DashboardHandler(SimpleHTTPRequestHandler):
    """Handles both static files and API endpoints."""

    # Resolve at class level so it's always correct
    PUBLIC_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'public'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.PUBLIC_DIR, **kwargs)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/api/scrape':
            self._handle_scrape()
        elif path == '/api/generate':
            self._handle_generate()
        elif path == '/api/scrape-and-generate':
            self._handle_scrape_and_generate()
        elif path == '/api/analyze-voice':
            self._handle_analyze_voice()
        elif path == '/api/discover-competitors':
            self._handle_discover_competitors()
        elif path == '/api/generate-templates':
            self._handle_generate_templates()
        elif path == '/api/refresh-caption':
            self._handle_refresh_caption()
        elif path == '/api/refresh-image':
            self._handle_refresh_image()
        elif path == '/api/migrate':
            self._handle_migrate()
        else:
            self._json_response(404, {"error": "Not found"})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/health':
            self._json_response(200, {
                "status": "ok",
                "apify_key": bool(APIFY_API_KEY),
                "gemini_key": bool(GEMINI_API_KEY),
                "supabase_url": bool(SUPABASE_URL)
            })
        elif path.startswith('/api/'):
            self._json_response(404, {"error": "Not found"})
        else:
            # Serve static files
            super().do_GET()

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        return json.loads(body) if body else {}

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    # ---- API: Scrape ----
    def _handle_scrape(self):
        try:
            body = self._read_body()
            profile_url = body.get('profile_url')
            keyword = body.get('keyword')
            client_id = body.get('client_id')
            competitor_id = body.get('competitor_id')
            max_items = body.get('max_items', 20)

            if not profile_url and not keyword:
                self._json_response(400, {"error": "profile_url or keyword required"})
                return

            if not APIFY_API_KEY:
                self._json_response(500, {"error": "APIFY_API_KEY not configured"})
                return

            # Create scrape job record
            job = supabase_insert("scrape_jobs", {
                "client_id": client_id,
                "status": "running",
                "actor_id": PROFILE_POSTS_ACTOR if profile_url else KEYWORD_SEARCH_ACTOR,
                "started_at": datetime.utcnow().isoformat()
            })
            job_id = job[0]["id"] if job else None

            if profile_url:
                input_data = {
                    "urls": [profile_url],
                    "deepScrape": False,
                    "maxItems": max_items,
                    "limit": max_items,
                    "maxPosts": max_items,
                    "proxyPosition": "RESIDENTIAL"
                }
                results = run_apify_actor(PROFILE_POSTS_ACTOR, input_data)
            else:
                input_data = {"searchTerms": [keyword], "maxResults": max_items, "sortBy": "relevance"}
                results = run_apify_actor(KEYWORD_SEARCH_ACTOR, input_data)

            if isinstance(results, list):
                results = results[:max_items]

            # Parse and insert posts
            inserted = 0
            for raw_post in results:
                parsed = parse_post(raw_post, competitor_id, client_id)
                result = supabase_insert("posts", parsed)
                if result:
                    inserted += 1

            # Update job
            if job_id:
                supabase_update("scrape_jobs", job_id, {
                    "status": "completed",
                    "posts_found": inserted,
                    "completed_at": datetime.utcnow().isoformat()
                })

            self._json_response(200, {
                "success": True,
                "posts_scraped": len(results),
                "posts_inserted": inserted,
                "job_id": job_id
            })

        except Exception as e:
            print(f"[API ERROR] Scrape: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Generate Draft ----
    def _handle_generate(self):
        try:
            body = self._read_body()
            post_id = body.get('post_id')
            client_id = body.get('client_id')

            if not post_id or not client_id:
                self._json_response(400, {"error": "post_id and client_id required"})
                return

            # Fetch source post
            posts = supabase_get("posts", f"id=eq.{post_id}")
            if not posts:
                self._json_response(404, {"error": "Post not found"})
                return
            post = posts[0]

            # Fetch client voice (use voice_summary if available)
            clients = supabase_get("clients", f"id=eq.{client_id}")
            client = clients[0] if clients else {}
            voice_summary = client.get("voice_summary") or {}
            voice = voice_summary.get("rewrite_instructions", "") or client.get("voice_description", "")

            # Get design template if set
            template_id = body.get('template_id') or client.get('design_template_id')
            template_prompt = ""
            reference_imgUrl = None
            if template_id:
                templates = supabase_get("design_templates", f"id=eq.{template_id}")
                if templates:
                    template_prompt = templates[0].get("style_prompt", "")
                    reference_imgUrl = templates[0].get("reference_image_url")

            # Rewrite caption with Gemini
            new_caption = rewrite_with_gemini(post.get("content", ""), voice)

            # Generate image with Gemini
            image_url = generate_image_gemini((post.get("content") or "")[:200], style_prompt=template_prompt, reference_image_url=reference_imgUrl)

            # Create draft in Supabase
            draft = supabase_insert("drafts", {
                "client_id": client_id,
                "source_post_id": post_id,
                "caption": new_caption,
                "image_url": image_url,
                "status": "pending"
            })

            draft_id = draft[0]["id"] if draft else None

            self._json_response(200, {
                "success": True,
                "draft_id": draft_id,
                "caption_length": len(new_caption),
                "has_image": bool(image_url)
            })

        except Exception as e:
            print(f"[API ERROR] Generate: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Scrape + Generate in one shot ----
    def _handle_scrape_and_generate(self):
        try:
            body = self._read_body()
            profile_url = body.get('profile_url')
            client_id = body.get('client_id')
            competitor_id = body.get('competitor_id')
            max_items = body.get('max_items', 10)
            top_n = body.get('top_n', 3)

            if not profile_url or not client_id:
                self._json_response(400, {"error": "profile_url and client_id required"})
                return

            # Step 1: Scrape
            input_data = {
                "urls": [profile_url],
                "deepScrape": False,
                "maxItems": max_items,
                "limit": max_items,
                "maxPosts": max_items,
                "proxyPosition": "RESIDENTIAL"
            }
            results = run_apify_actor(PROFILE_POSTS_ACTOR, input_data)
            
            if isinstance(results, list):
                results = results[:max_items]

            # Step 2: Insert posts
            inserted_posts = []
            for raw_post in results:
                parsed = parse_post(raw_post, competitor_id, client_id)
                result = supabase_insert("posts", parsed)
                if result:
                    inserted_posts.append(result[0])

            # Step 3: Pick top N by engagement, generate drafts
            top_posts = sorted(inserted_posts, key=lambda p: p.get("engagement_score", 0), reverse=True)[:top_n]

            clients = supabase_get("clients", f"id=eq.{client_id}")
            voice = clients[0].get("voice_description", "") if clients else ""

            # Get design template if set
            template_id = clients[0].get('design_template_id') if clients else None
            template_prompt = ""
            reference_imgUrl = None
            if template_id:
                templates = supabase_get("design_templates", f"id=eq.{template_id}")
                if templates:
                    template_prompt = templates[0].get("style_prompt", "")
                    reference_imgUrl = templates[0].get("reference_image_url")

            drafts_created = 0
            for post in top_posts:
                caption = rewrite_with_gemini(post.get("content", ""), voice)
                image_url = generate_image_gemini((post.get("content") or "")[:200], style_prompt=template_prompt, reference_image_url=reference_imgUrl)
                draft = supabase_insert("drafts", {
                    "client_id": client_id,
                    "source_post_id": post["id"],
                    "caption": caption,
                    "image_url": image_url,
                    "status": "pending"
                })
                if draft:
                    drafts_created += 1

            self._json_response(200, {
                "success": True,
                "posts_scraped": len(results),
                "posts_inserted": len(inserted_posts),
                "drafts_created": drafts_created
            })

        except Exception as e:
            print(f"[API ERROR] Scrape+Generate: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Analyze Voice ----
    def _handle_analyze_voice(self):
        try:
            body = self._read_body()
            client_id = body.get('client_id')
            sample_posts = body.get('sample_posts', [])

            if not sample_posts or len(sample_posts) < 2:
                self._json_response(400, {"error": "At least 2 sample posts required"})
                return

            voice_summary = analyze_voice(sample_posts[:5])

            # Update client with voice_summary and sample_posts
            if client_id:
                import requests as req
                req.patch(
                    f"{SUPABASE_URL}/rest/v1/clients?id=eq.{client_id}",
                    headers=supabase_headers(),
                    json={"voice_summary": voice_summary, "sample_posts": sample_posts[:5]}
                )

            self._json_response(200, {
                "success": True,
                "voice_summary": voice_summary
            })
        except Exception as e:
            print(f"[API ERROR] Analyze Voice: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Discover Competitors ----
    def _handle_discover_competitors(self):
        try:
            body = self._read_body()
            niche = body.get('niche')
            sample_posts = body.get('sample_posts', [])
            limit = body.get('limit', 10)

            if not niche:
                self._json_response(400, {"error": "niche required"})
                return

            candidates = discover_competitors_full(niche, sample_posts, limit)

            self._json_response(200, {
                "success": True,
                "candidates": candidates,
                "count": len(candidates)
            })
        except Exception as e:
            print(f"[API ERROR] Discover: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Generate Templates ----
    def _handle_generate_templates(self):
        try:
            body = self._read_body()
            niche = body.get('niche')
            client_id = body.get('client_id')

            if not niche:
                self._json_response(400, {"error": "niche required"})
                return

            templates = generate_design_templates(niche, client_id=client_id)

            self._json_response(200, {
                "success": True,
                "templates": templates
            })
        except Exception as e:
            print(f"[API ERROR] Templates: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Refresh Caption ----
    def _handle_refresh_caption(self):
        try:
            body = self._read_body()
            draft_id = body.get('draft_id')
            if not draft_id:
                self._json_response(400, {"error": "draft_id required"})
                return

            drafts = supabase_get("drafts", f"id=eq.{draft_id}")
            if not drafts:
                self._json_response(404, {"error": "Draft not found"})
                return
            draft = drafts[0]

            # Get source post
            posts = supabase_get("posts", f"id=eq.{draft['source_post_id']}")
            post_content = posts[0].get("content", "") if posts else ""

            # Get client voice
            clients = supabase_get("clients", f"id=eq.{draft['client_id']}")
            client = clients[0] if clients else {}
            voice_summary = client.get("voice_summary") or {}
            voice = voice_summary.get("rewrite_instructions", "") or client.get("voice_description", "")

            # Generate new caption
            new_caption = rewrite_with_gemini(post_content, voice)

            # Update draft
            import requests as req
            req.patch(
                f"{SUPABASE_URL}/rest/v1/drafts?id=eq.{draft_id}",
                headers=supabase_headers(),
                json={"caption": new_caption}
            )

            self._json_response(200, {"success": True, "caption": new_caption})
        except Exception as e:
            print(f"[API ERROR] Refresh Caption: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Refresh Image ----
    def _handle_refresh_image(self):
        try:
            body = self._read_body()
            draft_id = body.get('draft_id')
            template_id = body.get('template_id')
            if not draft_id:
                self._json_response(400, {"error": "draft_id required"})
                return

            drafts = supabase_get("drafts", f"id=eq.{draft_id}")
            if not drafts:
                self._json_response(404, {"error": "Draft not found"})
                return
            draft = drafts[0]

            # Get template prompt if provided
            extra_prompt = ""
            reference_imgUrl = None
            if template_id:
                templates = supabase_get("design_templates", f"id=eq.{template_id}")
                if templates:
                    extra_prompt = templates[0].get("style_prompt", "")
                    reference_imgUrl = templates[0].get("reference_image_url")

            # Get source post for context
            posts = supabase_get("posts", f"id=eq.{draft['source_post_id']}")
            post_hint = (posts[0].get("content") or "")[:200] if posts else ""

            # Generate new image
            image_url = generate_image_gemini(post_hint, extra_prompt, reference_image_url=reference_imgUrl)

            # Update draft
            if image_url:
                import requests as req
                req.patch(
                    f"{SUPABASE_URL}/rest/v1/drafts?id=eq.{draft_id}",
                    headers=supabase_headers(),
                    json={"image_url": image_url}
                )

            self._json_response(200, {"success": True, "image_url": image_url})
        except Exception as e:
            print(f"[API ERROR] Refresh Image: {e}")
            self._json_response(500, {"error": str(e)})

    # ---- API: Run DB Migration ----
    def _handle_migrate(self):
        """Apply schema changes via Supabase REST."""
        try:
            # We use RPC or direct REST calls
            # Add columns to clients if missing
            import requests as req
            headers = supabase_headers()
            
            # Test if sample_posts column exists by doing a select
            resp = req.get(
                f"{SUPABASE_URL}/rest/v1/clients?select=sample_posts&limit=1",
                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}
            )
            
            if resp.status_code == 200:
                self._json_response(200, {"success": True, "message": "Schema already up to date"})
            else:
                self._json_response(200, {
                    "success": False,
                    "message": "Schema migration needed — run via Supabase Dashboard SQL editor",
                    "sql": "ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS sample_posts text[] DEFAULT '{}'; ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS voice_summary jsonb DEFAULT NULL;"
                })
        except Exception as e:
            self._json_response(500, {"error": str(e)})

    def log_message(self, format, *args):
        # Log everything for debugging
        try:
            msg = format % args
            sys.stderr.write(f"[SERVER] {self.client_address[0]} - {msg}\n")
        except Exception:
            pass


def run_server(port=5003):
    # Railway passes the PORT env var dynamically
    env_port = os.getenv("PORT")
    if env_port:
        port = int(env_port)
        
    print(f"[DEBUG] Serving files from: {DashboardHandler.PUBLIC_DIR}")
    print(f"[DEBUG] Directory exists: {os.path.isdir(DashboardHandler.PUBLIC_DIR)}")
    if os.path.isdir(DashboardHandler.PUBLIC_DIR):
        print(f"[DEBUG] Files: {os.listdir(DashboardHandler.PUBLIC_DIR)}")
    server = HTTPServer(('0.0.0.0', port), DashboardHandler)
    print(f"""
╔══════════════════════════════════════════════╗
║          LinkedInOS Dashboard Server         ║
╠══════════════════════════════════════════════╣
║  Dashboard:  http://0.0.0.0:{port}             ║
║  API:        http://0.0.0.0:{port}/api/health   ║
║                                              ║
║  Keys loaded:                                ║
║    Apify:    {'✅' if APIFY_API_KEY else '❌'}                                ║
║    Gemini:   {'✅' if GEMINI_API_KEY else '❌'}                                ║
║    Supabase: {'✅' if SUPABASE_URL else '❌'}                                ║
╚══════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedInOS Dashboard + API Server")
    parser.add_argument("--port", type=int, default=5003, help="Port to run on")
    args = parser.parse_args()
    run_server(args.port)
