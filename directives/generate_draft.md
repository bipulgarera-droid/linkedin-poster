# Directive: Generate AI Draft from Scraped Post

## Goal
Take a high-performing scraped competitor post and use Gemini to rewrite the caption in the client's voice, then use Flux to generate a matching graphic. Store the result as a draft in Supabase.

## Inputs
- `post_id` (UUID) — the source post from the `posts` table
- `client_id` (UUID) — determines the voice/tone
- `client_voice_description` (string) — from clients table

## Execution Script
`execution/generate_content.py`

## Process
1. Fetch the source post from Supabase.
2. Fetch the client record for their `voice_description`.
3. Send the post content + voice description to Gemini with a prompt like:
   > "Rewrite this LinkedIn post in the following voice: {voice_description}. Keep the core message but make it original. Add relevant hashtags."
4. Send a prompt to Flux to generate a professional social media graphic based on the post topic.
5. Upload the generated image to Supabase Storage (`generated-images` bucket).
6. Insert a new record in the `drafts` table with status `pending`.

## Outputs
- New draft in `drafts` table
- Image in Supabase Storage

## Edge Cases
- Gemini API rate limit → retry 3x with backoff
- Flux image generation failure → create draft without image
- Client has no voice description → use a default professional voice
