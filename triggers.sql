-- ReliefLink database triggers.
-- Run this file after schema.sql and before data.sql.

-- Donations add each donated resource to the selected warehouse.
CREATE OR REPLACE FUNCTION add_donation_stock()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_warehouse_id INTEGER;
BEGIN
    SELECT warehouse_id
      INTO v_warehouse_id
      FROM donation
     WHERE donation_id = NEW.donation_id;

    INSERT INTO inventory (warehouse_id, resource_id, quantity)
    VALUES (v_warehouse_id, NEW.resource_id, NEW.quantity)
    ON CONFLICT (warehouse_id, resource_id)
    DO UPDATE
          SET quantity = inventory.quantity + EXCLUDED.quantity,
              updated_at = CURRENT_TIMESTAMP;

    RETURN NEW;
END;
$$;

CREATE TRIGGER add_stock
AFTER INSERT ON donation_item
FOR EACH ROW
EXECUTE FUNCTION add_donation_stock();

-- Dispatches subtract stock atomically; an insufficient quantity aborts the insert.
CREATE OR REPLACE FUNCTION reduce_shipment_stock()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_warehouse_id INTEGER;
BEGIN
    SELECT warehouse_id
      INTO v_warehouse_id
      FROM shipment
     WHERE shipment_id = NEW.shipment_id;

    UPDATE inventory
       SET quantity = quantity - NEW.quantity,
           updated_at = CURRENT_TIMESTAMP
     WHERE warehouse_id = v_warehouse_id
       AND resource_id = NEW.resource_id
       AND quantity >= NEW.quantity;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Insufficient stock for resource % in warehouse %',
            NEW.resource_id, v_warehouse_id
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER reduce_stock
AFTER INSERT ON shipment_item
FOR EACH ROW
EXECUTE FUNCTION reduce_shipment_stock();

-- Low-stock alerts compare warehouse stock with active camps' three-day needs.
CREATE OR REPLACE FUNCTION create_low_stock_alert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_region_id INTEGER;
    v_resource_name TEXT;
    v_needed NUMERIC(20, 4);
BEGIN
    SELECT region_id
      INTO v_region_id
      FROM warehouse
     WHERE warehouse_id = NEW.warehouse_id;

    SELECT name
      INTO v_resource_name
      FROM resource
     WHERE resource_id = NEW.resource_id;

    SELECT COALESCE(
               SUM(c.population * r.daily_need_per_person * days_of_cover()),
               0
           )
      INTO v_needed
      FROM camp AS c
      JOIN disaster AS d ON d.disaster_id = c.disaster_id
      JOIN resource AS r ON r.resource_id = NEW.resource_id
     WHERE c.region_id = v_region_id
       AND c.status = 'Active'
       AND d.status = 'Active';

    IF NEW.quantity < v_needed THEN
        INSERT INTO alert (warehouse_id, resource_id, message)
        VALUES (
            NEW.warehouse_id,
            NEW.resource_id,
            format(
                'Needs %s: %s available; %s needed for %s days of active camp demand.',
                v_resource_name,
                NEW.quantity,
                v_needed,
                days_of_cover()
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER low_stock_alert
AFTER INSERT OR UPDATE OF quantity ON inventory
FOR EACH ROW
EXECUTE FUNCTION create_low_stock_alert();

-- Shipment creation advances its request; delivery advances it to Delivered.
CREATE OR REPLACE FUNCTION update_request_from_shipment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.status = 'Delivered' THEN
        UPDATE request
           SET status = CASE
                            WHEN NEW.status = 'Delivered' THEN 'Delivered'
                            ELSE 'Dispatched'
                        END
         WHERE request_id = NEW.request_id
           AND status <> CASE
                             WHEN NEW.status = 'Delivered' THEN 'Delivered'
                             ELSE 'Dispatched'
                         END;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER shipment_updates_request
AFTER INSERT OR UPDATE OF status ON shipment
FOR EACH ROW
EXECUTE FUNCTION update_request_from_shipment();

-- Important record changes are logged without copying sensitive field values.
-- The application can set relieflink.user_id transaction-locally for the actor.
CREATE OR REPLACE FUNCTION log_relief_activity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_row JSONB;
    v_record_id INTEGER;
    v_actor_id INTEGER;
BEGIN
    v_row := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    v_actor_id := NULLIF(current_setting('relieflink.user_id', TRUE), '')::INTEGER;

    CASE TG_TABLE_NAME
        WHEN 'request' THEN
            v_record_id := (v_row ->> 'request_id')::INTEGER;
            v_actor_id := COALESCE(v_actor_id, (v_row ->> 'requested_by')::INTEGER);
        WHEN 'donation' THEN
            v_record_id := (v_row ->> 'donation_id')::INTEGER;
            IF v_actor_id IS NULL THEN
                SELECT user_id INTO v_actor_id
                  FROM donor
                 WHERE donor_id = (v_row ->> 'donor_id')::INTEGER;
            END IF;
        WHEN 'shipment' THEN
            v_record_id := (v_row ->> 'shipment_id')::INTEGER;
        WHEN 'message' THEN
            v_record_id := (v_row ->> 'message_id')::INTEGER;
            v_actor_id := COALESCE(v_actor_id, (v_row ->> 'sender_user_id')::INTEGER);
        WHEN 'call_log' THEN
            v_record_id := (v_row ->> 'call_id')::INTEGER;
            v_actor_id := COALESCE(v_actor_id, (v_row ->> 'logged_by')::INTEGER);
        WHEN 'user_account' THEN
            v_record_id := (v_row ->> 'user_id')::INTEGER;
        WHEN 'helpline' THEN
            v_record_id := (v_row ->> 'helpline_id')::INTEGER;
        WHEN 'disaster_area' THEN
            v_record_id := (v_row ->> 'disaster_id')::INTEGER;
        ELSE
            RAISE EXCEPTION 'Activity logging is not configured for table %', TG_TABLE_NAME;
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

CREATE TRIGGER log_request_activity
AFTER INSERT OR UPDATE OR DELETE ON request
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_donation_activity
AFTER INSERT OR UPDATE OR DELETE ON donation
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_shipment_activity
AFTER INSERT OR UPDATE OR DELETE ON shipment
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_message_activity
AFTER INSERT OR UPDATE OR DELETE ON message
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_call_activity
AFTER INSERT OR UPDATE OR DELETE ON call_log
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_user_account_activity
AFTER INSERT OR UPDATE OR DELETE ON user_account
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_helpline_activity
AFTER INSERT OR UPDATE OR DELETE ON helpline
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();

CREATE TRIGGER log_disaster_area_activity
AFTER INSERT OR UPDATE OR DELETE ON disaster_area
FOR EACH ROW EXECUTE FUNCTION log_relief_activity();
