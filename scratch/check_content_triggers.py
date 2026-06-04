import os
import json
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL", "").strip('"')
key = os.getenv("SUPABASE_KEY", "").strip('"')
sb = create_client(url, key)

# Fetch syllabus topic 1.1
res = sb.table("syllabus_topics").select("id").ilike("topic_name", "%1.1%").execute()
topic_id = res.data[0]["id"]

# Fetch topic_content
tc_res = sb.table("topic_content").select("*").eq("topic_id", topic_id).execute()
if tc_res.data:
    tc = tc_res.data[0]
    print("Generated Curriculum Page Content:")
    print("Confidence Score:", tc.get("confidence_score"))
    print("Sources Used Count:", len(tc.get("sources_used", [])))
    print("Review Status:", tc.get("review_status"))
else:
    print("No topic_content record found for Topic 1.1")
