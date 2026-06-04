-- Create the submit_review RPC function to execute the updates under a single database transaction.
CREATE OR REPLACE FUNCTION submit_review(
    p_topic_id UUID,
    p_content_id UUID,
    p_review_status TEXT,
    p_reviewer_id TEXT,
    p_review_notes TEXT,
    p_edited_content JSONB,
    p_raw_content JSONB,
    p_version INTEGER
) RETURNS TEXT AS $$
DECLARE
    v_current_version INTEGER;
    v_field RECORD;
    v_edited_val JSONB;
    v_raw_val JSONB;
    v_merged_content JSONB;
BEGIN
    -- 1. Optimistic Concurrency Control (OCC) Check
    SELECT version INTO v_current_version FROM topic_content WHERE id = p_content_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Content row not found for ID %', p_content_id USING ERRCODE = 'P0002';
    END IF;
    
    IF v_current_version IS DISTINCT FROM p_version THEN
        RAISE EXCEPTION 'Conflict: This content has been modified by another reviewer. Current version is %, but you submitted version %.', v_current_version, p_version USING ERRCODE = 'P0001';
    END IF;

    -- 2. Process Overrides
    IF p_edited_content IS NOT NULL THEN
        FOR v_field IN SELECT * FROM jsonb_each(p_edited_content) LOOP
            v_edited_val := v_field.value;
            v_raw_val := p_raw_content -> v_field.key;
            
            -- If edited value is different from raw value
            IF v_edited_val IS DISTINCT FROM v_raw_val AND NOT (v_edited_val IS NULL AND v_raw_val IS NULL) THEN
                -- Insert or update override with is_active = true
                INSERT INTO knowledge_overrides (topic_id, field_name, original_value, corrected_value, correction_note, reviewer_id, is_active, created_at, updated_at)
                VALUES (p_topic_id, v_field.key, v_raw_val, v_edited_val, p_review_notes, p_reviewer_id, true, NOW(), NOW())
                ON CONFLICT (topic_id, field_name) WHERE is_active = true
                DO UPDATE SET
                    corrected_value = EXCLUDED.corrected_value,
                    original_value = EXCLUDED.original_value,
                    correction_note = EXCLUDED.correction_note,
                    reviewer_id = EXCLUDED.reviewer_id,
                    updated_at = NOW();
            ELSE
                -- If edited is same as raw, deactivate any active override
                UPDATE knowledge_overrides
                SET is_active = false, updated_at = NOW()
                WHERE topic_id = p_topic_id AND field_name = v_field.key AND is_active = true;
            END IF;
        END LOOP;
    END IF;

    -- 3. Construct Merged Approved Content
    v_merged_content := p_raw_content;
    IF p_review_status = 'approved' THEN
        -- Read all active overrides for this topic and merge them onto raw content
        FOR v_field IN 
            SELECT field_name, corrected_value 
            FROM knowledge_overrides 
            WHERE topic_id = p_topic_id AND is_active = true
        LOOP
            v_merged_content := jsonb_set(v_merged_content, array[v_field.field_name], v_field.corrected_value, true);
        END LOOP;
    END IF;

    -- 4. Update TopicContent
    UPDATE topic_content
    SET
        review_status = p_review_status,
        reviewer_id = p_reviewer_id,
        reviewed_at = NOW(),
        review_notes = p_review_notes,
        content_json = CASE WHEN p_review_status = 'approved' THEN v_merged_content ELSE p_raw_content END,
        published_at = CASE WHEN p_review_status = 'approved' THEN NOW() ELSE published_at END,
        version = v_current_version + 1
    WHERE id = p_content_id;

    -- 5. Update SyllabusTopic status
    UPDATE syllabus_topics
    SET
        status = CASE WHEN p_review_status = 'approved' THEN 'completed' ELSE 'pending' END,
        updated_at = NOW()
    WHERE id = p_topic_id;

    -- 6. Insert ReviewerActivity log
    INSERT INTO reviewer_activity (id, topic_id, content_id, reviewer_id, action, review_notes, created_at)
    VALUES (gen_random_uuid(), p_topic_id, p_content_id, p_reviewer_id, p_review_status, p_review_notes, NOW());

    -- 7. Queue regeneration if needed
    IF p_review_status = 'needs_regeneration' THEN
        -- Avoid queuing duplicate pending curation jobs
        INSERT INTO curation_jobs (id, topic_id, status, created_at, updated_at)
        VALUES (gen_random_uuid(), p_topic_id, 'pending', NOW(), NOW())
        ON CONFLICT (topic_id, status) WHERE status = 'pending'
        DO NOTHING;
    END IF;

    RETURN 'success';
END;
$$ LANGUAGE plpgsql;
