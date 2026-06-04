import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)
res = supabase.table("curation_jobs").select("logs, error_message").eq("id", "dd51b8cd-4721-498c-806c-77835a549b1b").execute()
if res.data:
    print("ERROR:", res.data[0]["error_message"])
    print("LOGS:", res.data[0]["logs"])
else:
    print("No logs found for this job ID")
