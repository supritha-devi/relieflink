-- Clearly marked demonstration data. Confirm all phone numbers before public use.
-- Run this file after schema.sql and triggers.sql.

BEGIN;

INSERT INTO department (name)
VALUES ('Logistics'), ('Warehouse'), ('Camp Relief'), ('Donations')
ON CONFLICT (name) DO NOTHING;

INSERT INTO disaster
    (name, type, severity, description, start_date, status)
VALUES
    ('SAMPLE - Monsoon Flood', 'Flood', 'High',
     'Demonstration flood scenario; replace with verified incident information.',
     CURRENT_DATE - 3, 'Active'),
    ('SAMPLE - Coastal Cyclone', 'Cyclone', 'Moderate',
     'Demonstration cyclone scenario; replace with verified incident information.',
     CURRENT_DATE - 1, 'Active')
ON CONFLICT (name) DO NOTHING;

INSERT INTO region (name, district, state)
VALUES
    ('SAMPLE - Riverbend', 'SAMPLE - North District', 'SAMPLE - State'),
    ('SAMPLE - Lowland', 'SAMPLE - North District', 'SAMPLE - State'),
    ('SAMPLE - Eastfield', 'SAMPLE - Coastal District', 'SAMPLE - State'),
    ('SAMPLE - Hillview', 'SAMPLE - Coastal District', 'SAMPLE - State')
ON CONFLICT (name, district) DO NOTHING;

INSERT INTO disaster_area (disaster_id, region_id)
SELECT d.disaster_id, r.region_id
  FROM (VALUES
        ('SAMPLE - Monsoon Flood', 'SAMPLE - Riverbend', 'SAMPLE - North District'),
        ('SAMPLE - Monsoon Flood', 'SAMPLE - Lowland', 'SAMPLE - North District'),
        ('SAMPLE - Coastal Cyclone', 'SAMPLE - Eastfield', 'SAMPLE - Coastal District'),
        ('SAMPLE - Coastal Cyclone', 'SAMPLE - Hillview', 'SAMPLE - Coastal District')
       ) AS sample(disaster_name, region_name, district_name)
  JOIN disaster AS d ON d.name = sample.disaster_name
  JOIN region AS r
    ON r.name = sample.region_name AND r.district = sample.district_name
ON CONFLICT (disaster_id, region_id) DO NOTHING;

INSERT INTO camp (disaster_id, region_id, name, population)
SELECT d.disaster_id, r.region_id, sample.camp_name, sample.population
  FROM (VALUES
        ('SAMPLE - Monsoon Flood', 'SAMPLE - Riverbend', 'SAMPLE - Riverside Camp', 220),
        ('SAMPLE - Monsoon Flood', 'SAMPLE - Riverbend', 'SAMPLE - Bridge Camp', 180),
        ('SAMPLE - Monsoon Flood', 'SAMPLE - Lowland', 'SAMPLE - School Camp', 150),
        ('SAMPLE - Monsoon Flood', 'SAMPLE - Lowland', 'SAMPLE - Market Camp', 130),
        ('SAMPLE - Coastal Cyclone', 'SAMPLE - Eastfield', 'SAMPLE - Harbor Camp', 260),
        ('SAMPLE - Coastal Cyclone', 'SAMPLE - Hillview', 'SAMPLE - Ridge Camp', 190)
       ) AS sample(disaster_name, region_name, camp_name, population)
  JOIN disaster AS d ON d.name = sample.disaster_name
  JOIN region AS r ON r.name = sample.region_name
ON CONFLICT (disaster_id, region_id, name) DO NOTHING;

INSERT INTO resource (name, category, unit, daily_need_per_person)
VALUES
    ('Water', 'Essential', 'liters', 3.0000),
    ('Food', 'Essential', 'packets', 2.0000),
    ('Medicine', 'Medical', 'kits', 0.0500),
    ('Blankets', 'Shelter', 'blankets', 0.0200)
ON CONFLICT (name) DO NOTHING;

INSERT INTO warehouse (region_id, name, capacity)
SELECT r.region_id, sample.warehouse_name, sample.capacity
  FROM (VALUES
        ('SAMPLE - Riverbend', 'SAMPLE - Riverbend Relief Warehouse', 50000::NUMERIC),
        ('SAMPLE - Lowland', 'SAMPLE - Lowland Relief Warehouse', 40000::NUMERIC),
        ('SAMPLE - Eastfield', 'SAMPLE - Eastfield Relief Warehouse', 45000::NUMERIC)
       ) AS sample(region_name, warehouse_name, capacity)
  JOIN region AS r ON r.name = sample.region_name
ON CONFLICT (region_id, name) DO NOTHING;

-- These quantities exceed three days of active camp needs in each warehouse region.
INSERT INTO inventory (warehouse_id, resource_id, quantity)
SELECT w.warehouse_id, r.resource_id, sample.quantity
  FROM (VALUES
        ('SAMPLE - Riverbend Relief Warehouse', 'Water', 5000::NUMERIC),
        ('SAMPLE - Riverbend Relief Warehouse', 'Food', 3000::NUMERIC),
        ('SAMPLE - Riverbend Relief Warehouse', 'Medicine', 90::NUMERIC),
        ('SAMPLE - Riverbend Relief Warehouse', 'Blankets', 60::NUMERIC),
        ('SAMPLE - Lowland Relief Warehouse', 'Water', 2800::NUMERIC),
        ('SAMPLE - Lowland Relief Warehouse', 'Food', 2000::NUMERIC),
        ('SAMPLE - Lowland Relief Warehouse', 'Medicine', 50::NUMERIC),
        ('SAMPLE - Lowland Relief Warehouse', 'Blankets', 30::NUMERIC),
        ('SAMPLE - Eastfield Relief Warehouse', 'Water', 2500::NUMERIC),
        ('SAMPLE - Eastfield Relief Warehouse', 'Food', 1800::NUMERIC),
        ('SAMPLE - Eastfield Relief Warehouse', 'Medicine', 50::NUMERIC),
        ('SAMPLE - Eastfield Relief Warehouse', 'Blankets', 30::NUMERIC)
       ) AS sample(warehouse_name, resource_name, quantity)
  JOIN warehouse AS w ON w.name = sample.warehouse_name
  JOIN resource AS r ON r.name = sample.resource_name
ON CONFLICT (warehouse_id, resource_id) DO NOTHING;

INSERT INTO vehicle (plate_no, type, capacity)
VALUES
    ('SAMPLE-RELIEF-01', 'Truck', 5000),
    ('SAMPLE-RELIEF-02', 'Van', 1500)
ON CONFLICT (plate_no) DO NOTHING;

INSERT INTO driver (name, phone, license_no)
VALUES
    ('SAMPLE - Driver One', 'SAMPLE - verify before use', 'SAMPLE-LICENSE-001'),
    ('SAMPLE - Driver Two', 'SAMPLE - verify before use', 'SAMPLE-LICENSE-002')
ON CONFLICT (license_no) DO NOTHING;

INSERT INTO volunteer (camp_id, name, role, phone)
SELECT c.camp_id, sample.volunteer_name, sample.volunteer_role, 'SAMPLE - verify before use'
  FROM (VALUES
        ('SAMPLE - Riverside Camp', 'SAMPLE - Volunteer One', 'Distribution'),
        ('SAMPLE - School Camp', 'SAMPLE - Volunteer Two', 'First aid'),
        ('SAMPLE - Harbor Camp', 'SAMPLE - Volunteer Three', 'Registration'),
        ('SAMPLE - Ridge Camp', 'SAMPLE - Volunteer Four', 'Shelter support')
       ) AS sample(camp_name, volunteer_name, volunteer_role)
  JOIN camp AS c ON c.name = sample.camp_name
WHERE NOT EXISTS (
    SELECT 1 FROM volunteer AS existing
     WHERE existing.camp_id = c.camp_id AND existing.name = sample.volunteer_name
);

INSERT INTO helpline
    (name, phone_number, level, description)
SELECT sample.name, sample.phone_number, sample.level, sample.description
  FROM (VALUES
        ('SAMPLE - National emergency (verify before use)', '112', 'National',
         'Sample entry; verify the number and coverage before public use.'),
        ('SAMPLE - NDMA helpline (verify before use)', '011-1078', 'National',
         'Sample entry; verify the number and coverage before public use.'),
        ('SAMPLE - State relief control room (verify before use)', '1070', 'State',
         'Sample entry; verify the number and coverage before public use.'),
        ('SAMPLE - District control room (verify before use)', '1077', 'District',
         'Sample entry; verify the number and coverage before public use.')
       ) AS sample(name, phone_number, level, description)
 WHERE NOT EXISTS (
     SELECT 1 FROM helpline AS existing
      WHERE existing.name = sample.name
        AND existing.phone_number = sample.phone_number
        AND existing.level = sample.level
 );

INSERT INTO helpline
    (name, phone_number, level, contact_type, region_id, description)
SELECT sample.contact_name, sample.phone_number, 'Local', sample.contact_type,
       r.region_id, 'SAMPLE local contact; verify before use.'
  FROM (VALUES
        ('SAMPLE - Riverbend Relief Group', 'SAMPLE - verify before use', 'Group',
         'SAMPLE - Riverbend'),
        ('SAMPLE - Eastfield Local Coordinator', 'SAMPLE - verify before use', 'Person',
         'SAMPLE - Eastfield')
       ) AS sample(contact_name, phone_number, contact_type, region_name)
  JOIN region AS r ON r.name = sample.region_name
WHERE NOT EXISTS (
    SELECT 1
      FROM helpline AS existing
     WHERE existing.name = sample.contact_name
       AND existing.region_id = r.region_id
);

COMMIT;
