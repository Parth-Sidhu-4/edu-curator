import os
import psycopg2
from dotenv import load_dotenv

# Load env
dotenv_path = "d:/Internship/.env"
print(f"Loading env from {dotenv_path}...")
load_dotenv(dotenv_path=dotenv_path)

db_url = os.getenv("DATABASE_URL", "")
if "postgresql+psycopg2" in db_url:
    db_url = db_url.replace("postgresql+psycopg2", "postgresql")

print(f"Connecting to database...")
conn = psycopg2.connect(db_url)
conn.autocommit = True
cur = conn.cursor()

create_table_sql = """
CREATE TABLE IF NOT EXISTS evaluation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID NOT NULL REFERENCES syllabus_topics(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    logs TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_topic ON evaluation_jobs(topic_id);

-- Enable RLS
ALTER TABLE evaluation_jobs ENABLE ROW LEVEL SECURITY;

-- Policies
DROP POLICY IF EXISTS "Allow public read evaluation_jobs" ON evaluation_jobs;
DROP POLICY IF EXISTS "Allow public write evaluation_jobs" ON evaluation_jobs;

CREATE POLICY "Allow public read evaluation_jobs" ON evaluation_jobs 
    FOR SELECT TO anon, authenticated USING (true);

CREATE POLICY "Allow public write evaluation_jobs" ON evaluation_jobs 
    FOR ALL TO anon, authenticated USING (true);

-- Grants
GRANT ALL ON TABLE evaluation_jobs TO service_role, postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE evaluation_jobs TO anon, authenticated;
"""

try:
    print("Executing SQL to create evaluation_jobs table...")
    cur.execute(create_table_sql)
    print("Success: evaluation_jobs table created and permissions configured!")
except Exception as e:
    print(f"Error executing SQL: {e}")
finally:
    cur.close()
    conn.close()
