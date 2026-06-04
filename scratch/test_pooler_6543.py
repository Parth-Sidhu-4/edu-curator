import psycopg2

# Try connection pooler port 6543 (transaction mode / session mode)
db_url = "postgresql://postgres.qofphbmnxoorgbhtmmni:VincenzoCassano04@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require"
print("Attempting to connect to Supabase pooler on port 6543...")
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
