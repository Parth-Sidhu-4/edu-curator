import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

def fix_privileges():
    load_dotenv(Path("d:/Internship/.env"))
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return
        
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        
    print("Connecting to Supabase PostgreSQL...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            # First, check who current_user is
            cur.execute("SELECT current_user, session_user;")
            users = cur.fetchone()
            print(f"Connected as: current_user={users[0]}, session_user={users[1]}")
            
            # Execute GRANTS
            print("Granting ALL on public.knowledge_override_history...")
            cur.execute("GRANT ALL ON public.knowledge_override_history TO service_role;")
            cur.execute("GRANT ALL ON public.knowledge_override_history TO postgres;")
            cur.execute("GRANT ALL ON public.knowledge_override_history TO authenticated;")
            cur.execute("GRANT ALL ON public.knowledge_override_history TO anon;")
            
            # Also grant sequence permissions if there is any auto-increment
            try:
                cur.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role, postgres, authenticated;")
                print("Granted sequence permissions.")
            except Exception as seq_e:
                print(f"Sequence grant info/skip: {seq_e}")
                
            print("Privileges granted successfully!")
            
        conn.close()
    except Exception as e:
        print(f"Failed to fix privileges: {e}")

if __name__ == "__main__":
    fix_privileges()
