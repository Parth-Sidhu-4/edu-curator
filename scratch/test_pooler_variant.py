import psycopg2

host = "aws-0-ap-south-1.pooler.supabase.com"
password = "VincenzoCassano04"

test_cases = [
    # 1. Standard pooler: postgres.project_ref as user, postgres as db
    {"user": "postgres.qofphbmnxoorgbhtmmni", "database": "postgres", "port": 6543},
    # 2. Session pooler: postgres.project_ref as user, postgres as db, port 5432
    {"user": "postgres.qofphbmnxoorgbhtmmni", "database": "postgres", "port": 5432},
    # 3. Project ref in db name: postgres as user, postgres.project_ref as db
    {"user": "postgres", "database": "postgres.qofphbmnxoorgbhtmmni", "port": 6543},
    {"user": "postgres", "database": "postgres.qofphbmnxoorgbhtmmni", "port": 5432},
    # 4. Project ref in options: postgres as user, postgres as db, options='-c project=qofphbmnxoorgbhtmmni'
    {"user": "postgres", "database": "postgres", "port": 6543, "options": "-c project=qofphbmnxoorgbhtmmni"},
    {"user": "postgres", "database": "postgres", "port": 5432, "options": "-c project=qofphbmnxoorgbhtmmni"}
]

for idx, tc in enumerate(test_cases, 1):
    print(f"\n--- Test Case {idx}: user={tc.get('user')}, db={tc.get('database')}, port={tc.get('port')}, options={tc.get('options')} ---")
    try:
        conn = psycopg2.connect(
            host=host,
            port=tc["port"],
            user=tc["user"],
            password=password,
            database=tc["database"],
            options=tc.get("options"),
            sslmode="require"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            print("SUCCESS! Connected:", cur.fetchone())
        conn.close()
        break
    except Exception as e:
        print("Failed:", e)
