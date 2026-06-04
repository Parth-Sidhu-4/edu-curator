import psycopg2
import socket

regions = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
    "ca-central-1", "sa-east-1"
]

project_ref = "qofphbmnxoorgbhtmmni"
password = "VincenzoCassano04"
user = f"postgres.{project_ref}"

for region in regions:
    for host_tmpl in [f"aws-0-{region}.pooler.supabase.com", f"aws-{region}.pooler.supabase.com"]:
        # Resolve host first to avoid slow connect timeouts on non-existent hosts
        try:
            ip = socket.gethostbyname(host_tmpl)
        except Exception:
            continue
            
        print(f"Testing {host_tmpl} ({ip}) on port 6543...")
        db_url = f"postgresql://{user}:{password}@{host_tmpl}:6543/postgres?sslmode=require"
        try:
            conn = psycopg2.connect(db_url, connect_timeout=5)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT current_user;")
                print(f"--> SUCCESS: Connected using {host_tmpl}!")
            conn.close()
            exit(0)
        except Exception as e:
            err_msg = str(e)
            if "tenant/user" not in err_msg.lower() and "tenant or user not found" not in err_msg.lower():
                print(f"--> POTENTIAL MATCH: {host_tmpl} returned: {err_msg}")
            else:
                pass
