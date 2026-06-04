import psycopg2

db_url = "postgresql://postgres.qofphbmnxoorgbhtmmni:VincenzoCassano04@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"
print("Attempting to connect to Supabase via IPv4 pooler...")
try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, version();")
        res = cur.fetchone()
        print("CONNECTION SUCCESSFUL!")
        print("User:", res[0])
        print("Version:", res[1])
    conn.close()
except Exception as e:
    print("Connection failed:", e)
