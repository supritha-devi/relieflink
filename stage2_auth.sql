-- ReliefLink Stage 2: prepare an existing Stage 1 database for administrator
-- setup, password/PIN authentication, and future normal-user registration.
-- Run once with psql against relief_db before starting main.py.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- One Admin per database makes first-time setup safe even when two setup
-- screens are submitted at the same time.
CREATE UNIQUE INDEX IF NOT EXISTS user_account_single_admin_idx
    ON user_account (role)
    WHERE role = 'Admin';

-- Keep username and email unique even when only letter casing differs.
CREATE UNIQUE INDEX IF NOT EXISTS user_account_username_ci_idx
    ON user_account (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS user_account_email_ci_idx
    ON user_account (lower(email))
    WHERE email IS NOT NULL;

-- Normal users will authenticate with a password only. Staff and Admin still
-- need a stored PIN hash. These constraints also match the current schema.sql.
ALTER TABLE user_account
    ALTER COLUMN security_pin_hash DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'user_account'::regclass
           AND conname = 'user_account_role_pin_check'
    ) THEN
        ALTER TABLE user_account
            ADD CONSTRAINT user_account_role_pin_check
            CHECK (role = 'User' OR security_pin_hash IS NOT NULL);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'user_account'::regclass
           AND conname = 'user_account_user_email_check'
    ) THEN
        ALTER TABLE user_account
            ADD CONSTRAINT user_account_user_email_check
            CHECK (role <> 'User' OR email IS NOT NULL);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'user_account'::regclass
           AND conname = 'user_account_admin_officer_check'
    ) THEN
        ALTER TABLE user_account
            ADD CONSTRAINT user_account_admin_officer_check
            CHECK (role <> 'Admin' OR officer_id IS NOT NULL);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'user_account'::regclass
           AND conname = 'user_account_recovery_key_role_check'
    ) THEN
        ALTER TABLE user_account
            ADD CONSTRAINT user_account_recovery_key_role_check
            CHECK (role = 'Admin' OR recovery_key_hash IS NULL);
    END IF;
END;
$$;
