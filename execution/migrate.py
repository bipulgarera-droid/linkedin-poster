"""
Apply schema migrations directly via Supabase Management API.
Run this once to set up the enhanced client onboarding schema.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

MIGRATION_SQL = """
-- Add voice analysis columns to clients
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS sample_posts text[] DEFAULT '{}';
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS voice_summary jsonb DEFAULT NULL;

-- Create design_templates table
CREATE TABLE IF NOT EXISTS public.design_templates (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id uuid REFERENCES public.clients(id) ON DELETE CASCADE,
  name text NOT NULL,
  style_prompt text NOT NULL,
  preview_url text,
  created_at timestamptz DEFAULT now()
);

-- RLS for design_templates
ALTER TABLE public.design_templates ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "dt_select" ON public.design_templates FOR SELECT TO public USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "dt_insert" ON public.design_templates FOR INSERT TO public WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "dt_update" ON public.design_templates FOR UPDATE TO public USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "dt_delete" ON public.design_templates FOR DELETE TO public USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
"""

if __name__ == "__main__":
    print("=" * 60)
    print("SCHEMA MIGRATION")
    print("=" * 60)
    print(f"\nSupabase URL: {SUPABASE_URL}")
    
    # Test if column already exists
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
    }
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/clients?select=sample_posts&limit=1", headers=headers)
    
    if resp.status_code == 200:
        print("\n✅ Schema already up to date (sample_posts column exists)")
    else:
        print(f"\n⚠️  Column doesn't exist yet (status {resp.status_code})")
        print("\nPlease run the following SQL in Supabase Dashboard → SQL Editor:")
        print("-" * 60)
        print(MIGRATION_SQL)
        print("-" * 60)
        print("\n📋 Copy the SQL above and paste it at:")
        print(f"   https://supabase.com/dashboard/project/{SUPABASE_URL.split('//')[1].split('.')[0]}/sql/new")
