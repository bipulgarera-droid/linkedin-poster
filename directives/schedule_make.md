# Directive: Schedule Post via Make.com

**Goal:** Send approved drafts to a Make.com webhook to be scheduled on LinkedIn.

## Inputs
- `draft_id`: The UUID of the approved draft in the `drafts` table.
- Required Env Vars:
  - `MAKE_WEBHOOK_URL` (the endpoint provided by Make.com for the custom webhook trigger)
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`

## Execution Script
**Target:** `execution/webhook_make.py`

## Process
1. Query Supabase `drafts` table for the provided `draft_id`.
2. Verify the draft `status` is exactly `approved`.
3. Construct the payload containing `text` (caption), `image_url` (if any), and `author` (`client_id`).
4. Send a POST request to the `MAKE_WEBHOOK_URL`.
5. Check if the response is 2xx. If successful, update the draft `status` to `scheduled`.

## Outputs
- Draft status updated to `scheduled`
- Post queued in Buffer

## Edge Cases
- Buffer API returns 401 → token expired, notify user
- Image URL not accessible → post text only
- Buffer queue full → retry after 60 seconds
