import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

def apply_hardening():
    # Load .env
    load_dotenv(Path("d:/Internship/.env"))
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return
        
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        
    migration_file = Path("d:/Internship/migrations/security_hardening_migration.sql")
    if not migration_file.exists():
        print(f"Error: Migration file {migration_file} not found")
        return
        
    migration_sql = migration_file.read_text(encoding="utf-8")
    
    print("Connecting to Supabase PostgreSQL database...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Applying database security hardening migration (F-02 & F-16)...")
            cur.execute(migration_sql)
            print("Migration applied successfully!")
        conn.close()
    except Exception as e:
        print(f"Failed to apply hardening migration: {e}")

if __name__ == "__main__":
    apply_hardening()
