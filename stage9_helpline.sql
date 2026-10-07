-- ReliefLink Stage 9: secure messages, conversations and call-log access.
-- Message and call-log audit triggers were installed in the earlier migrations.

ALTER TABLE message
    ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS conversation_owner_created_idx
    ON conversation (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS conversation_open_created_idx
    ON conversation (status, created_at DESC);
CREATE INDEX IF NOT EXISTS message_conversation_sent_idx
    ON message (conversation_id, sent_at, message_id);
CREATE INDEX IF NOT EXISTS call_log_called_at_idx
    ON call_log (called_at DESC);
CREATE INDEX IF NOT EXISTS call_log_region_idx
    ON call_log (region_id);
