import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL", "").strip('"')
key = os.getenv("SUPABASE_KEY", "").strip('"')
sb = create_client(url, key)

res = sb.table("topic_knowledge").select("*").eq("topic_id", "11111111-1111-1111-1111-111111111111").execute()
if res.data:
    tk = res.data[0]
    knowledge = tk.get("knowledge", {})
    if isinstance(knowledge, str):
        knowledge = json.loads(knowledge)
    
    print("Resolved Fields in Knowledge:")
    for k, v in knowledge.items():
        if k == "_review_triggers":
            print(f"_review_triggers: {json.dumps(v, indent=2)}")
        elif isinstance(v, dict) and "status" in v:
            print(f"- {k}: status={v['status']}, confidence={v.get('confidence')}")
        else:
            print(f"- {k}: type={type(v)}")
else:
    print("Record not found")
