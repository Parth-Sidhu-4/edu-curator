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

sql_path = workspace_root / "migrations" / "submit_review_rpc.sql"
sql_content = sql_path.read_text(encoding="utf-8")

try:
    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("Executing RPC definition command...")
    cursor.execute(sql_content)
    
    cursor.close()
    conn.close()
    print("RPC function submit_review created successfully!")
except Exception as e:
    print(f"Failed to create RPC function: {e}")
    exit(1)
