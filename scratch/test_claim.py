import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(str(Path("D:/Internship/src")))
from edu_curator.config import load_settings
from supabase import create_client

root = Path("D:/Internship")
settings = load_settings(root)
supabase = create_client(settings.supabase_url, settings.supabase_key)

try:
    print("Executing RPC claim_next_job...")
    res = supabase.rpc("claim_next_job", {"worker_name": "TestWorker"}).execute()
    print("Success! Data returned:")
    print(res.data)
except Exception as e:
    print("Failed to execute claim_next_job:")
    import traceback
    traceback.print_exc()
