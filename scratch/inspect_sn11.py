import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client
from edu_curator.cli import _topic_uuid

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)

topic_uuid = _topic_uuid(11)
print(f"Topic SN 11 maps to UUID: {topic_uuid}")

# Get syllabus topic
topic_res = supabase.table("syllabus_topics").select("*").eq("id", topic_uuid).execute()
print("\nSyllabus Topic:")
if topic_res.data:
    for k, v in topic_res.data[0].items():
        print(f"  {k}: {v}")
else:
    print("  Not found in syllabus_topics")

# Get one source to see its columns
sources_sample = supabase.table("sources").select("*").limit(1).execute()
if sources_sample.data:
    print("\nColumns in sources table:")
    for k in sources_sample.data[0].keys():
        print(f"  {k}")
else:
    print("\nNo sources found at all.")

# Query sources using topic_ids containment if it contains topic_uuid
# Postgrest syntax for array containment is CS (contains). Let's try contains or similar.
# Wait, let's also fetch sources and filter in python if needed, or query them.
sources_res = supabase.table("sources").select("*").execute()
print(f"\nAll sources count: {len(sources_res.data)}")
topic_sources = []
for s in sources_res.data:
    # check if topic_uuid is in s.get('topic_ids') or similar
    t_ids = s.get('topic_ids')
    if t_ids and (topic_uuid in t_ids or str(topic_uuid) in t_ids):
        topic_sources.append(s)

print(f"\nSources for Topic 11 ({len(topic_sources)}):")
for s in topic_sources:
    print(f"  ID: {s['id']}, URL: {s.get('url')}, Title: {s.get('title')}, Status: {s.get('status') or s.get('crawl_status') or s.get('ingest_status')}")

# Get curation jobs for this topic
jobs_res = supabase.table("curation_jobs").select("*").eq("topic_id", topic_uuid).order("created_at", desc=True).execute()
print(f"\nCuration Jobs ({len(jobs_res.data)}):")
for j in jobs_res.data:
    print(f"  ID: {j['id']}, Status: {j['status']}, Error: {j.get('error_message')}, Created At: {j.get('created_at')}")

# Get evaluation jobs for this topic
eval_jobs_res = supabase.table("evaluation_jobs").select("*").eq("topic_id", topic_uuid).order("created_at", desc=True).execute()
print(f"\nEvaluation Jobs ({len(eval_jobs_res.data)}):")
for j in eval_jobs_res.data:
    print(f"  ID: {j['id']}, Status: {j['status']}, Error: {j.get('error_message')}, Created At: {j.get('created_at')}")
