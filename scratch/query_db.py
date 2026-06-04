import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

root = Path("D:/Internship")
settings = load_settings(root)

supabase = create_client(settings.supabase_url, settings.supabase_key)
res = supabase.table("evaluation_results").select("*").execute()
print(f"Total evaluation results: {len(res.data)}")
for row in res.data:
    print(row)
