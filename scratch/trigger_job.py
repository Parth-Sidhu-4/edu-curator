import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)

# Topic SN 4 deterministic UUID
from edu_curator.cli import _topic_uuid
topic_id = _topic_uuid(4)

# Insert pending job
res = supabase.table("curation_jobs").insert([{
    "topic_id": topic_id,
    "status": "pending"
}]).execute()
print("Queued Job:", res.data)
