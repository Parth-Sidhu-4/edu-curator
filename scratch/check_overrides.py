import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

load_dotenv(Path("D:/Internship/.env"))
root = Path("D:/Internship")
settings = load_settings(root)

supabase = create_client(settings.supabase_url, settings.supabase_key)

res = supabase.table("knowledge_overrides").select("*").execute()
print(f"Total overrides: {len(res.data)}")
for o in res.data:
    print(f"ID: {o['id']}")
    print(f"  Topic ID: {o['topic_id']}")
    print(f"  Field: {o['field_name']}")
    print(f"  Active: {o['is_active']}")
    val_str = str(o['corrected_value'])
    print(f"  Corrected (truncated): {val_str[:150]}...")
