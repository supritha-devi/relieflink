-- ReliefLink Stage 6: resources, warehouses, donations and inventory updates.
-- Run once in relief_db after stage5_admin_catalog.sql.

-- One public donor profile per registered user makes repeat donations update
-- their existing profile rather than creating duplicate donor records.
CREATE UNIQUE INDEX IF NOT EXISTS donor_user_id_unique_idx
    ON donor (user_id)
    WHERE user_id IS NOT NULL;

-- Audit additions and inventory changes without storing sensitive values.
CREATE OR REPLACE FUNCTION log_stage6_activity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_row JSONB;
    v_actor_id INTEGER;
    v_record_id INTEGER;
BEGIN
    v_row := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    v_actor_id := NULLIF(current_setting('relieflink.user_id', TRUE), '')::INTEGER;

    CASE TG_TABLE_NAME
        WHEN 'resource' THEN v_record_id := (v_row ->> 'resource_id')::INTEGER;
        WHEN 'warehouse' THEN v_record_id := (v_row ->> 'warehouse_id')::INTEGER;
        WHEN 'donor' THEN
            v_record_id := (v_row ->> 'donor_id')::INTEGER;
            v_actor_id := COALESCE(v_actor_id, (v_row ->> 'user_id')::INTEGER);
        WHEN 'inventory' THEN v_record_id := (v_row ->> 'warehouse_id')::INTEGER;
        ELSE
            RAISE EXCEPTION 'Stage 6 activity logging is not configured for %',
                TG_TABLE_NAME;
    END CASE;

    INSERT INTO activity_log (user_id, action, table_name, record_id)
    VALUES (
        v_actor_id,
        lower(TG_OP) || '_' || TG_TABLE_NAME,
        TG_TABLE_NAME,
        v_record_id
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS log_resource_activity ON resource;
CREATE TRIGGER log_resource_activity
AFTER INSERT OR UPDATE OR DELETE ON resource
FOR EACH ROW EXECUTE FUNCTION log_stage6_activity();

DROP TRIGGER IF EXISTS log_warehouse_activity ON warehouse;
CREATE TRIGGER log_warehouse_activity
AFTER INSERT OR UPDATE OR DELETE ON warehouse
FOR EACH ROW EXECUTE FUNCTION log_stage6_activity();

DROP TRIGGER IF EXISTS log_donor_activity ON donor;
CREATE TRIGGER log_donor_activity
AFTER INSERT OR UPDATE OR DELETE ON donor
FOR EACH ROW EXECUTE FUNCTION log_stage6_activity();

DROP TRIGGER IF EXISTS log_inventory_activity ON inventory;
CREATE TRIGGER log_inventory_activity
AFTER INSERT OR UPDATE OR DELETE ON inventory
FOR EACH ROW EXECUTE FUNCTION log_stage6_activity();
