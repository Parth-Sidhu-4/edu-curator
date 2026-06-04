import psycopg2

host = "aws-ap-south-1.pooler.supabase.com"
user = "postgres.qofphbmnxoorgbhtmmni"
password = "VincenzoCassano04"

print(f"Testing connection to {host} on port 6543...")
try:
    conn = psycopg2.connect(
        host=host,
        port=6543,
        user=user,
        password=password,
        database="postgres",
        sslmode="require"
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("CONNECTION SUCCESS (6543):", cur.fetchone())
    conn.close()
except Exception as e:
    print("Failed on 6543:", e)

print(f"\nTesting connection to {host} on port 5432...")
try:
    conn = psycopg2.connect(
        host=host,
        port=5432,
        user=user,
        password=password,
        database="postgres",
        sslmode="require"
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("CONNECTION SUCCESS (5432):", cur.fetchone())
    conn.close()
except Exception as e:
    print("Failed on 5432:", e)
