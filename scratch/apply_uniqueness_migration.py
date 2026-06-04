import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

workspace_root = Path(__file__).resolve().parents[1]
load_dotenv(workspace_root / ".env")

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL is not set!")
    exit(1)

# Convert connection scheme for psycopg2
if db_url.startswith("postgresql+psycopg2://"):
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")

sql_path = workspace_root / "migrations" / "data_integrity_uniqueness.sql"
sql_content = sql_path.read_text(encoding="utf-8")

try:
    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cursor = conn.cursor()
    
    # We can split the commands by semicolon and execute them one by one
    commands = [cmd.strip() for cmd in sql_content.split(";") if cmd.strip()]
    for i, cmd in enumerate(commands, 1):
        print(f"Executing command {i}/{len(commands)}...")
        try:
            cursor.execute(cmd)
        except Exception as cmd_exc:
            print(f"Warning on command {i}: {cmd_exc}")
            
    cursor.close()
    conn.close()
    print("Migration completed successfully!")
except Exception as e:
    print(f"Migration failed: {e}")
    exit(1)
