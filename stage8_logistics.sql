-- ReliefLink Stage 8: transaction-safe same-region shipment allocation.
-- Run once after stage7_requests.sql.

CREATE INDEX IF NOT EXISTS request_status_priority_time_idx
    ON request (status, priority, request_date, request_id);
CREATE INDEX IF NOT EXISTS shipment_status_dispatch_time_idx
    ON shipment (status, dispatch_date DESC);
CREATE INDEX IF NOT EXISTS shipment_request_idx
    ON shipment (request_id);
CREATE INDEX IF NOT EXISTS shipment_warehouse_idx
    ON shipment (warehouse_id);
CREATE INDEX IF NOT EXISTS shipment_item_resource_idx
    ON shipment_item (resource_id);
CREATE INDEX IF NOT EXISTS request_item_resource_idx
    ON request_item (resource_id);
CREATE INDEX IF NOT EXISTS warehouse_region_idx
    ON warehouse (region_id);
CREATE INDEX IF NOT EXISTS inventory_resource_idx
    ON inventory (resource_id);
CREATE INDEX IF NOT EXISTS activity_log_time_idx
    ON activity_log (logged_at DESC);

-- Allocate one pending request from a warehouse in its camp's affected region.
-- The request row and each inventory row are locked until the calling
-- transaction commits. Shipment-item triggers decrement stock and raise
-- low-stock alerts; request triggers update status and append status history.
CREATE OR REPLACE PROCEDURE auto_allocate(
    IN p_request_id INTEGER,
    IN p_warehouse_id INTEGER,
    IN p_vehicle_id INTEGER,
    IN p_driver_id INTEGER,
    IN p_actor_id INTEGER,
    INOUT p_shipment_id INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_role TEXT;
    v_active BOOLEAN;
    v_department TEXT;
    v_request_status TEXT;
    v_region_id INTEGER;
    v_new_shipment_id INTEGER;
    v_item RECORD;
    v_available NUMERIC(14, 3);
BEGIN
    SELECT u.role, u.is_active, d.name
      INTO v_role, v_active, v_department
      FROM user_account AS u
      LEFT JOIN department AS d USING (department_id)
     WHERE u.user_id = p_actor_id;

    IF NOT FOUND OR NOT v_active
       OR NOT (v_role = 'Admin' OR (v_role = 'Staff' AND v_department = 'Logistics')) THEN
        RAISE EXCEPTION 'You do not have permission.'
            USING ERRCODE = '42501';
    END IF;

    SELECT q.status, c.region_id
      INTO v_request_status, v_region_id
      FROM request AS q
      JOIN camp AS c USING (camp_id)
     WHERE q.request_id = p_request_id
     FOR UPDATE OF q;

    IF NOT FOUND OR v_request_status <> 'Pending' THEN
        RAISE EXCEPTION 'This request is no longer pending.'
            USING ERRCODE = 'P0001';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM warehouse
         WHERE warehouse_id = p_warehouse_id AND region_id = v_region_id
    ) THEN
        RAISE EXCEPTION 'Choose a warehouse in the affected place.'
            USING ERRCODE = 'P0001';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM request_item WHERE request_id = p_request_id) THEN
        RAISE EXCEPTION 'This request has no supply items.'
            USING ERRCODE = 'P0001';
    END IF;

    -- Lock resources in stable order so concurrent dispatchers serialize.
    FOR v_item IN
        SELECT resource_id, quantity
          FROM request_item
         WHERE request_id = p_request_id
         ORDER BY resource_id
    LOOP
        SELECT quantity
          INTO v_available
          FROM inventory
         WHERE warehouse_id = p_warehouse_id
           AND resource_id = v_item.resource_id
         FOR UPDATE;

        IF NOT FOUND OR v_available < v_item.quantity THEN
            RAISE EXCEPTION 'Insufficient stock for resource % in this warehouse.',
                v_item.resource_id
                USING ERRCODE = 'P0001';
        END IF;
    END LOOP;

    PERFORM set_config('relieflink.user_id', p_actor_id::TEXT, TRUE);

    INSERT INTO shipment
        (request_id, warehouse_id, vehicle_id, driver_id, status)
    VALUES
        (p_request_id, p_warehouse_id, p_vehicle_id, p_driver_id, 'Dispatched')
    RETURNING shipment_id INTO v_new_shipment_id;

    INSERT INTO shipment_item (shipment_id, resource_id, quantity)
    SELECT v_new_shipment_id, resource_id, quantity
      FROM request_item
     WHERE request_id = p_request_id
     ORDER BY resource_id;

    p_shipment_id := v_new_shipment_id;
END;
$$;
