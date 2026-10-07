-- ReliefLink Stage 4: staff roles and department setup.
-- Run once in relief_db after the Stage 3 migration and before staff setup.

INSERT INTO department (name)
VALUES ('Logistics'), ('Warehouse'), ('Camp Relief'), ('Donations')
ON CONFLICT (name) DO NOTHING;

ALTER TABLE user_account
    ALTER COLUMN security_pin_hash DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS user_account_username_ci_idx
    ON user_account (lower(username));

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'user_account'::regclass
           AND conname = 'user_account_department_role_check'
    ) THEN
        ALTER TABLE user_account
            ADD CONSTRAINT user_account_department_role_check
            CHECK (
                (role = 'Staff' AND department_id IS NOT NULL)
                OR (role IN ('User', 'Admin') AND department_id IS NULL)
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'user_account'::regclass
           AND conname = 'user_account_role_pin_check'
    ) THEN
        ALTER TABLE user_account
            ADD CONSTRAINT user_account_role_pin_check
            CHECK (role = 'User' OR security_pin_hash IS NOT NULL);
    END IF;
END;
$$;
