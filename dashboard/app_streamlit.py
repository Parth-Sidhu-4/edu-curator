import os
import sys
import datetime
from pathlib import Path
import streamlit as st
import pandas as pd

# Ensure we can import our core modules
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from edu_curator.config import load_settings
from edu_curator.schemas import SyllabusTopic, Source, FactExtraction, TopicContent, NormalizedDocument, ContentChunk, ReviewStatus, ProcessingStatus, TopicType, SourceType
from edu_curator.ids import new_id
from edu_curator.storage import get_table

st.set_page_config(page_title="Edu-Curator Dashboard", page_icon="📚", layout="wide")
st.title("📚 Edu-Curator Content Pipeline")

# Load settings and Supabase client
@st.cache_resource
def get_settings():
    return load_settings(ROOT)

settings = get_settings()

if not settings.supabase_url or not settings.supabase_key:
    st.error("⚠️ Supabase credentials not found. Please set `SUPABASE_URL` and `SUPABASE_KEY` in `.env`.")
    st.stop()

# Start background local queue worker thread
import threading
import time

@st.cache_resource
def start_local_worker():
    def worker_loop():
        import sys
        import subprocess
        from supabase import create_client
        import datetime
        
        thread_settings = load_settings(ROOT)
        if not thread_settings.supabase_url or not thread_settings.supabase_key:
            return
            
        supabase = create_client(thread_settings.supabase_url, thread_settings.supabase_key)
        
        # Reset any stuck "running" jobs to "failed" when the worker starts up
        try:
            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            supabase.table("curation_jobs").update({
                "status": "failed",
                "error_message": "Worker thread restarted. Stale job was aborted.",
                "updated_at": now_str
            }).eq("status", "running").execute()
        except Exception as e:
            pass
            
        while True:
            try:
                res = supabase.table("curation_jobs").select("*").eq("status", "pending").order("created_at").limit(1).execute()
                jobs = res.data
                if not jobs:
                    time.sleep(2)
                    continue
                    
                job = jobs[0]
                job_id = job["id"]
                topic_id = job["topic_id"]
                
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                transition = supabase.table("curation_jobs").update({
                    "status": "running",
                    "updated_at": now_str
                }).eq("id", job_id).eq("status", "pending").execute()
                
                if not transition.data:
                    continue
                    
                from edu_curator.cli import _topic_uuid
                topic_sn = None
                for sn_val in range(1, 100):
                    if _topic_uuid(sn_val) == topic_id:
                        topic_sn = sn_val
                        break
                        
                if topic_sn is None:
                    supabase.table("curation_jobs").update({
                        "status": "failed",
                        "error_message": f"Could not resolve serial number for topic ID: {topic_id}",
                        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }).eq("id", job_id).execute()
                    continue
                    
                cmd = [sys.executable, "-m", "edu_curator.cli", "run-topic", "--sn", str(topic_sn)]
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT / "src")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(ROOT),
                    env=env
                )
                
                log_lines = []
                last_db_update = time.time()
                
                while True:
                    line = process.stdout.readline()
                    if line == "" and process.poll() is not None:
                        break
                    if line:
                        log_lines.append(line)
                        if time.time() - last_db_update > 2.0:
                            supabase.table("curation_jobs").update({
                                "logs": "".join(log_lines),
                                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            }).eq("id", job_id).execute()
                            last_db_update = time.time()
                            
                rc = process.poll()
                supabase.table("curation_jobs").update({
                    "logs": "".join(log_lines),
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }).eq("id", job_id).execute()
                
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                if rc == 0:
                    supabase.table("curation_jobs").update({
                        "status": "completed",
                        "updated_at": now_str
                    }).eq("id", job_id).execute()
                else:
                    supabase.table("curation_jobs").update({
                        "status": "failed",
                        "error_message": f"Pipeline execution failed with exit code {rc}.",
                        "updated_at": now_str
                    }).eq("id", job_id).execute()
                    
            except Exception as e:
                try:
                    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    supabase.table("curation_jobs").update({
                        "status": "failed",
                        "error_message": str(e),
                        "updated_at": now_str
                    }).eq("id", job_id).execute()
                except:
                    pass
                time.sleep(2)

    thread = threading.Thread(target=worker_loop, daemon=True, name="EduCuratorLocalQueueWorker")
    thread.start()
    return "Active"

worker_status = start_local_worker()

def fetch_latest_job(topic_id):
    try:
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        response = supabase.table("curation_jobs").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(1).execute()
        return response.data[0] if response.data else None
    except:
        return None

@st.cache_data(ttl=60) # Cache for 60 seconds
def fetch_topics():
    table = get_table("syllabus_topics", SyllabusTopic, settings)
    return table.read()

@st.cache_data(ttl=60)
def fetch_sources():
    table = get_table("sources", Source, settings)
    return table.read()

@st.cache_data(ttl=60)
def fetch_extractions():
    table = get_table("fact_extractions", FactExtraction, settings)
    return table.read()

@st.cache_data(ttl=60)
def fetch_content():
    table = get_table("topic_content", TopicContent, settings)
    return table.read()

# Load data
with st.spinner("Loading data from Supabase..."):
    topics = fetch_topics()
    sources = fetch_sources()
    extractions = fetch_extractions()
    content = fetch_content()

# Create tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Overview", "📑 Content Viewer", "🗂️ Topic Management", "🔌 Source Ingest", "📂 Sources", "💰 Cost & Observability"])

with tab1:
    st.header("Pipeline Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Topics", len(topics))
    col2.metric("Total Sources", len(sources))
    col3.metric("Facts Extracted", len(extractions))
    col4.metric("Generated Content", len(content))
    
    st.subheader("Topics Status")
    if topics:
        topics_df = pd.DataFrame([t.model_dump() for t in topics])
        st.dataframe(topics_df[['chapter', 'topic_name', 'topic_type', 'status', 'difficulty_level']], use_container_width=True)
    else:
        st.info("No topics found.")

with tab2:
    st.header("Content Viewer")
    
    if not topics:
        st.info("No topics available.")
    else:
        topic_options = {f"{t.topic_name}": t.id for t in topics}
        selected_topic_name = st.selectbox("Select a Topic", list(topic_options.keys()))
        selected_topic_id = topic_options[selected_topic_name]
        topic_obj = [t for t in topics if t.id == selected_topic_id][0]
        
        # Check active curation jobs
        latest_job = fetch_latest_job(selected_topic_id)
        job_active = latest_job and latest_job.get("status") in {"pending", "running"}
        
        # Pipeline execution button
        st.markdown("### ⚡ Run Content Generation Pipeline")
        col_run1, col_run2 = st.columns([1, 2])
        with col_run1:
            if job_active:
                st.button("Generation in progress...", disabled=True, key="run_pipeline_btn_disabled")
                if st.button("⚠️ Force Reset Stuck Job", key="force_reset_job_btn"):
                    try:
                        from supabase import create_client
                        import datetime
                        supabase = create_client(settings.supabase_url, settings.supabase_key)
                        supabase.table("curation_jobs").update({
                            "status": "failed",
                            "error_message": "Manually reset by user from dashboard.",
                            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }).eq("id", latest_job["id"]).execute()
                        st.success("Job status reset successfully!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to reset job: {exc}")
            else:
                run_btn = st.button("Generate / Re-generate Content", key="run_pipeline_btn")
        with col_run2:
            if job_active:
                st.caption(f"Curation task status: **{latest_job['status'].upper()}** (Job ID: `{latest_job['id'][:8]}`). Logs streaming below.")
            else:
                st.caption("This inserts a background curation job in Supabase to run async.")
            
        if not job_active and run_btn:
            selected_topic = [t for t in topics if t.id == selected_topic_id][0]
            # Determine topic serial number
            from edu_curator.cli import _topic_uuid
            topic_sn = None
            for sn_val in range(1, 100):
                if _topic_uuid(sn_val) == selected_topic_id:
                    topic_sn = sn_val
                    break
            
            if topic_sn is None:
                st.error("Could not determine Topic Serial Number for execution.")
            else:
                try:
                    from supabase import create_client
                    import datetime
                    supabase = create_client(settings.supabase_url, settings.supabase_key)
                    job_id = new_id()
                    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    supabase.table("curation_jobs").insert({
                        "id": job_id,
                        "topic_id": selected_topic_id,
                        "status": "pending",
                        "logs": "Job successfully queued. Waiting for worker...\n",
                        "created_at": now_str,
                        "updated_at": now_str
                    }).execute()
                    st.success(f"Curation job queued successfully! Job ID: `{job_id[:8]}`")
                    st.session_state.running_job_id = job_id
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to submit curation task: {exc}")

        # Render active log stream or failure/success status
        if latest_job:
            status = latest_job["status"]
            if status in {"pending", "running"}:
                st.info(f"⏳ Background Curation Job is **{status.upper()}**")
                with st.expander("📝 Live Pipeline execution logs", expanded=True):
                    st.code(latest_job.get("logs", ""))
                
                # Make sure we track this job's lifecycle
                if st.session_state.get("running_job_id") != latest_job["id"]:
                    st.session_state.running_job_id = latest_job["id"]
                
                # Auto-poll
                time.sleep(1.5)
                st.rerun()
            elif status == "completed":
                was_running = st.session_state.get("running_job_id") == latest_job["id"]
                if was_running:
                    st.success(f"🎉 Background Curation Job `{latest_job['id'][:8]}` completed successfully! Reloading data...")
                    st.cache_data.clear()
                    if "running_job_id" in st.session_state:
                        del st.session_state.running_job_id
                    st.rerun()
                else:
                    st.success(f"🎉 Pipeline status: **COMPLETED** (Job ID: `{latest_job['id'][:8]}`). Logs available below.")
                    with st.expander("📝 Pipeline execution logs", expanded=False):
                        st.code(latest_job.get("logs", ""))
            elif status == "failed":
                st.error(f"❌ Curation Job ID `{latest_job['id'][:8]}` failed: {latest_job.get('error_message')}")
                with st.expander("📝 Pipeline execution logs", expanded=True):
                    st.code(latest_job.get("logs", ""))
                if st.session_state.get("running_job_id") == latest_job["id"]:
                    if "running_job_id" in st.session_state:
                        del st.session_state.running_job_id

        # Display facts
        st.subheader("Extracted Facts")
        topic_facts = [f for f in extractions if f.topic_id == selected_topic_id]
        if topic_facts:
            facts_data = []
            for f in topic_facts:
                d = f.model_dump()
                val_dict = d.get("field_value", {})
                inner_val = val_dict.get("value") if isinstance(val_dict, dict) else val_dict
                if isinstance(inner_val, list):
                    d["field_value"] = ", ".join(str(x) for x in inner_val)
                else:
                    d["field_value"] = str(inner_val)
                facts_data.append(d)
            facts_df = pd.DataFrame(facts_data)
            st.dataframe(facts_df[['field_name', 'field_value', 'extraction_confidence', 'source_id']], use_container_width=True)
        else:
            st.info("No facts extracted for this topic yet.")
            
        # Display Generated Content
        st.subheader("Final Generated Content")
        topic_contents = [c for c in content if c.topic_id == selected_topic_id]
        
        if topic_contents:
            tc = topic_contents[0].content_json
            st.markdown(f"**Confidence Score:** {topic_contents[0].confidence_score}")
            st.markdown(f"**Consistency Check:** {'✅ PASS' if topic_contents[0].consistency_check_status else '❌ FAIL'}")
            
            # Sub-tabs for Sectioned vs Complete textbook page markdown
            view_tab1, view_tab2 = st.tabs(["📑 Interactive Sections", "📖 Full Textbook Page (Markdown)"])
            
            with view_tab1:
                with st.expander("Summary", expanded=True):
                    st.write(tc.get("summary", ""))
                
                with st.expander("Definition"):
                    st.write(tc.get("definition", ""))
                    
                with st.expander("Key Properties"):
                    for prop in tc.get("key_properties", []):
                        st.markdown(f"- {prop}")
                        
                with st.expander("Benefits & Limitations"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Benefits**")
                        for b in tc.get("benefits", []):
                            st.markdown(f"- {b}")
                    with col2:
                        st.markdown("**Limitations**")
                        for l in tc.get("limitations", []):
                            st.markdown(f"- {l}")
                            
                with st.expander("References & Citations", expanded=True):
                    used_source_ids = topic_contents[0].sources_used
                    if used_source_ids:
                        used_sources = [s for s in sources if s.id in used_source_ids]
                        for idx, src in enumerate(used_sources, 1):
                            if src.url:
                                st.markdown(f"{idx}. **[{src.title}]({src.url})**  \n   *URL: {src.url}*")
                            else:
                                st.markdown(f"{idx}. **{src.title}** *(Local Document: {src.local_path})*")
                    else:
                        st.info("No sources were flagged as actively used for this generated content.")
                        
            with view_tab2:
                # Compile full textbook markdown page
                md_lines = []
                md_lines.append(f"# {tc.get('topic_name', '') or topic_obj.topic_name}")
                md_lines.append("\n## Summary")
                md_lines.append(tc.get("summary", ""))
                md_lines.append("\n## Definition")
                md_lines.append(tc.get("definition", ""))
                md_lines.append("\n## Purpose")
                md_lines.append(tc.get("purpose", ""))
                
                md_lines.append("\n## Key Properties")
                for prop in tc.get("key_properties", []):
                    md_lines.append(f"- {prop}")
                    
                md_lines.append("\n## Benefits")
                for b in tc.get("benefits", []):
                    md_lines.append(f"- {b}")
                    
                md_lines.append("\n## Limitations")
                for l in tc.get("limitations", []):
                    md_lines.append(f"- {l}")
                    
                md_lines.append("\n## Common Misconceptions")
                for m in tc.get("common_misconceptions", []):
                    md_lines.append(f"- {m}")
                    
                md_lines.append("\n## Related Topics")
                for r in tc.get("related_topics", []):
                    md_lines.append(f"- {r}")

                md_lines.append("\n## References & Citations")
                used_source_ids = topic_contents[0].sources_used
                if used_source_ids:
                    used_sources = [s for s in sources if s.id in used_source_ids]
                    for idx, src in enumerate(used_sources, 1):
                        if src.url:
                            md_lines.append(f"{idx}. [{src.title}]({src.url})")
                        else:
                            md_lines.append(f"{idx}. {src.title} *(Local Document: {src.local_path})*")
                else:
                    md_lines.append("*No references used.*")
                    
                full_markdown = "\n".join(md_lines)
                
                st.markdown("### Rendered Page Preview")
                st.markdown(full_markdown)
                
                st.markdown("### Copy Raw Markdown Source")
                st.code(full_markdown, language="markdown")

            # Human-in-the-Loop Review form
            st.markdown("---")
            st.subheader("✍️ Human-in-the-Loop Review Workspace")
            
            st.info(f"Current Review Status: **{topic_contents[0].review_status.upper()}** | Reviewer: **{topic_contents[0].reviewer_id or 'None'}**")
            
            with st.form("hil_review_form"):
                st.markdown("### Edit Curriculum Markdown")
                ed_summary = st.text_area("Summary", value=tc.get("summary", ""), height=100)
                ed_definition = st.text_area("Definition", value=tc.get("definition", ""), height=100)
                ed_purpose = st.text_area("Purpose", value=tc.get("purpose", ""), height=80)
                
                ed_properties = st.text_area("Key Properties (one per line)", value="\n".join(tc.get("key_properties", [])), height=100)
                ed_benefits = st.text_area("Benefits (one per line)", value="\n".join(tc.get("benefits", [])), height=100)
                ed_limitations = st.text_area("Limitations (one per line)", value="\n".join(tc.get("limitations", [])), height=100)
                ed_misconceptions = st.text_area("Common Misconceptions (one per line)", value="\n".join(tc.get("common_misconceptions", [])), height=100)
                ed_related = st.text_area("Related Topics (one per line)", value="\n".join(tc.get("related_topics", [])), height=100)
                
                st.markdown("### Review Notes & Decisions")
                notes = st.text_input("Reviewer Notes / Feedback", value=topic_contents[0].review_notes or "")
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    approve_btn = st.form_submit_button("✅ Approve Content")
                with c2:
                    save_btn = st.form_submit_button("💾 Save Custom Edits")
                with c3:
                    reject_btn = st.form_submit_button("❌ Request Regeneration")
                    
                if approve_btn or save_btn or reject_btn:
                    updated_content_json = {
                        "topic_name": tc.get("topic_name", ""),
                        "summary": ed_summary,
                        "definition": ed_definition,
                        "purpose": ed_purpose,
                        "key_properties": [x.strip() for x in ed_properties.split("\n") if x.strip()],
                        "benefits": [x.strip() for x in ed_benefits.split("\n") if x.strip()],
                        "limitations": [x.strip() for x in ed_limitations.split("\n") if x.strip()],
                        "common_misconceptions": [x.strip() for x in ed_misconceptions.split("\n") if x.strip()],
                        "related_topics": [x.strip() for x in ed_related.split("\n") if x.strip()]
                    }
                    
                    if approve_btn:
                        new_review_status = ReviewStatus.approved
                        new_topic_status = ProcessingStatus.completed
                    elif reject_btn:
                        new_review_status = ReviewStatus.rejected
                        new_topic_status = ProcessingStatus.pending
                    else:
                        new_review_status = ReviewStatus.pending
                        new_topic_status = ProcessingStatus.pending
                        
                    import datetime
                    now = datetime.datetime.now(datetime.timezone.utc)
                    
                    content_row = topic_contents[0]
                    updated_content_row = content_row.model_copy(
                        update={
                            "content_json": updated_content_json,
                            "review_status": new_review_status,
                            "reviewer_id": "human_editor",
                            "reviewed_at": now,
                            "review_notes": notes,
                        }
                    )
                    
                    selected_topic = [t for t in topics if t.id == selected_topic_id][0]
                    updated_topic_row = selected_topic.model_copy(
                        update={
                            "status": new_topic_status,
                            "updated_at": now,
                        }
                    )
                    
                    try:
                        content_tbl = get_table("topic_content", TopicContent, settings)
                        content_tbl.write([updated_content_row])
                        
                        topics_tbl = get_table("syllabus_topics", SyllabusTopic, settings)
                        topics_tbl.write([updated_topic_row])
                        
                        st.success(f"Changes saved successfully! Review Status set to {new_review_status.upper()}.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error saving modifications: {exc}")
        else:
            st.info("Content has not been generated for this topic yet.")

with tab3:
    st.header("🗂️ Topic Management")
    action = st.radio("Action", ["Add Topic", "Update Topic", "Remove Topic"], horizontal=True)
    
    if action == "Add Topic":
        with st.form("add_topic_form"):
            st.markdown("### Register New Syllabus Topic")
            new_sn = st.number_input("Topic Serial Number (int)", min_value=1, max_value=200, value=len(topics)+1)
            new_chapter = st.text_input("Chapter (e.g., Chapter 1 or Chapter 2)", value="Chapter 1")
            new_name = st.text_input("Topic Name / Title", placeholder="e.g., 1.5 CI/CD Overview")
            new_type = st.selectbox("Topic Type", ["concept", "command", "tool", "architecture", "process"])
            new_keywords_str = st.text_input("Keywords (comma separated)", placeholder="ci-cd, pipeline, build")
            new_difficulty = st.selectbox("Difficulty Level", ["Beginner", "Intermediate", "Advanced"])
            
            submit_add = st.form_submit_button("➕ Add Topic to Syllabus")
            
            if submit_add:
                if not new_name:
                    st.error("Topic Name is required.")
                else:
                    from edu_curator.cli import _topic_uuid
                    topic_id = _topic_uuid(int(new_sn))
                    keywords = [k.strip() for k in new_keywords_str.split(",") if k.strip()]
                    import datetime
                    now = datetime.datetime.now(datetime.timezone.utc)
                    
                    new_topic = SyllabusTopic(
                        id=topic_id,
                        chapter=new_chapter,
                        topic_name=new_name,
                        topic_type=TopicType(new_type),
                        keywords=keywords,
                        difficulty_level=new_difficulty,
                        status=ProcessingStatus.pending,
                        created_at=now,
                        updated_at=now
                    )
                    
                    try:
                        topics_tbl = get_table("syllabus_topics", SyllabusTopic, settings)
                        topics_tbl.write([new_topic])
                        st.success(f"Successfully added topic: **{new_name}**")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding topic: {e}")
                        
    elif action == "Update Topic":
        if not topics:
            st.info("No topics available to update.")
        else:
            topic_options = {f"SN {t.topic_name}": t for t in topics}
            selected_topic_label = st.selectbox("Select Topic to Update", list(topic_options.keys()))
            t_to_update = topic_options[selected_topic_label]
            
            with st.form("update_topic_form"):
                st.markdown(f"### Update Topic ID: `{t_to_update.id}`")
                up_chapter = st.text_input("Chapter", value=t_to_update.chapter)
                up_name = st.text_input("Topic Name / Title", value=t_to_update.topic_name)
                up_type = st.selectbox("Topic Type", ["concept", "command", "tool", "architecture", "process"], index=["concept", "command", "tool", "architecture", "process"].index(t_to_update.topic_type))
                up_keywords_str = st.text_input("Keywords (comma separated)", value=", ".join(t_to_update.keywords))
                
                diff_list = ["Beginner", "Intermediate", "Advanced"]
                diff_idx = diff_list.index(t_to_update.difficulty_level) if t_to_update.difficulty_level in diff_list else 0
                up_difficulty = st.selectbox("Difficulty Level", diff_list, index=diff_idx)
                up_status = st.selectbox("Processing Status", ["pending", "processing", "completed", "failed"], index=["pending", "processing", "completed", "failed"].index(t_to_update.status))
                
                submit_update = st.form_submit_button("💾 Save Topic Updates")
                
                if submit_update:
                    keywords = [k.strip() for k in up_keywords_str.split(",") if k.strip()]
                    import datetime
                    updated_topic = t_to_update.model_copy(
                        update={
                            "chapter": up_chapter,
                            "topic_name": up_name,
                            "topic_type": TopicType(up_type),
                            "keywords": keywords,
                            "difficulty_level": up_difficulty,
                            "status": ProcessingStatus(up_status),
                            "updated_at": datetime.datetime.now(datetime.timezone.utc)
                        }
                    )
                    try:
                        topics_tbl = get_table("syllabus_topics", SyllabusTopic, settings)
                        topics_tbl.write([updated_topic])
                        st.success(f"Successfully updated topic: **{up_name}**")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating topic: {e}")
                        
    elif action == "Remove Topic":
        if not topics:
            st.info("No topics available.")
        else:
            topic_options = {f"{t.chapter} - {t.topic_name}": t for t in topics}
            selected_topic_label = st.selectbox("Select Topic to Remove", list(topic_options.keys()))
            t_to_remove = topic_options[selected_topic_label]
            
            st.warning(f"Are you sure you want to remove the topic: **{t_to_remove.topic_name}**?")
            confirm_delete = st.button("🗑️ Yes, Delete Topic")
            
            if confirm_delete:
                try:
                    topics_tbl = get_table("syllabus_topics", SyllabusTopic, settings)
                    if hasattr(topics_tbl, "supabase") and topics_tbl.supabase:
                        topics_tbl.supabase.table("syllabus_topics").delete().eq("id", t_to_remove.id).execute()
                    else:
                        current = topics_tbl.read()
                        remaining = [t for t in current if t.id != t_to_remove.id]
                        topics_tbl.write(remaining)
                    st.success(f"Successfully deleted topic: **{t_to_remove.topic_name}**")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error removing topic: {e}")

with tab4:
    st.header("🔌 Source Ingest & Auto-Normalization")
    source_mode = st.radio("Source Type", ["Website URL", "Document File (PDF/Image)"], horizontal=True)
    
    if not topics:
        st.warning("Please add syllabus topics before adding sources.")
    else:
        topic_options = {f"{t.chapter} - {t.topic_name}": t.id for t in topics}
        selected_topics = st.multiselect("Map Source to Syllabus Topic(s)", list(topic_options.keys()))
        mapped_topic_ids = [topic_options[label] for label in selected_topics]
        trust_score = st.slider("Source Trust Score (1-10)", min_value=1, max_value=10, value=8)
        
        if source_mode == "Website URL":
            with st.form("url_source_form"):
                st.markdown("### Add Web Source")
                src_title = st.text_input("Source Title / Description", placeholder="e.g., AWS: What is CI/CD?")
                src_url = st.text_input("Source URL", placeholder="https://aws.amazon.com/devops/what-is-ci-cd/")
                submit_url = st.form_submit_button("⚡ Ingest & Process Web Source")
                
                if submit_url:
                    if not src_title or not src_url:
                        st.error("Title and URL are required.")
                    elif not mapped_topic_ids:
                        st.error("Please select at least one syllabus topic mapping.")
                    else:
                        source_id = new_id()
                        new_src = Source(
                            id=source_id,
                            title=src_title,
                            source_type=SourceType.website,
                            url=src_url,
                            trust_score=trust_score,
                            topic_ids=mapped_topic_ids,
                            created_at=datetime.datetime.now(datetime.timezone.utc)
                        )
                        try:
                            sources_tbl = get_table("sources", Source, settings)
                            sources_tbl.write([new_src])
                            st.info("Source registered. Normalizing and chunking text content...")
                            
                            from edu_curator.ingest import normalize_source
                            updated, doc = normalize_source(new_src, ROOT)
                            sources_tbl.write([updated])
                            
                            doc_tbl = get_table("documents", NormalizedDocument, settings)
                            doc_tbl.write([doc])
                            
                            from edu_curator.chunking import word_chunks
                            chunks = word_chunks(doc, chunk_size=800, overlap=100)
                            chunks_tbl = get_table("content_chunks", ContentChunk, settings)
                            chunks_tbl.write(chunks)
                            
                            st.success(f"Successfully processed: **{src_title}**! Created {len(chunks)} text chunks.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ingestion failed: {e}")
                            
        elif source_mode == "Document File (PDF/Image)":
            uploaded_file = st.file_uploader("Upload PDF File or Image (for OCR)", type=["pdf", "png", "jpg", "jpeg", "webp"])
            if uploaded_file is not None:
                src_title = st.text_input("Source Title / Description", value=uploaded_file.name.split(".")[0].replace("_", " "))
                submit_file = st.button("⚡ Ingest & Process Uploaded File")
                
                if submit_file:
                    if not mapped_topic_ids:
                        st.error("Please select at least one syllabus topic mapping.")
                    else:
                        uploads_dir = ROOT / "data" / "uploads"
                        uploads_dir.mkdir(parents=True, exist_ok=True)
                        save_path = uploads_dir / uploaded_file.name
                        save_path.write_bytes(uploaded_file.getvalue())
                        
                        rel_path = f"data/uploads/{uploaded_file.name}"
                        source_id = new_id()
                        
                        ext = Path(uploaded_file.name).suffix.lower()
                        if ext == ".pdf":
                            source_type = SourceType.pdf
                        elif ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}:
                            source_type = SourceType.image
                        else:
                            source_type = SourceType.website

                        new_src = Source(
                            id=source_id,
                            title=src_title,
                            source_type=source_type,
                            local_path=rel_path,
                            trust_score=trust_score,
                            topic_ids=mapped_topic_ids,
                            created_at=datetime.datetime.now(datetime.timezone.utc)
                        )
                        try:
                            sources_tbl = get_table("sources", Source, settings)
                            sources_tbl.write([new_src])
                            st.info("Processing document layout/OCR and chunking...")
                            
                            from edu_curator.ingest import normalize_source
                            updated, doc = normalize_source(new_src, ROOT)
                            sources_tbl.write([updated])
                            
                            doc_tbl = get_table("documents", NormalizedDocument, settings)
                            doc_tbl.write([doc])
                            
                            from edu_curator.chunking import word_chunks
                            chunks = word_chunks(doc, chunk_size=800, overlap=100)
                            chunks_tbl = get_table("content_chunks", ContentChunk, settings)
                            chunks_tbl.write(chunks)
                            
                            st.success(f"Successfully processed local document: **{uploaded_file.name}**! Created {len(chunks)} chunks.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ingestion failed: {e}")

with tab5:
    st.header("Sources")
    if sources:
        sources_df = pd.DataFrame([s.model_dump() for s in sources])
        st.dataframe(sources_df[['title', 'source_type', 'trust_score', 'url']], use_container_width=True)
    else:
        st.info("No sources found.")

with tab6:
    st.header("💰 LLM Token Usage & Cost Observability")
    
    from edu_curator.token_logger import summarise_usage
    with st.spinner("Analyzing token usage records..."):
        summary = summarise_usage(ROOT / "data" / "logs")
        
    if summary["total_calls"] == 0:
        st.info("No token usage records found in Supabase or local logs. Run a topic pipeline first!")
    else:
        # Standard rate card for Cerebras Llama completions
        rate_prompt = 0.15 / 1_000_000      # $0.15 per 1M prompt tokens
        rate_completion = 0.60 / 1_000_000  # $0.60 per 1M completion tokens
        est_cost = (summary["total_prompt"] * rate_prompt) + (summary["total_completion"] * rate_completion)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total API Calls", f"{summary['total_calls']:,}")
        c2.metric("Total Tokens Used", f"{summary['total_tokens']:,}")
        c3.metric("Prompt / Completion Split", f"{summary['total_prompt']:,} / {summary['total_completion']:,}")
        c4.metric("Estimated API Cost", f"${est_cost:.4f}", help="Estimated using typical rate of $0.15/1M input, $0.60/1M output tokens")
        
        st.subheader("Usage Breakdown by Pipeline Stage")
        stage_rows = []
        for stage, data in summary["by_stage"].items():
            stage_rows.append({
                "Stage": stage,
                "Calls": data["calls"],
                "Prompt Tokens": data["prompt"],
                "Completion Tokens": data["completion"],
                "Total Tokens": data["total"],
                "Est. Cost ($)": f"${(data['prompt'] * rate_prompt) + (data['completion'] * rate_completion):.5f}"
            })
        st.dataframe(pd.DataFrame(stage_rows), use_container_width=True)
        
        st.subheader("Usage Breakdown by Model & Topic")
        col_m, col_t = st.columns(2)
        
        with col_m:
            st.markdown("**By Model**")
            model_rows = []
            for model, data in summary["by_model"].items():
                model_rows.append({
                    "Model": model,
                    "Calls": data["calls"],
                    "Total Tokens": data["total"]
                })
            st.dataframe(pd.DataFrame(model_rows), use_container_width=True)
            
        with col_t:
            st.markdown("**By Topic Serial Number**")
            topic_rows = []
            for sn, data in summary["by_topic_sn"].items():
                topic_rows.append({
                    "Topic SN": sn,
                    "Calls": data["calls"],
                    "Total Tokens": data["total"]
                })
            st.dataframe(pd.DataFrame(topic_rows), use_container_width=True)

        # Traces Viewer Section
        st.markdown("---")
        st.subheader("🕵️ LLM Request & Latency Traces")
        
        @st.cache_data(ttl=15)
        def fetch_traces():
            import json
            loaded = False
            records = []
            try:
                if settings.supabase_url and settings.supabase_key:
                    from supabase import create_client
                    supabase = create_client(settings.supabase_url, settings.supabase_key)
                    # Limit to last 50 traces
                    response = supabase.table("llm_traces").select("*").order("ts", desc=True).limit(50).execute()
                    records = response.data
                    loaded = True
            except Exception as exc:
                pass
                
            if not loaded:
                trace_path = ROOT / "data" / "logs" / "llm_traces.jsonl"
                if trace_path.exists():
                    with open(trace_path, encoding="utf-8") as fh:
                        for line in fh:
                            if line.strip():
                                try:
                                    records.append(json.loads(line))
                                except:
                                    pass
                    records.sort(key=lambda x: x.get("ts", ""), reverse=True)
                    records = records[:50]
            return records

        with st.spinner("Loading LLM traces..."):
            traces = fetch_traces()

        if not traces:
            st.info("No LLM traces found. Run the extraction or content generation pipeline to capture API traces.")
        else:
            traces_df = pd.DataFrame([
                {
                    "ID": t.get("id"),
                    "Time": t.get("ts"),
                    "Stage": t.get("stage"),
                    "Topic SN": t.get("topic_sn"),
                    "Model": t.get("model"),
                    "Latency (ms)": t.get("latency_ms"),
                    "Tokens": t.get("total_tokens")
                }
                for t in traces
            ])
            st.dataframe(traces_df, use_container_width=True)
            
            selected_trace_id = st.selectbox("Select Trace ID to inspect details", [t.get("id") for t in traces])
            selected_trace = [t for t in traces if t.get("id") == selected_trace_id][0]
            
            col_p, col_r = st.columns(2)
            with col_p:
                st.markdown("**Prompt Messages**")
                for msg in selected_trace.get("prompt", []):
                    role = msg.get("role", "user")
                    with st.chat_message(role):
                        st.write(msg.get("content", ""))
            with col_r:
                st.markdown("**LLM JSON Response**")
                st.code(selected_trace.get("response", ""), language="json")
