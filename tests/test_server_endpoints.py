import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from edu_curator.schemas import (
    SyllabusTopic, Source, TopicContent, CurationJob, ReviewerActivity,
    KnowledgeOverride, KnowledgeOverrideHistory, EvaluationJob, ReviewStatus, TopicType,
    ProcessingStatus
)
import dashboard.serve
from dashboard.serve import app, get_current_user_email

class MockUser:
    def __init__(self, email):
        self.email = email

class MockUserResponse:
    def __init__(self, email):
        self.user = MockUser(email)

class MockAuth:
    def get_user(self, token):
        if token == "valid_token":
            return MockUserResponse("test_reviewer@example.com")
        elif token == "non_allowlist_token":
            return MockUserResponse("outsider@example.com")
        else:
            raise Exception("Invalid token")

class MockResponse:
    def __init__(self, data, count=0):
        self.data = data
        self.count = count

class MockQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *args, **kwargs):
        count_exact = kwargs.get("count") == "exact"
        class Chain:
            def __init__(self, data, count_exact):
                self._data = data
                self._count_exact = count_exact
            def limit(self, *args, **kwargs):
                return self
            def eq(self, field, value):
                self._data = [d for d in self._data if d.get(field) == value]
                return self
            def execute(self):
                return MockResponse(self._data, count=1 if self._data else 0)
        return Chain(self._data, count_exact)

class MockSupabaseClient:
    def __init__(self, url, key):
        self.auth = MockAuth()
        self.emails = [{"email": "test_reviewer@example.com"}]
        
    def table(self, name):
        if name == "allowed_emails":
            return MockQuery(self.emails)
        class DummyChain:
            def delete(self, *args, **kwargs): return self
            def neq(self, *args, **kwargs): return self
            def insert(self, *args, **kwargs): return self
            def upsert(self, *args, **kwargs): return self
            def execute(self): return MockResponse([])
        return DummyChain()

@pytest.fixture
def client(monkeypatch, tmp_path):
    # Mock get_table to write to tmp_path
    import edu_curator.storage
    
    def mocked_get_table(name, model, settings=None):
        return edu_curator.storage.JsonTable(tmp_path / f"{name}.json", model, name=name)
        
    monkeypatch.setattr(edu_curator.storage, "get_table", mocked_get_table)
    monkeypatch.setattr(dashboard.serve, "get_table", mocked_get_table)
    
    # Mock environment and variables
    monkeypatch.setenv("START_IN_PROCESS_WORKER", "false")
    monkeypatch.setattr(dashboard.serve, "SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr(dashboard.serve, "SUPABASE_KEY", "mock_service_key")
    monkeypatch.setattr(dashboard.serve, "SUPABASE_BROWSER_KEY", "mock_anon_key")
    monkeypatch.setattr(dashboard.serve, "ALLOWED_EMAILS", {"test_reviewer@example.com"})
    
    # Mock background runner functions to prevent subprocess calls
    monkeypatch.setattr(dashboard.serve, "run_ingest", lambda source_id: None)
    monkeypatch.setattr(dashboard.serve, "run_evaluation_task", lambda topic_sn, job_id=None: None)
    monkeypatch.setattr(dashboard.serve, "_get_server_redis", lambda: None)
    
    # Mock supabase client module
    monkeypatch.setattr("supabase.create_client", lambda url, key: MockSupabaseClient(url, key))
    
    # Clear overrides before each test
    app.dependency_overrides.clear()
    
    # Redefine index files to point to real ones in dashboard folder, but allow writing uploads to tmp
    monkeypatch.setattr(dashboard.serve, "ROOT", tmp_path)
    
    # Set up app.dependency_overrides to bypass email authorization for most tests
    # Individual tests can override this as needed.
    app.dependency_overrides[get_current_user_email] = lambda: "test_reviewer@example.com"
    
    # Clear rate limiter dictionaries before each test to ensure tests are isolated
    dashboard.serve.ip_request_history.clear()
    dashboard.serve.auth_request_history.clear()
    
    yield TestClient(app)
    
    app.dependency_overrides.clear()

def test_read_index(client):
    # Tests GET / and GET /index.html
    for path in ["/", "/index.html"]:
        response = client.get(path)
        assert response.status_code == 200
        # Check security headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Content-Security-Policy" in response.headers
        
        # Verify content substitution
        content = response.text
        assert "https://mock.supabase.co" in content
        assert "mock_anon_key" in content
        assert "{{SUPABASE_URL_VALUE}}" not in content
        assert "{{SUPABASE_KEY_VALUE}}" not in content
        assert "{{CSP_NONCE}}" not in content

def test_read_static_assets(client):
    # Tests app.js, style.css, purify.min.js
    for asset in ["/app.js", "/style.css", "/purify.min.js"]:
        response = client.get(asset)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    # Tests all new JS module endpoints
    allowed_js_paths = [
        "/state.js", "/utils.js", "/api.js", "/auth.js",
        "/views/index.js", "/views/overview.js", "/views/content.js",
        "/views/topics.js", "/views/sources.js", "/views/observability.js",
        "/views/evaluation.js"
    ]
    for path in allowed_js_paths:
        response = client.get(path)
        assert response.status_code == 200, f"Failed for {path}"
        assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    # Tests disallowed path traversal or arbitrary JS request returns 404
    disallowed = [
        "/non_existent.js", "/views/non_existent.js", "/../../serve.py",
        "/../../../etc/passwd", "/../../../etc/passwd.js"
    ]
    for path in disallowed:
        response = client.get(path)
        assert response.status_code == 404, f"Path {path} should return 404 but got {response.status_code}"


def test_auth_verify_endpoint(client, monkeypatch):
    # Clear dependency override to test verify auth token logic
    app.dependency_overrides.clear()
    
    # 1. No Authorization header
    response = client.post("/api/auth/verify")
    assert response.status_code == 401
    
    # 2. Invalid Token
    response = client.post("/api/auth/verify", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    
    # 3. Valid Token but email not in allowlist
    response = client.post("/api/auth/verify", headers={"Authorization": "Bearer non_allowlist_token"})
    assert response.status_code == 403
    
    # 4. Valid Token and email in allowlist
    response = client.post("/api/auth/verify", headers={"Authorization": "Bearer valid_token"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "email": "test_reviewer@example.com"}

def test_dependency_auth_check(client):
    # Test that api routes fail if user is not verified/authorized
    app.dependency_overrides.clear()
    
    # No Auth -> 401
    response = client.post("/api/topic", json={"action": "insert", "topic": {}})
    assert response.status_code == 401

def test_manage_topic_endpoint(client):
    # Insert topic
    topic_data = {
        "id": "t1",
        "chapter": "Chapter 1",
        "topic_name": "Test Topic",
        "topic_type": "concept",
        "keywords": ["test"],
        "difficulty_level": "easy"
    }
    
    # Insert
    res = client.post("/api/topic", json={"action": "insert", "topic": topic_data})
    assert res.status_code == 200
    assert res.json()["status"] == "inserted"
    
    # Read back to verify
    from edu_curator.storage import get_table
    tbl = get_table("syllabus_topics", SyllabusTopic)
    topics = tbl.read(filters={"id": "t1"})
    assert len(topics) == 1
    assert topics[0].topic_name == "Test Topic"
    
    # Update
    update_data = {
        "action": "update",
        "id": "t1",
        "fields": {
            "topic_name": "Updated Topic Name",
            "status": "processing"
        }
    }
    res = client.post("/api/topic", json=update_data)
    assert res.status_code == 200
    assert res.json()["status"] == "updated"
    
    topics = tbl.read(filters={"id": "t1"})
    assert topics[0].topic_name == "Updated Topic Name"
    assert topics[0].status == "processing"
    
    # Delete
    delete_data = {
        "action": "delete",
        "id": "t1"
    }
    res = client.post("/api/topic", json=delete_data)
    assert res.status_code == 200
    assert res.json()["status"] == "deleted"
    
    topics = tbl.read(filters={"id": "t1"})
    assert len(topics) == 0

def test_manage_source_endpoint(client):
    source_data = {
        "id": "s1",
        "title": "Test Source",
        "source_type": "website",
        "url": "https://example.com/source",
        "trust_score": 7.5,
        "license_type": "MIT"
    }
    res = client.post("/api/source", json={"source": source_data})
    assert res.status_code == 200
    assert res.json()["status"] == "inserted"
    
    from edu_curator.storage import get_table
    tbl = get_table("sources", Source)
    sources = tbl.read(filters={"id": "s1"})
    assert len(sources) == 1
    assert sources[0].title == "Test Source"
    assert sources[0].trust_score == 7.5

def test_manage_job_endpoint(client):
    # Test Curation Job queue
    res = client.post("/api/job", json={"action": "insert", "topic_id": "t1", "table": "curation_jobs"})
    assert res.status_code == 200
    assert res.json()["status"] == "queued"
    
    from edu_curator.storage import get_table
    tbl = get_table("curation_jobs", CurationJob)
    jobs = tbl.read(filters={"topic_id": "t1"})
    assert len(jobs) == 1
    assert jobs[0].status == "pending"
    
    job_id = jobs[0].id
    
    # Reset Job
    res = client.post("/api/job", json={"action": "reset", "job_id": job_id, "table": "curation_jobs"})
    assert res.status_code == 200
    assert res.json()["status"] == "reset"
    
    jobs = tbl.read(filters={"id": job_id})
    assert jobs[0].status == "failed"

def test_submit_review_endpoint_occ(client):
    from edu_curator.storage import get_table
    
    # Populate SyllabusTopic
    topics_tbl = get_table("syllabus_topics", SyllabusTopic)
    topic = SyllabusTopic(
        id="topic_occ",
        chapter="1",
        topic_name="OCC Topic",
        topic_type=TopicType.concept
    )
    topics_tbl.write([topic])
    
    # Populate TopicContent
    content_tbl = get_table("topic_content", TopicContent)
    content = TopicContent(
        id="content_occ",
        topic_id="topic_occ",
        content_json={"definition": "Initial definition"},
        version=1,
        review_status=ReviewStatus.pending
    )
    content_tbl.write([content])
    
    # Test Concurrency OCC: submit with outdated/wrong version (e.g. 2 instead of 1)
    res = client.post("/api/review", json={
        "content_id": "content_occ",
        "topic_id": "topic_occ",
        "review_status": "approved",
        "content_json": {"definition": "Updated definition"},
        "version": 2
    })
    # Must raise Conflict / 409
    assert res.status_code == 409
    assert "Conflict" in res.json()["detail"]
    
    # Verify content not modified
    content_rows = content_tbl.read(filters={"id": "content_occ"})
    assert content_rows[0].version == 1
    assert content_rows[0].content_json == {"definition": "Initial definition"}
    
    # Test Success OCC: submit with correct version=1
    res = client.post("/api/review", json={
        "content_id": "content_occ",
        "topic_id": "topic_occ",
        "review_status": "approved",
        "content_json": {"definition": "Updated definition"},
        "version": 1
    })
    assert res.status_code == 200
    assert res.json()["status"] == "reviewed"
    
    # Verify content updated and version incremented
    content_rows = content_tbl.read(filters={"id": "content_occ"})
    assert content_rows[0].version == 2
    assert content_rows[0].review_status == ReviewStatus.approved

def test_api_upload_endpoint(client, tmp_path):
    # 1. Normal valid text file
    response = client.post("/api/upload?filename=test.txt", content=b"hello text content")
    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
    
    # Verify file saved locally in temporary data/uploads (resolved under ROOT, which is mocked to tmp_path)
    expected_path = tmp_path / "data" / "uploads" / "test.txt"
    assert expected_path.exists()
    assert expected_path.read_bytes() == b"hello text content"
    
    # 2. PDF signature check - fails if invalid
    response = client.post("/api/upload?filename=doc.pdf", content=b"invalid pdf bytes")
    assert response.status_code == 400
    assert "signature validation failed" in response.json()["detail"]
    
    # 3. PDF signature check - passes if starts with %PDF
    response = client.post("/api/upload?filename=doc.pdf", content=b"%PDF-1.4 mock pdf data")
    assert response.status_code == 200
    
    # 4. Large file (exceeds limit)
    # The endpoint checks content_length headers. Note: we mock headers.
    large_bytes = b"x" * 21 * 1024 * 1024
    response = client.post("/api/upload?filename=big.txt", content=large_bytes)
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]
    
    # 5. Forbidden extension
    response = client.post("/api/upload?filename=danger.exe", content=b"mock exe content")
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]
    
    # 6. Traversal/Invalid filename attempt
    response = client.post("/api/upload?filename=..", content=b"traversal")
    assert response.status_code == 400
    assert "Invalid filename" in response.json()["detail"]

    response = client.post("/api/upload?filename=.hidden", content=b"traversal")
    assert response.status_code == 400
    assert "Invalid filename" in response.json()["detail"]

    # 7. Cross-platform backslash path traversal attempt (simulating Linux behavior)
    import os
    import posixpath
    original_basename = os.path.basename
    original_splitext = os.path.splitext
    try:
        os.path.basename = posixpath.basename
        os.path.splitext = posixpath.splitext
        response = client.post("/api/upload?filename=a\\..\\..\\danger.txt", content=b"traversal")
        assert response.status_code == 400
        assert "Path traversal attempt detected" in response.json()["detail"]
    finally:
        os.path.basename = original_basename
        os.path.splitext = original_splitext

def test_rate_limiting_middleware(client, monkeypatch):
    # Restrict max requests to 2 to test the middleware
    monkeypatch.setattr(dashboard.serve, "RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(dashboard.serve, "RATE_LIMIT_AUTH_MAX", 2)
    
    # Send 2 valid POST requests -> status should not be 429
    for _ in range(2):
        response = client.post("/api/topic", json={"action": "insert", "topic": {
            "id": "t_rate", "chapter": "1", "topic_name": "Rate Limit", "topic_type": "concept"
        }})
        assert response.status_code != 429
        
    # 3rd request must trigger 429
    response = client.post("/api/topic", json={"action": "insert", "topic": {}})
    assert response.status_code == 429
    assert "Too many requests" in response.json()["error"]

def test_api_ingest_status_update(client):
    from edu_curator.schemas import Source
    # Insert a source first
    source_data = {
        "id": "s_ingest_test",
        "title": "Test Ingest Source",
        "source_type": "website",
        "url": "https://example.com/source",
        "trust_score": 7.5,
        "crawl_status": "pending"
    }
    # Register the source
    res_insert = client.post("/api/source", json={"source": source_data})
    assert res_insert.status_code == 200

    # Call /api/ingest
    res_ingest = client.post("/api/ingest", json={"source_id": "s_ingest_test"})
    assert res_ingest.status_code == 200
    assert res_ingest.json() == {"status": "processing"}

    # Read back source to verify crawl_status is "processing"
    from edu_curator.storage import get_table
    tbl = get_table("sources", Source)
    sources = tbl.read(filters={"id": "s_ingest_test"})
    assert len(sources) == 1
    assert sources[0].crawl_status == "processing"


def test_serve_upload_endpoint(client, tmp_path):
    # 1. Prepare a file in the mocked uploads directory
    uploads_dir = tmp_path / "data" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    test_file = uploads_dir / "test_serve.png"
    test_file.write_bytes(b"\x89PNG\r\n\x1a\nimage_data")

    # 2. Query the endpoint
    response = client.get("/data/uploads/test_serve.png")
    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\nimage_data"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-cache"

    # 3. Test non-existent file
    response = client.get("/data/uploads/non_existent.png")
    assert response.status_code == 404

    # 4. Path traversal attempt
    response = client.get("/data/uploads/../../secret.txt")
    # FastAPI path routing or path traversal check: if path traversal check in FastAPI/starlette normalizes it,
    # it may either match another route or be blocked by path validation.
    # Let's assert status code is 400 or 404 (traversal attempts should fail).
    assert response.status_code in (400, 404)
