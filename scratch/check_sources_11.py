import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)

uuid = 'c0099faf-b297-5de5-a5a8-c0710d3ec0fc'
sources = supabase.table("sources").select("*").execute().data
t_sources = [x for x in sources if x.get('topic_ids') and uuid in x.get('topic_ids')]

non_completed = [x for x in t_sources if x.get('crawl_status') != 'completed']
print(f"Total sources: {len(t_sources)}")
print(f"Non-completed sources: {len(non_completed)}")
for x in non_completed:
    print(f"ID: {x['id']}, Title: {x.get('title')}, URL: {x.get('url')}, Status: {x.get('crawl_status')}")
