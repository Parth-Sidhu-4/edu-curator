import sys
import time
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client
from edu_curator.cli import _topic_uuid

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)

topic_id = _topic_uuid(11)
print(f"Triggering curation job for topic SN 11 (ID: {topic_id})...")

# Insert pending job
res = supabase.table("curation_jobs").insert([{
    "topic_id": topic_id,
    "status": "pending"
}]).execute()
print("Queued Job:", res.data)
job_id = res.data[0]['id']

# Poll for job completion
print("Waiting for job to complete...")
start_time = time.time()
while time.time() - start_time < 300:
    time.sleep(5)
    job_res = supabase.table("curation_jobs").select("*").eq("id", job_id).execute()
    if job_res.data:
        status = job_res.data[0]['status']
        print(f"Current Job Status: {status}")
        if status in ['completed', 'failed']:
            print("Job Finished!")
            print(f"Error Message: {job_res.data[0].get('error_message')}")
            break
    else:
        print("Job record not found")

# Check content
content_res = supabase.table("topic_content").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(1).execute()
if content_res.data:
    print("\nLatest content keys:")
    print(content_res.data[0]['content_json'].keys())
    if 'subtopics' in content_res.data[0]['content_json']:
        print("Subtopics structure validated!")
        print("Number of subtopics generated:", len(content_res.data[0]['content_json']['subtopics']))
        for sub in content_res.data[0]['content_json']['subtopics']:
            print(f"  - Subtopic: {sub.get('subtopic_name')} (summary length: {len(sub.get('summary', ''))})")
else:
    print("\nNo content generated.")
