import psycopg2

regions = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-south-1",
    "ap-northeast-1",
    "ap-northeast-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-central-1",
    "eu-north-1",
    "ca-central-1",
    "sa-east-1"
]

for region in regions:
    host = f"aws-0-{region}.pooler.supabase.com"
    db_url = f"postgresql://postgres.qofphbmnxoorgbhtmmni:VincenzoCassano04@{host}:6543/postgres?sslmode=require"
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
        if "tenant/user" not in err_msg and "Tenant or user not found" not in err_msg:
            print(f"Region {region}: {err_msg}")
        else:
            # print(f"Region {region}: Tenant not found")
            pass
