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
sources = supabase.table("sources").select("id, title, topic_ids").execute().data
t_source_ids = [x['id'] for x in sources if x.get('id') and x.get('topic_ids') and uuid in x.get('topic_ids')]

# Fetch chunks from content_chunks
chunks_res = supabase.table("content_chunks").select("source_id").execute().data
topic_chunks = [c for c in chunks_res if c['source_id'] in t_source_ids]

print(f"Total sources for topic 11: {len(t_source_ids)}")
print(f"Total chunks extracted for topic 11 sources: {len(topic_chunks)}")

# Group by source_id
from collections import Counter
counts = Counter([c['source_id'] for c in topic_chunks])
print("\nChunks per source (top 15):")
for sid in t_source_ids[:15]:
    title = next((x['title'] for x in sources if x['id'] == sid), "Unknown")
    print(f"  {title}: {counts[sid]} chunks")
