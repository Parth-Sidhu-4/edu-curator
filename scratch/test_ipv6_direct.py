import psycopg2

print("Attempting direct IPv6 connection...")
try:
    # In psycopg2, we can pass host parameter directly as IPv6 address
    conn = psycopg2.connect(
        host="2406:da1a:b00:1301:b7e0:af79:530b:ec9c",
        port=5432,
        user="postgres",
        password="VincenzoCassano04",
        database="postgres",
        sslmode="require"
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("IPV6 DIRECT SUCCESS:", cur.fetchone())
    conn.close()
except Exception as e:
    print("Connection failed:", e)
