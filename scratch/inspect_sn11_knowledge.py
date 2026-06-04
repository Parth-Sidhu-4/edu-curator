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
print(f"Topic SN 11 UUID: {topic_uuid}")

# Get resolved knowledge
knowledge_res = supabase.table("topic_knowledge").select("*").eq("topic_id", topic_uuid).execute()
if knowledge_res.data:
    tk = knowledge_res.data[0]
    knowledge = tk.get("knowledge", {})
    print("\nKnowledge keys in database:")
    for k in sorted(knowledge.keys()):
        print(f"  {k}")
else:
    print("No topic knowledge found in database for topic 11.")
