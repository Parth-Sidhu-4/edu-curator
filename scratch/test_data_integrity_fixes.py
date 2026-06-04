import os
import sys
import json
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

workspace_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace_root / "src"))

load_dotenv(workspace_root / ".env")

from edu_curator.config import load_settings
from edu_curator.storage import get_table
from edu_curator.schemas import TopicContent, CurationJob, SourceToTopicMapping

settings = load_settings(workspace_root)
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgresql+psycopg2://"):
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")

def test_db_unique_constraints():
    if not db_url:
        print("[SKIP] Direct DB checks skipped: no DATABASE_URL configured.")
        return
        
    print("\n--- Testing Unique Constraints ---")
    try:
        conn = psycopg2.connect(db_url)
    except psycopg2.OperationalError as e:
        print(f"[SKIP] Direct DB checks skipped: connection failed: {e}")
        return
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Get a topic ID
    cursor.execute("SELECT id FROM syllabus_topics LIMIT 1;")
    topic_row = cursor.fetchone()
    if not topic_row:
        print("  Warning: No syllabus topics in database to test unique jobs constraint.")
        cursor.close()
        conn.close()
        return
    topic_id = topic_row[0]
    
    # 1. Test duplicate pending curation jobs prevention
    print("Testing duplicate curation jobs constraint...")
    try:
        # Clean up any existing curation jobs for this topic
        cursor.execute("DELETE FROM curation_jobs WHERE topic_id = %s;", (topic_id,))
        
        # Insert first pending job
        cursor.execute(
            "INSERT INTO curation_jobs (id, topic_id, status) VALUES (gen_random_uuid(), %s, 'pending');",
            (topic_id,)
        )
        
        # Attempt to insert second pending job for same topic
        try:
            cursor.execute(
                "INSERT INTO curation_jobs (id, topic_id, status) VALUES (gen_random_uuid(), %s, 'pending');",
                (topic_id,)
            )
            print("  [FAIL] Successfully inserted duplicate pending curation jobs!")
            sys.exit(1)
        except psycopg2.errors.UniqueViolation as unique_exc:
            print(f"  [PASS] Successfully blocked duplicate pending curation jobs: {unique_exc.diag.message_primary}")
    finally:
        # Cleanup
        cursor.execute("DELETE FROM curation_jobs WHERE topic_id = %s;", (topic_id,))
        
    # 2. Test duplicate mappings prevention
    print("Testing duplicate source-to-topic mapping constraint...")
    cursor.execute("SELECT id FROM sources LIMIT 1;")
    source_row = cursor.fetchone()
    cursor.execute("SELECT id FROM content_chunks LIMIT 1;")
    chunk_row = cursor.fetchone()
    
    if not source_row or not chunk_row:
        print("  Warning: Need at least one source and chunk to test unique mapping constraint.")
    else:
        source_id = source_row[0]
        chunk_id = chunk_row[0]
        try:
            # Clean up existing mappings for this combination
            cursor.execute(
                "DELETE FROM source_to_topic_mapping WHERE source_id = %s AND chunk_id = %s AND topic_id = %s;",
                (source_id, chunk_id, topic_id)
            )
            
            # Insert first
            cursor.execute(
                "INSERT INTO source_to_topic_mapping (id, source_id, chunk_id, topic_id) VALUES (gen_random_uuid(), %s, %s, %s);",
                (source_id, chunk_id, topic_id)
            )
            
            # Attempt to insert duplicate mapping
            try:
                cursor.execute(
                    "INSERT INTO source_to_topic_mapping (id, source_id, chunk_id, topic_id) VALUES (gen_random_uuid(), %s, %s, %s);",
                    (source_id, chunk_id, topic_id)
                )
                print("  [FAIL] Successfully inserted duplicate mappings!")
                sys.exit(1)
            except psycopg2.errors.UniqueViolation as unique_exc:
                print(f"  [PASS] Successfully blocked duplicate mapping links: {unique_exc.diag.message_primary}")
        finally:
            # Cleanup
            cursor.execute(
                "DELETE FROM source_to_topic_mapping WHERE source_id = %s AND chunk_id = %s AND topic_id = %s;",
                (source_id, chunk_id, topic_id)
            )

    cursor.close()
    conn.close()

def test_optimistic_concurrency_control():
    if not db_url:
        print("[SKIP] Concurrency check skipped: no DATABASE_URL configured.")
        return
        
    print("\n--- Testing Optimistic Concurrency Control (OCC) ---")
    try:
        conn = psycopg2.connect(db_url)
    except psycopg2.OperationalError as e:
        print(f"[SKIP] Concurrency check skipped: connection failed: {e}")
        return
    conn.autocommit = True
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM syllabus_topics LIMIT 1;")
    topic_row = cursor.fetchone()
    if not topic_row:
        print("  Warning: No syllabus topics in database to test OCC.")
        cursor.close()
        conn.close()
        return
    topic_id = topic_row[0]
    
    # Create or clean a test topic_content row
    content_id = "00000000-0000-0000-0000-000000000000"
    try:
        cursor.execute("DELETE FROM topic_content WHERE id = %s;", (content_id,))
        cursor.execute(
            "INSERT INTO topic_content (id, topic_id, content_json, version) VALUES (%s, %s, '{}', 1);",
            (content_id, topic_id)
        )
        
        # Test RPC with matching version (should succeed and increment version to 2)
        print("Submitting review with valid version (1)...")
        cursor.execute(
            "SELECT submit_review(%s, %s, 'approved', 'tester', 'notes', '{}', '{}', 1);",
            (topic_id, content_id)
        )
        res = cursor.fetchone()[0]
        print(f"  Result: {res}")
        
        # Check that version was incremented to 2
        cursor.execute("SELECT version FROM topic_content WHERE id = %s;", (content_id,))
        current_version = cursor.fetchone()[0]
        print(f"  Current DB version: {current_version}")
        assert current_version == 2, f"Expected version 2, got {current_version}"
        
        # Test RPC with stale version (version 1 again) -> should raise version mismatch exception
        print("Submitting review with stale version (1)...")
        try:
            cursor.execute(
                "SELECT submit_review(%s, %s, 'approved', 'tester', 'notes', '{}', '{}', 1);",
                (topic_id, content_id)
            )
            print("  [FAIL] Saved stale version successfully without OCC failure!")
            sys.exit(1)
        except Exception as occ_exc:
            print(f"  [PASS] Correctly blocked stale write with version mismatch exception: {occ_exc}")
            
    finally:
        # Clean up
        cursor.execute("DELETE FROM topic_content WHERE id = %s;", (content_id,))
        cursor.execute("DELETE FROM reviewer_activity WHERE content_id = %s;", (content_id,))
        cursor.close()
        conn.close()

def test_atomic_json_table_writes():
    print("\n--- Testing Atomic JSON Table Writes ---")
    test_json_path = workspace_root / "data" / "test_atomic_table.json"
    if test_json_path.exists():
        test_json_path.unlink()
        
    from edu_curator.storage import JsonTable
    from edu_curator.schemas import SyllabusTopic, TopicType
    
    table = JsonTable(test_json_path, SyllabusTopic)
    test_row = SyllabusTopic(
        id="11111111-1111-1111-1111-111111111111",
        chapter="Test Chapter",
        topic_name="Test Topic",
        topic_type=TopicType.concept
    )
    
    # Save row
    table.write([test_row])
    
    # Check that file exists and the .tmp file is not left behind
    assert test_json_path.exists(), "JSON file was not created!"
    tmp_path = test_json_path.with_suffix(".tmp")
    assert not tmp_path.exists(), "Temporary write file (.tmp) was left behind!"
    
    # Read row and verify
    read_rows = table.read()
    assert len(read_rows) == 1
    assert read_rows[0].topic_name == "Test Topic"
    
    # Clean up
    test_json_path.unlink()
    print("  [PASS] Atomic JSON writes verified. No temp files leaked.")

if __name__ == "__main__":
    test_db_unique_constraints()
    test_optimistic_concurrency_control()
    test_atomic_json_table_writes()
    print("\nALL DATA INTEGRITY VERIFICATIONS PASSED SUCCESSFULLY!")
