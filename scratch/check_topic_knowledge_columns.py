import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL", "").strip('"')
key = os.getenv("SUPABASE_KEY", "").strip('"')
sb = create_client(url, key)

res = sb.table("topic_knowledge").select("*").limit(1).execute()
if res.data:
    print("topic_knowledge columns:", json.dumps(list(res.data[0].keys())))
else:
    print("topic_knowledge: no data")
