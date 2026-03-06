"""
AI Content Generator - Execution Script
========================================
Takes a scraped competitor post and generates a new draft 
using Gemini (caption rewrite + image generation via gemini-2.5-flash-image).

Usage:
    python execution/generate_content.py --post_id <uuid> --client_id <uuid>
    python execution/generate_content.py --test
"""

import os
import sys
import json
import base64
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Models
GEMINI_TEXT_MODEL = "gemini-2.0-flash"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

# ---- Supabase helpers ----
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

def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.post(url, headers=supabase_headers(), json=data)
    if resp.status_code not in (200, 201):
        print(f"  [ERROR] Supabase insert to {table} failed: {resp.status_code} {resp.text}")
        return None
    return resp.json()

# ---- Gemini Text Rewrite ----
def rewrite_with_gemini(original_content, voice_description):
    """Rewrite a LinkedIn post caption using Gemini."""
    if not GEMINI_API_KEY:
        print("  [WARN] GEMINI_API_KEY not set, returning placeholder")
        return f"[AI Draft] {original_content[:300]}"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""You are a LinkedIn content strategist. Rewrite the following LinkedIn post in a new voice.

ORIGINAL POST:
{original_content}

TARGET VOICE/TONE:
{voice_description or 'Professional, insightful, with a personal touch. Use short, punchy sentences.'}

INSTRUCTIONS:
- Keep the core message and insights
- Make it completely original (not a copy)
- Add relevant hashtags (3-5)
- Use line breaks for readability
- Include a hook in the first line
- End with a call-to-action or question
- Keep it under 1300 characters

OUTPUT ONLY THE REWRITTEN POST, nothing else."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 1000
        }
    }
    
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        raise Exception(f"Gemini API error: {resp.status_code} {resp.text}")
    
    result = resp.json()
    return result["candidates"][0]["content"]["parts"][0]["text"]

# ---- Gemini Image Generation (nano banana) ----
def generate_image_gemini(topic_description, style_prompt="", reference_image_url=None):
    """Generate a LinkedIn post graphic using Gemini gemini-2.5-flash-image.
    
    Args:
        topic_description: The topic/content to base the image on
        style_prompt: Optional extra style instructions (from design template)
        reference_image_url: Optional image URL to use as reference for style transfer/composition
    
    Returns the public URL of the uploaded image, or None if generation fails.
    """
    if not GEMINI_API_KEY:
        print("  [WARN] GEMINI_API_KEY not set, skipping image generation")
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    extra_style = f"\n\nADDITIONAL STYLE: {style_prompt}" if style_prompt else ""
    reference_instruction = f"\n\nCRITICAL INSTRUCTION: Mimic the visual style, color palette, and abstract composition of the provided reference image. Do not include any text." if reference_image_url else ""
    
    prompt = f"""Generate a professional, modern LinkedIn post graphic for the following topic:

{topic_description}

STYLE REQUIREMENTS:
- Clean, minimal design
- Dark/navy background with vibrant accent colors (purple, blue, teal)
- Professional and corporate feel
- Include relevant abstract or geometric shapes
- 1080x1080 square format (LinkedIn post)
- No stock-photo feel
- ABSOLUTELY NO TEXT ON THE IMAGE. Do not generate fake words, logos, watermarks, or text snippets ending in '...'. The image should be purely visual/abstract design graphic without words.{extra_style}{reference_instruction}
"""
    
    # Build payload parts
    parts = [{"text": prompt}]
    
    if reference_image_url:
        try:
            print(f"  [GEMINI-IMG] Fetching reference image from {reference_image_url}...")
            # Download reference image
            img_resp = requests.get(reference_image_url, timeout=10)
            if img_resp.status_code == 200:
                img_data = base64.b64encode(img_resp.content).decode('utf-8')
                mime_type = "image/jpeg" if "jpg" in reference_image_url.lower() or "jpeg" in reference_image_url.lower() else "image/png"
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": img_data
                    }
                })
                print(f"  [GEMINI-IMG] Added reference image to payload.")
            else:
                print(f"  [WARN] Failed to fetch reference image: {img_resp.status_code}")
        except Exception as e:
            print(f"  [WARN] Error processing reference image: {e}")
            
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"]
        }
    }
    
    try:
        print("  [GEMINI-IMG] Generating image with gemini-2.5-flash-image...")
        resp = requests.post(url, json=payload)
        
        if resp.status_code != 200:
            print(f"  [WARN] Gemini image API error: {resp.status_code} {resp.text[:200]}")
            return None
        
        result = resp.json()
        candidates = result.get("candidates", [])
        
        if not candidates:
            print("  [WARN] No candidates returned from Gemini image model")
            return None
        
        # Look for inline image data in the response parts
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                mime_type = part["inlineData"].get("mimeType", "image/png")
                image_data = part["inlineData"]["data"]
                
                # Save to .tmp/
                os.makedirs(".tmp", exist_ok=True)
                ext = "png" if "png" in mime_type else "jpg"
                filename = f".tmp/generated_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.{ext}"
                
                with open(filename, "wb") as f:
                    f.write(base64.b64decode(image_data))
                
                print(f"  [GEMINI-IMG] Image saved: {filename} ({len(image_data)} bytes base64)")
                
                # Upload to Supabase Storage
                image_url = upload_to_supabase_storage(filename, mime_type)
                return image_url
        
        print("  [WARN] No image data found in Gemini response")
        return None
        
    except Exception as e:
        print(f"  [WARN] Image generation failed: {e}")
        return None

def upload_to_supabase_storage(filepath, mime_type="image/png"):
    """Upload a file to the Supabase generated-images bucket."""
    try:
        filename = os.path.basename(filepath)
        upload_url = f"{SUPABASE_URL}/storage/v1/object/generated-images/{filename}"
        
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": mime_type
        }
        
        with open(filepath, "rb") as f:
            resp = requests.post(upload_url, headers=headers, data=f.read())
        
        if resp.status_code in (200, 201):
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/generated-images/{filename}"
            print(f"  [STORAGE] Uploaded to: {public_url}")
            return public_url
        else:
            print(f"  [WARN] Storage upload failed: {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [WARN] Storage upload error: {e}")
        return None

# ---- Main flow ----
def generate_draft(post_id, client_id):
    """Generate a draft from a scraped post."""
    print(f"\n{'='*60}")
    print(f"Generating draft from post: {post_id}")
    print(f"{'='*60}")
    
    # Fetch the source post
    posts = supabase_get("posts", f"id=eq.{post_id}")
    if not posts:
        print("[ERROR] Post not found")
        return None
    post = posts[0]
    
    # Fetch client voice
    clients = supabase_get("clients", f"id=eq.{client_id}")
    voice = clients[0].get("voice_description", "") if clients else ""
    
    # Rewrite caption
    print("  [GEMINI] Rewriting caption...")
    new_caption = rewrite_with_gemini(post["content"], voice)
    print(f"  [GEMINI] Generated {len(new_caption)} chars")
    
    # Generate image
    image_url = generate_image_gemini(post["content"][:200])
    
    # Create draft
    draft = supabase_insert("drafts", {
        "client_id": client_id,
        "source_post_id": post_id,
        "caption": new_caption,
        "image_url": image_url,
        "status": "pending"
    })
    
    if draft:
        print(f"  [DB] Draft created: {draft[0]['id']}")
    
    return draft

def test_generate():
    """Test Gemini rewriting + image generation with a sample post."""
    print("\n" + "="*60)
    print("TEST MODE: Testing Gemini caption rewriting + image generation")
    print("="*60)
    
    sample_post = """
🚀 The #1 mistake I see founders make?

They build what they think is cool instead of what customers actually need.

I've coached 200+ startups and the pattern is always the same:
- 6 months building in stealth
- Launch day: crickets
- Pivot or die

The fix? Talk to 50 customers BEFORE writing a single line of code.

Your product is not for you. It's for them.

#startups #entrepreneurship #product
"""
    
    voice = "Casual, witty Indian entrepreneur. Uses Hindi words occasionally. Loves cricket metaphors."
    
    # Test caption rewrite
    print("\n[1/2] Testing caption rewrite...")
    result = rewrite_with_gemini(sample_post.strip(), voice)
    print(f"\n--- REWRITTEN POST ---\n{result}\n")
    
    # Test image generation
    print("[2/2] Testing image generation...")
    image_url = generate_image_gemini("Startup mistakes founders make - talk to customers first")
    if image_url:
        print(f"  Image URL: {image_url}")
    else:
        print("  Image: skipped or failed (check GEMINI_API_KEY)")
    
    # Save to .tmp
    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/test_generated_draft.txt", "w") as f:
        f.write(result)
    print("\n[SAVED] .tmp/test_generated_draft.txt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate AI content drafts")
    parser.add_argument("--post_id", help="Source post UUID")
    parser.add_argument("--client_id", help="Client UUID")
    parser.add_argument("--test", action="store_true", help="Run a test generation")
    
    args = parser.parse_args()
    
    if args.test:
        test_generate()
    elif args.post_id and args.client_id:
        generate_draft(args.post_id, args.client_id)
    else:
        parser.print_help()
