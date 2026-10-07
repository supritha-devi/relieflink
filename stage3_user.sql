-- ReliefLink Stage 3 database migration.
-- Run once in pgAdmin's relief_db Query Tool before using registration/login.
-- Safe for the Stage 1 database whether or not stage2_auth.sql was applied.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Normal Users use password login and have no security PIN.
ALTER TABLE user_account
    ALTER COLUMN security_pin_hash DROP NOT NULL;

-- Enforce a single Admin even if setup requests race.
CREATE UNIQUE INDEX IF NOT EXISTS user_account_single_admin_idx
    ON user_account (role)
    WHERE role = 'Admin';

-- Registration and login treat username/email casing consistently.
CREATE UNIQUE INDEX IF NOT EXISTS user_account_username_ci_idx
    ON user_account (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS user_account_email_ci_idx
    ON user_account (lower(email))
    WHERE email IS NOT NULL;

-- Apply the account-role rules from Stage 2 to the existing database.
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
