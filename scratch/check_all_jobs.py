import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)
res = supabase.table("curation_jobs").select("*").order("created_at", desc=True).limit(5).execute()
for j in res.data:
    print(f"ID: {j['id']} | Topic: {j['topic_id']} | Status: {j['status']} | Error: {j.get('error_message')} | Logs length: {len(j.get('logs') or '')}")
