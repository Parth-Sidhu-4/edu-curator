import psycopg2

regions = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "eu-west-1",
    "eu-west-2",
    "eu-central-1",
    "ca-central-1"
]

for region in regions:
    host = f"aws-0-{region}.pooler.supabase.com"
    db_url = f"postgresql://postgres.qofphbmnxoorgbhtmmni:VincenzoCassano04@{host}:5432/postgres?sslmode=require"
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT current_user;")
            print(f"SUCCESS: Connected to region {region}!")
        conn.close()
        break
    except Exception as e:
        err_msg = str(e)
        if "tenant/user" not in err_msg:
            # If it's a password error or connection error (but NOT tenant not found), it might be the right region
            print(f"Region {region}: {err_msg}")
        else:
            print(f"Region {region}: Tenant not found")
