-- Migration: Advanced Data Integrity Fixes
-- 1. Create knowledge_override_history table
CREATE TABLE IF NOT EXISTS knowledge_override_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    override_id UUID NOT NULL,
    topic_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    reviewer_id TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Grant necessary permissions on the history table to avoid PostgREST transaction failures
GRANT ALL ON TABLE public.knowledge_override_history TO service_role;
GRANT ALL ON TABLE public.knowledge_override_history TO postgres;
GRANT ALL ON TABLE public.knowledge_override_history TO authenticated;
GRANT ALL ON TABLE public.knowledge_override_history TO anon;

-- Create indexes for performance and searchability
CREATE INDEX IF NOT EXISTS idx_override_history_override ON knowledge_override_history(override_id);
CREATE INDEX IF NOT EXISTS idx_override_history_topic ON knowledge_override_history(topic_id);

-- 2. Create history trigger function
CREATE OR REPLACE FUNCTION log_override_history_func()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO knowledge_override_history(override_id, topic_id, field_name, old_value, new_value, reviewer_id, changed_at)
        VALUES (NEW.id, NEW.topic_id, NEW.field_name, NEW.original_value, NEW.corrected_value, NEW.reviewer_id, NOW());
    ELSIF (TG_OP = 'UPDATE') THEN
        IF (OLD.corrected_value IS DISTINCT FROM NEW.corrected_value OR OLD.is_active IS DISTINCT FROM NEW.is_active) THEN
            INSERT INTO knowledge_override_history(override_id, topic_id, field_name, old_value, new_value, reviewer_id, changed_at)
            VALUES (
                NEW.id,
                NEW.topic_id,
                NEW.field_name,
                OLD.corrected_value,
                CASE WHEN NEW.is_active = FALSE THEN NULL ELSE NEW.corrected_value END,
                NEW.reviewer_id,
                NOW()
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Bind trigger to knowledge_overrides
DROP TRIGGER IF EXISTS trigger_log_override_history ON knowledge_overrides;
CREATE TRIGGER trigger_log_override_history
AFTER INSERT OR UPDATE ON knowledge_overrides
FOR EACH ROW EXECUTE FUNCTION log_override_history_func();

-- 3. Create storage deletion trigger function
CREATE OR REPLACE FUNCTION delete_storage_object_func()
RETURNS TRIGGER AS $$
DECLARE
    file_name TEXT;
BEGIN
    IF OLD.local_path IS NOT NULL AND OLD.local_path LIKE 'supabase://uploads/%' THEN
        file_name := substring(OLD.local_path from 'supabase://uploads/(.*)');
        IF file_name IS NOT NULL AND file_name != '' THEN
            -- Check if we are running in Supabase context and storage.objects exists
            IF EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'storage' AND table_name = 'objects'
            ) THEN
                DELETE FROM storage.objects WHERE bucket_id = 'uploads' AND name = file_name;
            END IF;
        END IF;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Bind trigger to sources
DROP TRIGGER IF EXISTS trigger_delete_storage_object ON sources;
CREATE TRIGGER trigger_delete_storage_object
AFTER DELETE ON sources
FOR EACH ROW EXECUTE FUNCTION delete_storage_object_func();
