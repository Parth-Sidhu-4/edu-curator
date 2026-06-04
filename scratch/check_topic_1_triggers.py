import os
import json
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL", "").strip('"')
key = os.getenv("SUPABASE_KEY", "").strip('"')
sb = create_client(url, key)

# Fetch latest updated topic_knowledge record
res = sb.table("topic_knowledge").select("*").order("updated_at", desc=True).limit(1).execute()
if not res.data:
    print("No topic knowledge records found.")
    sys.exit(0)

tk = res.data[0]
topic_id = tk.get("topic_id")

# Fetch syllabus topic name
topic_res = sb.table("syllabus_topics").select("topic_name").eq("id", topic_id).execute()
topic_name = topic_res.data[0]["topic_name"] if topic_res.data else "Unknown"

print(f"Latest Resolved Topic: {topic_name} (ID: {topic_id})")
print("Confidence:", tk.get("confidence"))
print("Sources Used:", tk.get("sources_used"))

knowledge = tk.get("knowledge", {})
if isinstance(knowledge, str):
    knowledge = json.loads(knowledge)

print("Triggers:", json.dumps(knowledge.get("_review_triggers"), indent=2))
