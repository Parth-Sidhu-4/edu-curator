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

eval_res = supabase.table("evaluation_results").select("*").eq("topic_id", topic_uuid).order("created_at", desc=True).execute()
print(f"Total evaluation results for topic 11: {len(eval_res.data)}")
if eval_res.data:
    latest_eval = eval_res.data[0]
    print(f"\nLATEST EVALUATION RESULT:")
    print(f"ID: {latest_eval.get('id')}")
    print(f"Created At: {latest_eval.get('created_at')}")
    print(f"Faithfulness: {latest_eval.get('faithfulness_score')}/10")
    print(f"Completeness: {latest_eval.get('completeness_score')}/10")
    print("\nFaithfulness Reasoning:")
    print(latest_eval.get('faithfulness_reasoning'))
    print("\nCompleteness Reasoning:")
    print(latest_eval.get('completeness_reasoning'))
else:
    print("No evaluation results found for topic 11.")
