-- ReliefLink Canonical SQL Views
-- Provides optimized views for pending requests, stock levels, camp shortfall, regional demand, and helpline messages.

CREATE OR REPLACE VIEW vw_pending_requests AS
SELECT
    q.request_id,
    q.priority,
    q.request_date,
    c.name AS camp_name,
    r.name AS region_name,
    r.district,
    u.name AS requested_by_user,
    COALESCE(
        string_agg(res.name || ': ' || qi.quantity, ', ' ORDER BY res.name),
        'No items'
    ) AS requested_items
FROM request q
JOIN camp c ON c.camp_id = q.camp_id
JOIN region r ON r.region_id = c.region_id
JOIN user_account u ON u.user_id = q.requested_by
LEFT JOIN request_item qi ON qi.request_id = q.request_id
LEFT JOIN resource res ON res.resource_id = qi.resource_id
WHERE q.status = 'Pending'
GROUP BY q.request_id, q.priority, q.request_date, c.name, r.name, r.district, u.name;

CREATE OR REPLACE VIEW vw_stock_summary AS
SELECT
    r.name AS region_name,
    w.warehouse_id,
    w.name AS warehouse_name,
    res.resource_id,
    res.name AS resource_name,
    res.unit,
    i.quantity AS stock_quantity
FROM inventory i
JOIN warehouse w ON w.warehouse_id = i.warehouse_id
JOIN region r ON r.region_id = w.region_id
JOIN resource res ON res.resource_id = i.resource_id;

CREATE OR REPLACE VIEW vw_camp_shortfall AS
SELECT
    c.camp_id,
    c.name AS camp_name,
    r.name AS region_name,
    c.population,
    res.resource_id,
    res.name AS resource_name,
    res.unit,
    (c.population * res.daily_need_per_person * 3) AS three_day_need,
    COALESCE(SUM(qi.quantity), 0) AS pending_quantity,
    GREATEST(0, (c.population * res.daily_need_per_person * 3) - COALESCE(SUM(qi.quantity), 0)) AS shortfall
FROM camp c
JOIN region r ON r.region_id = c.region_id
CROSS JOIN resource res
LEFT JOIN request q ON q.camp_id = c.camp_id AND q.status = 'Pending'
LEFT JOIN request_item qi ON qi.request_id = q.request_id AND qi.resource_id = res.resource_id
WHERE c.status = 'Active' AND res.daily_need_per_person > 0
GROUP BY c.camp_id, c.name, r.name, c.population, res.resource_id, res.name, res.unit, res.daily_need_per_person;

CREATE OR REPLACE VIEW vw_regional_unmet_demand AS
SELECT
    r.region_id,
    r.name AS region_name,
    res.resource_id,
    res.name AS resource_name,
    res.unit,
    COALESCE(SUM(qi.quantity), 0) AS total_unmet_quantity
FROM region r
CROSS JOIN resource res
LEFT JOIN camp c ON c.region_id = r.region_id
LEFT JOIN request q ON q.camp_id = c.camp_id AND q.status = 'Pending'
LEFT JOIN request_item qi ON qi.request_id = q.request_id AND qi.resource_id = res.resource_id
GROUP BY r.region_id, r.name, res.resource_id, res.name, res.unit;

CREATE OR REPLACE VIEW vw_open_conversations AS
SELECT
    conv.conversation_id,
    conv.created_at,
    u.user_id,
    u.name AS user_name,
    u.phone AS user_phone,
    COALESCE(c.name, 'No camp selected') AS camp_name,
    (
        SELECT m.body FROM message m
        WHERE m.conversation_id = conv.conversation_id
        ORDER BY m.sent_at DESC, m.message_id DESC LIMIT 1
    ) AS latest_message,
    (
        SELECT m.sent_at FROM message m
        WHERE m.conversation_id = conv.conversation_id
        ORDER BY m.sent_at DESC, m.message_id DESC LIMIT 1
    ) AS latest_message_time
FROM conversation conv
JOIN user_account u ON u.user_id = conv.user_id
LEFT JOIN camp c ON c.camp_id = conv.camp_id
WHERE conv.status = 'Open';
