# Directive: Scrape Competitor LinkedIn Posts

## Goal
Given a competitor's LinkedIn profile URL or a niche keyword, fetch their top-performing posts using Apify actors (no cookies required).

## Inputs
- `competitor_linkedin_url` (string) — e.g. `https://www.linkedin.com/in/garyvee/`
- `niche` (string, optional) — e.g. `marketing`, `fitness`
- `client_id` (UUID) — the client this scrape belongs to
- `competitor_id` (UUID) — the competitor record in Supabase

## Apify Actors
1. **Profile Posts**: `apimaestro/linkedin-profile-posts` — scrapes all recent posts from a specific LinkedIn profile.
2. **Keyword Search**: `curious_coder/linkedin-posts-search-scraper-no-cookies` — searches LinkedIn for posts by keyword/niche.

## Execution Script
`execution/scrape_apify.py`

## Process
1. Read `.env` for `APIFY_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.
2. Call the Apify actor via the Apify API client.
3. Wait for the run to complete.
4. Parse results → extract post content, engagement metrics, media URLs.
5. Calculate an `engagement_score` = likes + (comments * 2) + (shares * 3).
6. Insert each post into the Supabase `posts` table.
7. Update the `scrape_jobs` table with status and `posts_found` count.

## Outputs
- Posts saved to Supabase `posts` table
- Scrape job record updated in `scrape_jobs`

## Edge Cases
- Actor returns empty results → mark job as `completed` with `posts_found=0`
- Apify API rate limit → retry with exponential backoff (max 3 retries)
- Invalid LinkedIn URL → mark job as `failed` with error message
- LinkedIn profile is private → mark job as `failed`

## Learnings
- **CRITICAL**: The Apify API uses `username~actorname` format (with TILDE `~`), NOT `username/actorname` (with slash). Using a slash will result in a 404 error.
- The `apimaestro~linkedin-profile-posts` actor does NOT require cookies.
- Set `maxItems` to 20 for initial scrapes to save credits.
- The actor accepts both full URLs and usernames.
