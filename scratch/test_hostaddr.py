import psycopg2

print("Attempting connection with host and hostaddr...")
try:
    conn = psycopg2.connect(
        host="db.qofphbmnxoorgbhtmmni.supabase.co",
        hostaddr="3.108.251.216",
        port=6543,
        user="postgres",
        password="VincenzoCassano04",
        database="postgres",
        sslmode="require"
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("CONNECTION SUCCESSFUL:", cur.fetchone())
    conn.close()
except Exception as e:
    print("Connection failed:", e)
