"""Database-backed administrator setup and authentication."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import secrets

import psycopg2
from psycopg2 import errors

from db import get_connection


ADMIN_ROLE = "Admin"
MAX_FAILED_ATTEMPTS = 3


class AuthenticationError(Exception):
    """A safe message that can be shown on an authentication page."""


@dataclass(frozen=True)
class AdminIdentity:
    """The non-secret account fields needed by the signed-in page."""

    user_id: int
    name: str
    username: str
    role: str


@dataclass(frozen=True)
class UserIdentity:
    """The non-secret account fields needed by the normal-user dashboard."""

    user_id: int
    name: str
    username: str
    role: str = "User"


@dataclass(frozen=True)
class StaffIdentity:
    """Database-verified staff identity and assigned department."""

    user_id: int
    name: str
    username: str
    department_id: int
    department_name: str
    role: str = "Staff"
    must_change_password: bool = False


def validate_username(username):
    """Allow simple usernames that are safe to display and easy to remember."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        raise ValueError("Username must be 3-32 letters, numbers, dots, dashes, or underscores.")


def validate_email(email):
    """Reject malformed addresses before they reach the unique database column."""
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address.")


def validate_password(password):
    """Require a strong password that bcrypt can hash without truncation."""
    if len(password) < 12:
        raise ValueError("Use a password with at least 12 characters.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Use a password of at most 72 UTF-8 bytes.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Include at least one lowercase letter.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Include at least one uppercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Include at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Include at least one symbol.")


def validate_pin(pin):
    """Accept a six-digit PIN and reject common repeated or sequential PINs."""
    if not re.fullmatch(r"\d{6}", pin):
        raise ValueError("The security PIN must contain exactly 6 digits.")
    if len(set(pin)) == 1:
        raise ValueError("Choose a PIN that does not repeat the same digit.")
    if pin in "0123456789" or pin in "9876543210":
        raise ValueError("Choose a PIN that is not a simple sequence.")


def generate_recovery_key():
    """Generate an unguessable key; only its pgcrypto hash is persisted."""
    return secrets.token_urlsafe(32)


def _write_activity(cursor, user_id, action, table_name="user_account", record_id=None):
    """Record the action without storing a password, PIN, or recovery key."""
    cursor.execute(
        """
        INSERT INTO activity_log (user_id, action, table_name, record_id)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, action, table_name, user_id if record_id is None else record_id),
    )


def _set_activity_actor(cursor, user_id):
    """Attach the acting account to row-trigger audit records for this transaction."""
    cursor.execute("SELECT set_config('relieflink.user_id', %s, TRUE)", (str(user_id),))


def admin_is_configured():
    """Return true if an administrator exists, including a disabled one."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM user_account WHERE role = %s)",
                (ADMIN_ROLE,),
            )
            return cursor.fetchone()[0]
    finally:
        connection.close()


def create_first_admin(name, officer_id, username, password, pin):
    """Create the single administrator and return a recovery key exactly once."""
    name = name.strip()
    officer_id = officer_id.strip()
    username = username.strip()
    if not name or not officer_id or not username:
        raise ValueError("Fill in every box.")
    if len(name) > 120 or len(officer_id) > 80:
        raise ValueError("The name or officer ID is too long.")
    validate_username(username)
    validate_password(password)
    validate_pin(pin)

    recovery_key = generate_recovery_key()
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                # Recheck inside the creation transaction; the unique index
                # handles two first-time setup attempts racing each other.
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM user_account WHERE role = %s)",
                    (ADMIN_ROLE,),
                )
                if cursor.fetchone()[0]:
                    raise AuthenticationError(
                        "An administrator already exists. Please log in."
                    )

                cursor.execute(
                    """
                    INSERT INTO user_account
                        (name, officer_id, username, password_hash,
                         security_pin_hash, role, recovery_key_hash)
                    VALUES
                        (%s, %s, %s,
                         crypt(%s, gen_salt('bf')),
                         crypt(%s, gen_salt('bf')),
                         %s,
                         crypt(%s, gen_salt('bf')))
                    RETURNING user_id
                    """,
                    (name, officer_id, username, password, pin, ADMIN_ROLE, recovery_key),
                )
                user_id = cursor.fetchone()[0]
                _write_activity(cursor, user_id, "admin_setup_success")
    except errors.UniqueViolation as error:
        if error.diag.constraint_name == "user_account_single_admin_idx":
            raise AuthenticationError(
                "An administrator already exists. Please log in."
            ) from error
        if error.diag.constraint_name == "user_account_username_key":
            raise AuthenticationError("That username is already in use.") from error
        if error.diag.constraint_name == "user_account_officer_id_key":
            raise AuthenticationError("That officer ID is already in use.") from error
        raise
    finally:
        connection.close()

    return AdminIdentity(user_id, name, username, ADMIN_ROLE), recovery_key
def register_user(name, phone, username, email, password):
    """Register a public account; the role and password hash are set here."""
    name = name.strip()
    phone = phone.strip()
    username = username.strip().lower()
    email = email.strip().lower()
    if not name or not phone or not username or not email or not password:
        raise ValueError("Fill in every box.")
    if len(name) > 120 or len(phone) > 32:
        raise ValueError("The name or phone number is too long.")
    validate_username(username)
    validate_email(email)
    validate_password(password)

    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_account
                        (name, phone, username, email, password_hash, role)
                    VALUES (%s, %s, %s, %s, crypt(%s, gen_salt('bf')), 'User')
                    RETURNING user_id
                    """,
                    (name, phone, username, email, password),
                )
                user_id = cursor.fetchone()[0]
                _write_activity(cursor, user_id, "user_registration_success")
    except errors.UniqueViolation as error:
        if error.diag.constraint_name in (
            "user_account_username_key",
            "user_account_username_ci_idx",
        ):
            raise AuthenticationError("That username is already in use.") from error
        if error.diag.constraint_name in (
            "user_account_email_key",
            "user_account_email_ci_idx",
        ):
            raise AuthenticationError("That email address is already registered.") from error
        raise
    finally:
        connection.close()

    return UserIdentity(user_id, name, username)


def authenticate_user(username_or_email, password):
    """Authenticate a normal account and apply the shared three-attempt lockout."""
    identifier = username_or_email.strip()
    if not identifier or not password:
        raise ValueError("Enter your username or email and password.")

    connection = get_connection()
    identity = None
    error_message = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, name, username, role, is_active,
                           failed_attempts,
                           (locked_until > CURRENT_TIMESTAMP) AS is_locked,
                           (locked_until <= CURRENT_TIMESTAMP) AS lock_expired,
                           (crypt(%s, password_hash) = password_hash) AS password_matches
                      FROM user_account
                     WHERE lower(username) = lower(%s)
                        OR lower(email) = lower(%s)
                     FOR UPDATE
                    """,
                    (password, identifier, identifier),
                )
                account = cursor.fetchone()

                if account is None:
                    _write_activity(cursor, None, "user_login_failure")
                    error_message = "Incorrect username/email or password."
                else:
                    (
                        user_id,
                        name,
                        account_username,
                        role,
                        is_active,
                        failed_attempts,
                        is_locked,
                        lock_expired,
                        password_matches,
                    ) = account

                    if role != "User":
                        _write_activity(cursor, user_id, "user_login_role_mismatch")
                        error_message = "This is not a Normal User account."
                    elif not is_active:
                        _write_activity(cursor, user_id, "user_login_failure")
                        error_message = "This account is disabled."
                    elif is_locked:
                        _write_activity(cursor, user_id, "user_login_failure")
                        error_message = "Account locked, try again later."
                    else:
                        if lock_expired:
                            failed_attempts = 0
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = 0, locked_until = NULL
                                 WHERE user_id = %s
                                """,
                                (user_id,),
                            )

                        if not password_matches:
                            failed_attempts += 1
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = %s,
                                       locked_until = CASE
                                           WHEN %s >= %s
                                           THEN CURRENT_TIMESTAMP + INTERVAL '15 minutes'
                                           ELSE NULL
                                       END
                                 WHERE user_id = %s
                                """,
                                (failed_attempts, failed_attempts, MAX_FAILED_ATTEMPTS, user_id),
                            )
                            _write_activity(cursor, user_id, "user_login_failure")
                            error_message = (
                                "Account locked, try again later."
                                if failed_attempts >= MAX_FAILED_ATTEMPTS
                                else "Incorrect username/email or password."
                            )
                        else:
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = 0, locked_until = NULL
                                 WHERE user_id = %s
                                """,
                                (user_id,),
                            )
                            _write_activity(cursor, user_id, "user_login_success")
                            identity = UserIdentity(user_id, name, account_username)
    finally:
        connection.close()

    if error_message:
        raise AuthenticationError(error_message)
    return identity


def public_relief_information():
    """Return public disaster, camp, and helpline details without stock counts."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT d.name, d.type, d.severity, r.name, r.district, c.name,
                       c.population
                  FROM disaster AS d
                  JOIN disaster_area AS da ON da.disaster_id = d.disaster_id
                  JOIN region AS r ON r.region_id = da.region_id
                  LEFT JOIN camp AS c
                    ON c.disaster_id = d.disaster_id
                   AND c.region_id = r.region_id
                   AND c.status = 'Active'
                 WHERE d.status = 'Active'
                 ORDER BY d.name, r.district, r.name, c.name
                """
            )
            disasters = cursor.fetchall()
            cursor.execute(
                """
                SELECT public_contacts.name, public_contacts.phone_number,
                       public_contacts.level, public_contacts.region_name,
                       public_contacts.camp_name, public_contacts.contact_type
                  FROM (
                        SELECT h.name, h.phone_number, h.level,
                               r.name AS region_name, c.name AS camp_name,
                               h.contact_type
                          FROM helpline AS h
                          LEFT JOIN region AS r ON r.region_id = h.region_id
                          LEFT JOIN camp AS c ON c.camp_id = h.camp_id
                         WHERE h.is_active = TRUE
                        UNION ALL
                        SELECT lc.name, lc.phone_number, 'Local',
                               r.name, NULL::TEXT, lc.contact_type
                          FROM local_contact AS lc
                          JOIN region AS r ON r.region_id = lc.region_id
                         WHERE lc.is_active = TRUE
                       ) AS public_contacts
                 ORDER BY CASE public_contacts.level
                              WHEN 'National' THEN 1
                              WHEN 'State' THEN 2
                              WHEN 'District' THEN 3
                              WHEN 'Local' THEN 4
                              ELSE 5
                          END,
                          public_contacts.region_name NULLS FIRST,
                          public_contacts.name
                """
            )
            helplines = cursor.fetchall()
    finally:
        connection.close()
    return disasters, helplines


def _require_admin(cursor, actor_id):
    """Recheck the acting account in PostgreSQL before each admin operation."""
    cursor.execute(
        "SELECT role, is_active FROM user_account WHERE user_id = %s FOR UPDATE",
        (actor_id,),
    )
    actor = cursor.fetchone()
    if actor is None or actor[0] != ADMIN_ROLE or not actor[1]:
        raise AuthenticationError("You do not have permission.")


def list_departments():
    """Return departments available for administrator staff assignment."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT department_id, name FROM department ORDER BY name")
            return cursor.fetchall()
    finally:
        connection.close()


def create_staff(actor_id, name, phone, username, temporary_password, pin, department_id):
    """Create a staff account; the department comes from the administrator form."""
    name, phone, username = name.strip(), phone.strip(), username.strip().lower()
    if not all((name, phone, username, temporary_password, pin, department_id)):
        raise ValueError("Fill in every box.")
    validate_username(username)
    validate_password(temporary_password)
    validate_pin(pin)
    try:
        department_id = int(department_id)
    except (TypeError, ValueError) as error:
        raise ValueError("Choose a valid department.") from error

    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(
                    """
                    INSERT INTO user_account
                        (name, phone, username, password_hash, security_pin_hash,
                         role, department_id, must_change_password)
                    SELECT %s, %s, %s, crypt(%s, gen_salt('bf')),
                           crypt(%s, gen_salt('bf')), 'Staff', department_id, TRUE
                      FROM department
                     WHERE department_id = %s
                    RETURNING user_id
                    """,
                    (name, phone, username, temporary_password, pin, department_id),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    raise ValueError("Choose a valid department.")
                staff_id = inserted[0]
                _write_activity(cursor, actor_id, "staff_created")
    except errors.UniqueViolation as error:
        if error.diag.constraint_name in (
            "user_account_username_key",
            "user_account_username_ci_idx",
        ):
            raise AuthenticationError("That username is already in use.") from error
        raise
    finally:
        connection.close()
    return staff_id


def list_staff(actor_id):
    """List staff only after rechecking the requesting Admin in the database."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT u.user_id, u.name, u.username, d.name, u.is_active,
                           u.created_at
                      FROM user_account AS u
                      JOIN department AS d ON d.department_id = u.department_id
                     WHERE u.role = 'Staff'
                     ORDER BY u.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def update_staff(actor_id, staff_id, department_id=None, active=None,
                 temporary_password=None, temporary_pin=None):
    """Perform one Admin-authorized staff change and record it in the log."""
    if department_id is None and active is None and temporary_password is None:
        raise ValueError("Choose a staff change to apply.")
    if temporary_password is not None:
        validate_password(temporary_password)
        validate_pin(temporary_pin or "")

    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(
                    "SELECT role FROM user_account WHERE user_id = %s FOR UPDATE",
                    (staff_id,),
                )
                staff = cursor.fetchone()
                if staff is None or staff[0] != "Staff":
                    raise AuthenticationError("You do not have permission.")

                if department_id is not None:
                    cursor.execute(
                        """
                        UPDATE user_account SET department_id = %s
                         WHERE user_id = %s AND role = 'Staff'
                        """,
                        (department_id, staff_id),
                    )
                    _write_activity(cursor, actor_id, "staff_department_changed")
                if active is not None:
                    cursor.execute(
                        """
                        UPDATE user_account SET is_active = %s
                         WHERE user_id = %s AND role = 'Staff'
                        """,
                        (active, staff_id),
                    )
                    _write_activity(
                        cursor, actor_id, "staff_enabled" if active else "staff_disabled"
                    )
                if temporary_password is not None:
                    cursor.execute(
                        """
                        UPDATE user_account
                           SET password_hash = crypt(%s, gen_salt('bf')),
                               security_pin_hash = crypt(%s, gen_salt('bf')),
                               must_change_password = TRUE,
                               failed_attempts = 0,
                               locked_until = NULL
                         WHERE user_id = %s AND role = 'Staff'
                        """,
                        (temporary_password, temporary_pin, staff_id),
                    )
                    _write_activity(cursor, actor_id, "staff_password_reset")
    finally:
        connection.close()


def authenticate_staff(username, password, pin):
    """Authenticate staff and return the assigned department from PostgreSQL."""
    username = username.strip()
    if not username or not password or not pin:
        raise ValueError("Enter your username, password, and security PIN.")

    connection = get_connection()
    identity = None
    error_message = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.user_id, u.name, u.username, u.role, u.is_active,
                           u.failed_attempts, (u.locked_until > CURRENT_TIMESTAMP),
                           (u.locked_until <= CURRENT_TIMESTAMP),
                           (crypt(%s, u.password_hash) = u.password_hash),
                           (crypt(%s, u.security_pin_hash) = u.security_pin_hash),
                           u.department_id, d.name, u.must_change_password
                      FROM user_account AS u
                      LEFT JOIN department AS d ON d.department_id = u.department_id
                     WHERE lower(u.username) = lower(%s)
                     FOR UPDATE OF u
                    """,
                    (password, pin, username),
                )
                account = cursor.fetchone()
                if account is None:
                    _write_activity(cursor, None, "staff_login_failure")
                    error_message = "Incorrect username, password, or security PIN."
                else:
                    (user_id, name, account_username, role, is_active, failures,
                     locked, lock_expired, password_ok, pin_ok, department_id,
                     department_name, must_change) = account
                    if role != "Staff":
                        _write_activity(cursor, user_id, "staff_login_role_mismatch")
                        error_message = "This is not a Staff account."
                    elif not is_active:
                        _write_activity(cursor, user_id, "staff_login_failure")
                        error_message = "This staff account is disabled."
                    elif locked:
                        _write_activity(cursor, user_id, "staff_login_failure")
                        error_message = "Account locked, try again later."
                    elif not department_id:
                        _write_activity(cursor, user_id, "staff_login_failure")
                        error_message = "This staff account has no assigned department."
                    else:
                        if lock_expired:
                            failures = 0
                        if not (password_ok and pin_ok):
                            failures += 1
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = %s,
                                       locked_until = CASE WHEN %s >= %s
                                           THEN CURRENT_TIMESTAMP + INTERVAL '15 minutes'
                                           ELSE NULL END
                                 WHERE user_id = %s
                                """,
                                (failures, failures, MAX_FAILED_ATTEMPTS, user_id),
                            )
                            _write_activity(cursor, user_id, "staff_login_failure")
                            error_message = (
                                "Account locked, try again later."
                                if failures >= MAX_FAILED_ATTEMPTS
                                else "Incorrect username, password, or security PIN."
                            )
                        else:
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = 0, locked_until = NULL
                                 WHERE user_id = %s
                                """,
                                (user_id,),
                            )
                            _write_activity(cursor, user_id, "staff_login_success")
                            identity = StaffIdentity(
                                user_id, name, account_username, department_id,
                                department_name, "Staff", must_change
                            )
    finally:
        connection.close()

    if error_message:
        raise AuthenticationError(error_message)
    return identity


def change_staff_credentials(user_id, old_password, old_pin, new_password, new_pin):
    """Require the current credentials before changing a staff password and PIN."""
    validate_password(new_password)
    validate_pin(new_pin)
    if old_password == new_password or old_pin == new_pin:
        raise ValueError("Choose a new password and a new security PIN.")

    connection = get_connection()
    changed = False
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active,
                           crypt(%s, password_hash) = password_hash,
                           crypt(%s, security_pin_hash) = security_pin_hash
                      FROM user_account WHERE user_id = %s FOR UPDATE
                    """,
                    (old_password, old_pin, user_id),
                )
                account = cursor.fetchone()
                if not account or account[0] != "Staff" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                if not (account[2] and account[3]):
                    raise AuthenticationError("Current password or security PIN is incorrect.")
                cursor.execute(
                    """
                    UPDATE user_account
                       SET password_hash = crypt(%s, gen_salt('bf')),
                           security_pin_hash = crypt(%s, gen_salt('bf')),
                           must_change_password = FALSE,
                           failed_attempts = 0,
                           locked_until = NULL
                     WHERE user_id = %s AND role = 'Staff' AND is_active = TRUE
                    """,
                    (new_password, new_pin, user_id),
                )
                _write_activity(cursor, user_id, "staff_credentials_changed")
                changed = True
    finally:
        connection.close()
    return changed


def require_department(user_id, required_department):
    """Recheck staff role, active status, and assigned department for each action."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.role, u.is_active, d.name
                  FROM user_account AS u
                  LEFT JOIN department AS d ON d.department_id = u.department_id
                 WHERE u.user_id = %s
                """,
                (user_id,),
            )
            account = cursor.fetchone()
            if not account or not account[1] or account[0] not in ("Staff", "Admin"):
                raise AuthenticationError("You do not have permission.")
            if account[0] == "Staff" and account[2] != required_department:
                raise AuthenticationError("You do not have permission.")
            return account[0]
    finally:
        connection.close()


def admin_catalog_rows(actor_id, catalog):
    """Read an Admin-only catalog after verifying the active database role."""
    queries = {
        "disasters": """
            SELECT disaster_id, name, type, severity, status, start_date, end_date
              FROM disaster ORDER BY start_date DESC, name
        """,
        "places": """
            SELECT region_id, name, district, state
              FROM region ORDER BY district, name
        """,
        "affected areas": """
            SELECT d.name, r.name, r.district, da.created_at
              FROM disaster_area da
              JOIN disaster d USING (disaster_id)
              JOIN region r USING (region_id)
             ORDER BY d.name, r.district, r.name
        """,
        "camps": """
            SELECT c.camp_id, c.name, d.name, r.name, c.population, c.status
              FROM camp c JOIN disaster d USING (disaster_id)
              JOIN region r USING (region_id)
             ORDER BY d.name, r.name, c.name
        """,
        "local contacts": """
            SELECT lc.local_contact_id, lc.name, r.name, r.district,
                   lc.contact_type, lc.phone_number, lc.is_active
              FROM local_contact lc JOIN region r USING (region_id)
             ORDER BY r.district, r.name, lc.name
        """,
        "helplines": """
            SELECT display.helpline_id, display.name, display.phone_number,
                   display.level, display.region_name, display.camp_name,
                   display.is_active
              FROM (
                    SELECT h.helpline_id, h.name, h.phone_number, h.level,
                           r.name AS region_name, c.name AS camp_name, h.is_active
                      FROM helpline h
                      LEFT JOIN region r USING (region_id)
                      LEFT JOIN camp c USING (camp_id)
                    UNION ALL
                    SELECT NULL::INTEGER, lc.name, lc.phone_number, 'Local',
                           r.name, NULL::TEXT, lc.is_active
                      FROM local_contact lc
                      JOIN region r USING (region_id)
                   ) AS display
             ORDER BY display.level, display.name
        """,
    }
    if catalog not in queries:
        raise ValueError("Unknown administrator catalog.")
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(queries[catalog])
                return cursor.fetchall()
    finally:
        connection.close()


def admin_catalog_choices(actor_id, choice_type):
    """Load database-backed dropdown options for Admin disaster setup forms."""
    queries = {
        "disasters": """
            SELECT disaster_id, name FROM disaster ORDER BY name
        """,
        "places": """
            SELECT region_id, name || ' — ' || district
              FROM region ORDER BY district, name
        """,
        "affected_areas": """
            SELECT da.disaster_id, da.region_id,
                   d.name || ' — ' || r.name || ', ' || r.district
              FROM disaster_area da
              JOIN disaster d USING (disaster_id)
              JOIN region r USING (region_id)
             ORDER BY d.name, r.district, r.name
        """,
        "camps": """
            SELECT c.camp_id, c.name || ' — ' || r.name
              FROM camp c JOIN region r USING (region_id)
             WHERE c.status = 'Active'
             ORDER BY r.name, c.name
        """,
    }
    if choice_type not in queries:
        raise ValueError("Unknown administrator choice list.")
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(queries[choice_type])
                return cursor.fetchall()
    finally:
        connection.close()


def _admin_insert(actor_id, sql, parameters):
    """Run a single parameterized catalog insert as the verified Admin."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                _set_activity_actor(cursor, actor_id)
                cursor.execute(sql, parameters)
                created = cursor.fetchone()
                if created is None:
                    raise ValueError("The selected database record was not found.")
                record_id = created[0]
    finally:
        connection.close()
    return record_id


def create_disaster(actor_id, name, disaster_type, severity, start_date,
                    end_date="", description=""):
    """Create a disaster record after checking required fields and dates."""
    name, disaster_type = name.strip(), disaster_type.strip()
    if not name or not disaster_type or not start_date:
        raise ValueError("Fill in every required box.")
    if severity not in ("Low", "Moderate", "High", "Critical"):
        raise ValueError("Choose a valid severity.")
    return _admin_insert(
        actor_id,
        """
        INSERT INTO disaster (name, type, severity, start_date, end_date, description)
        VALUES (%s, %s, %s, %s, NULLIF(%s, '')::DATE, NULLIF(%s, ''))
        RETURNING disaster_id
        """,
        (name, disaster_type, severity, start_date, end_date, description.strip()),
    )


def create_region(actor_id, name, district, state=""):
    """Add a place for future affected-area and camp assignments."""
    name, district, state = name.strip(), district.strip(), state.strip()
    if not name or not district:
        raise ValueError("Place name and district are required.")
    return _admin_insert(
        actor_id,
        """
        INSERT INTO region (name, district, state)
        VALUES (%s, %s, NULLIF(%s, ''))
        RETURNING region_id
        """,
        (name, district, state),
    )


def create_disaster_area(actor_id, disaster_id, region_id):
    """Link a disaster to a place; the composite key prevents duplicate links."""
    return _admin_insert(
        actor_id,
        """
        INSERT INTO disaster_area (disaster_id, region_id)
        SELECT disaster_id, region_id FROM disaster CROSS JOIN region
         WHERE disaster_id = %s AND region_id = %s
        RETURNING disaster_id
        """,
        (disaster_id, region_id),
    )


def create_camp(actor_id, disaster_id, region_id, name, population):
    """Add a camp only inside an area already assigned to its disaster."""
    name = name.strip()
    if not name:
        raise ValueError("Camp name is required.")
    try:
        population = int(population)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a whole-number camp population.") from error
    if population <= 0:
        raise ValueError("Camp population must be greater than zero.")
    return _admin_insert(
        actor_id,
        """
        INSERT INTO camp (disaster_id, region_id, name, population)
        SELECT disaster_id, region_id, %s, %s FROM disaster_area
         WHERE disaster_id = %s AND region_id = %s
        RETURNING camp_id
        """,
        (name, population, disaster_id, region_id),
    )


def create_local_contact(actor_id, region_id, name, contact_type, phone, description=""):
    """Add a Person or Group contact to any affected place."""
    name, phone = name.strip(), phone.strip()
    if not name or not phone:
        raise ValueError("Contact name and phone number are required.")
    if contact_type not in ("Person", "Group"):
        raise ValueError("Choose Person or Group.")
    return _admin_insert(
        actor_id,
        """
        INSERT INTO local_contact
            (region_id, name, contact_type, phone_number, description)
        SELECT region_id, %s, %s, %s, NULLIF(%s, '')
          FROM region WHERE region_id = %s
        RETURNING local_contact_id
        """,
        (name, contact_type, phone, description.strip(), region_id),
    )


def create_helpline(actor_id, name, phone, level, contact_type=None,
                    region_id=None, camp_id=None):
    """Add a verified helpline number at its national-to-camp scope."""
    name, phone = name.strip(), phone.strip()
    levels = ("National", "State", "District", "Local", "Camp")
    if not name or not phone:
        raise ValueError("Helpline name and phone number are required.")
    if level not in levels:
        raise ValueError("Choose a valid helpline level.")
    if level in ("District", "Local") and not region_id:
        raise ValueError("Choose the place for this helpline.")
    if level == "Camp" and not camp_id:
        raise ValueError("Choose the camp for this helpline.")
    if level in ("Local", "Camp") and contact_type not in ("Person", "Group"):
        raise ValueError("Choose whether this contact is a Person or Group.")
    return _admin_insert(
        actor_id,
        """
        INSERT INTO helpline (name, phone_number, level, contact_type, region_id, camp_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING helpline_id
        """,
        (name, phone, level, contact_type, region_id, camp_id),
    )


def _positive_quantity(value):
    """Parse a positive finite supply quantity without floating-point rounding."""
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Enter a valid positive quantity.") from error
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("Supply quantities must be greater than zero.")
    return quantity


def public_supply_resources():
    """List public donation options without exposing their inventory levels."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT resource_id, name, unit FROM resource ORDER BY name"
            )
            return cursor.fetchall()
    finally:
        connection.close()


def _nonnegative_quantity(value, label):
    """Parse a finite zero-or-greater amount using exact decimal arithmetic."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Enter a valid {label}.") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label.title()} cannot be negative.")
    return amount


def supply_catalog_choices(actor_id, choice_type):
    """Return permitted resource, place, or warehouse dropdown options."""
    if choice_type not in ("resources", "places", "warehouses"):
        raise ValueError("Unknown supply choice list.")
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                if choice_type == "resources":
                    cursor.execute(
                        "SELECT resource_id, name FROM resource ORDER BY name"
                    )
                elif choice_type == "places":
                    cursor.execute(
                        """
                        SELECT region_id, name || ' — ' || district
                          FROM region ORDER BY district, name
                        """
                    )
                else:
                    cursor.execute(
                        "SELECT warehouse_id, name FROM warehouse ORDER BY name"
                    )
                return cursor.fetchall()
    finally:
        connection.close()


def admin_supply_rows(actor_id, catalog):
    """Read supply catalogs only after checking for an active Admin."""
    queries = {
        "resources": """
            SELECT resource_id, name, category, unit, daily_need_per_person
              FROM resource ORDER BY name
        """,
        "warehouses": """
            SELECT w.warehouse_id, w.name, r.name, r.district, w.capacity
              FROM warehouse w JOIN region r USING (region_id)
             ORDER BY r.district, r.name, w.name
        """,
    }
    if catalog not in queries:
        raise ValueError("Unknown supply catalog.")
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(queries[catalog])
                return cursor.fetchall()
    finally:
        connection.close()


def create_resource(actor_id, name, category, unit, daily_need_per_person):
    """Add an adjustable resource and its per-person daily need."""
    name, category, unit = name.strip(), category.strip(), unit.strip()
    if not name or not category or not unit:
        raise ValueError("Fill in every required box.")
    need = _nonnegative_quantity(daily_need_per_person, "daily need per person")
    return _admin_insert(
        actor_id,
        """
        INSERT INTO resource (name, category, unit, daily_need_per_person)
        VALUES (%s, %s, %s, %s)
        RETURNING resource_id
        """,
        (name, category, unit, need),
    )


def create_warehouse(actor_id, region_id, name, capacity):
    """Add a warehouse in a selected place."""
    name = name.strip()
    if not name:
        raise ValueError("Warehouse name is required.")
    capacity_value = _positive_quantity(capacity)
    return _admin_insert(
        actor_id,
        """
        INSERT INTO warehouse (region_id, name, capacity)
        SELECT region_id, %s, %s FROM region WHERE region_id = %s
        RETURNING warehouse_id
        """,
        (name, capacity_value, region_id),
    )


def public_dropoff_warehouses():
    """List donation drop-off locations and need tags, never exact stock."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH warehouse_need AS (
                    SELECT c.region_id, r.resource_id,
                           SUM(c.population * r.daily_need_per_person * days_of_cover())
                               AS needed
                      FROM camp c
                      JOIN disaster d ON d.disaster_id = c.disaster_id
                      CROSS JOIN resource r
                     WHERE c.status = 'Active' AND d.status = 'Active'
                     GROUP BY c.region_id, r.resource_id
                )
                SELECT w.warehouse_id, w.name, r.name, r.district,
                       COALESCE(
                           string_agg(
                               CASE
                                   WHEN COALESCE(i.quantity, 0) < COALESCE(n.needed, 0)
                                   THEN 'Needs ' || lower(res.name)
                               END,
                               ', ' ORDER BY res.name
                           ) FILTER (
                               WHERE COALESCE(i.quantity, 0) < COALESCE(n.needed, 0)
                           ),
                           'Well stocked'
                       ) AS need_tags
                  FROM warehouse w
                  JOIN region r USING (region_id)
                  CROSS JOIN resource res
                  LEFT JOIN inventory i
                    ON i.warehouse_id = w.warehouse_id
                   AND i.resource_id = res.resource_id
                  LEFT JOIN warehouse_need n
                    ON n.region_id = w.region_id
                   AND n.resource_id = res.resource_id
                 GROUP BY w.warehouse_id, w.name, r.name, r.district
                 ORDER BY r.district, r.name, w.name
                """
            )
            return cursor.fetchall()
    finally:
        connection.close()


def donate_supplies(user_id, warehouse_id, items):
    """Record a user's donation; database triggers credit the warehouse stock."""
    if not items:
        raise ValueError("Choose at least one supply to donate.")
    cleaned_items = []
    seen_resources = set()
    for resource_id, quantity in items:
        quantity = _positive_quantity(quantity)
        try:
            resource_id = int(resource_id)
        except (TypeError, ValueError) as error:
            raise ValueError("Choose a valid supply.") from error
        if resource_id in seen_resources:
            raise ValueError("Choose each supply only once.")
        seen_resources.add(resource_id)
        cleaned_items.append((resource_id, quantity))

    connection = get_connection()
    donation_id = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT name, phone, role, is_active
                      FROM user_account
                     WHERE user_id = %s
                     FOR UPDATE
                    """,
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[2] != "User" or not account[3]:
                    raise AuthenticationError("You do not have permission.")
                donor_name, donor_phone = account[0], account[1]
                if not donor_phone:
                    raise ValueError("Add a phone number to your account before donating.")
                _set_activity_actor(cursor, user_id)
                cursor.execute(
                    """
                    INSERT INTO donor (user_id, name, phone, type)
                    VALUES (%s, %s, %s, 'Individual')
                    ON CONFLICT (user_id) WHERE user_id IS NOT NULL
                    DO UPDATE SET name = EXCLUDED.name, phone = EXCLUDED.phone
                    RETURNING donor_id
                    """,
                    (user_id, donor_name, donor_phone),
                )
                donor_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO donation (donor_id, warehouse_id)
                    SELECT %s, warehouse_id FROM warehouse WHERE warehouse_id = %s
                    RETURNING donation_id
                    """,
                    (donor_id, warehouse_id),
                )
                created = cursor.fetchone()
                if created is None:
                    raise ValueError("Choose a valid drop-off warehouse.")
                donation_id = created[0]
                for resource_id, quantity in cleaned_items:
                    cursor.execute(
                        """
                        INSERT INTO donation_item (donation_id, resource_id, quantity)
                        SELECT %s, resource_id, %s FROM resource WHERE resource_id = %s
                        RETURNING resource_id
                        """,
                        (donation_id, quantity, resource_id),
                    )
                    if cursor.fetchone() is None:
                        raise ValueError("One of the chosen supplies no longer exists.")
    finally:
        connection.close()
    return donation_id


def user_donation_history(user_id):
    """Show only donations made by the signed-in normal user."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT role, is_active FROM user_account WHERE user_id = %s",
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT d.donation_id, d.donation_date, w.name,
                           COALESCE(string_agg(r.name || ': ' || di.quantity || ' ' ||
                                               r.unit, ', ' ORDER BY r.name), 'No items')
                      FROM donor dn
                      JOIN donation d USING (donor_id)
                      JOIN warehouse w USING (warehouse_id)
                      LEFT JOIN donation_item di USING (donation_id)
                      LEFT JOIN resource r USING (resource_id)
                     WHERE dn.user_id = %s
                     GROUP BY d.donation_id, d.donation_date, w.name
                     ORDER BY d.donation_date DESC
                    """,
                    (user_id,),
                )
                return cursor.fetchall()
    finally:
        connection.close()


def request_catalog_for_region(user_id, region_id):
    """Return active camps in a selected affected place and safe need suggestions."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT role, is_active FROM user_account WHERE user_id = %s",
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT c.camp_id, c.name, c.population, d.name
                      FROM camp c
                      JOIN disaster d USING (disaster_id)
                      JOIN disaster_area da
                        ON da.disaster_id = c.disaster_id
                       AND da.region_id = c.region_id
                     WHERE c.region_id = %s
                       AND c.status = 'Active'
                       AND d.status = 'Active'
                     ORDER BY c.name
                    """,
                    (region_id,),
                )
                camps = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT resource_id, name, unit, daily_need_per_person
                      FROM resource ORDER BY name
                    """
                )
                resources = cursor.fetchall()
        return camps, resources
    finally:
        connection.close()


def public_affected_places():
    """Return active affected places for the public request form."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT r.region_id, r.name || ' — ' || r.district
                  FROM disaster_area da
                  JOIN disaster d USING (disaster_id)
                  JOIN region r USING (region_id)
                 WHERE d.status = 'Active'
                 ORDER BY 2
                """
            )
            return cursor.fetchall()
    finally:
        connection.close()


def submit_relief_request(user_id, region_id, camp_id, items, priority="Normal"):
    """Create a normal or urgent camp request atomically for its signed-in user."""
    if priority not in ("Normal", "Urgent"):
        raise ValueError("Choose a valid request priority.")
    if not items:
        raise ValueError("Choose at least one supply.")
    cleaned = []
    seen = set()
    for resource_id, quantity in items:
        amount = _positive_quantity(quantity)
        try:
            resource_id = int(resource_id)
        except (TypeError, ValueError) as error:
            raise ValueError("Choose a valid supply.") from error
        if resource_id in seen:
            raise ValueError("Choose each supply only once.")
        seen.add(resource_id)
        cleaned.append((resource_id, amount))

    connection = get_connection()
    request_id = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active FROM user_account
                     WHERE user_id = %s FOR UPDATE
                    """,
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT c.camp_id
                      FROM camp c
                      JOIN disaster d USING (disaster_id)
                      JOIN disaster_area da
                        ON da.disaster_id = c.disaster_id
                       AND da.region_id = c.region_id
                     WHERE c.camp_id = %s AND c.region_id = %s
                       AND c.status = 'Active' AND d.status = 'Active'
                    """,
                    (camp_id, region_id),
                )
                if cursor.fetchone() is None:
                    raise ValueError("Choose a camp in the selected affected place.")
                _set_activity_actor(cursor, user_id)
                cursor.execute(
                    """
                    INSERT INTO request (camp_id, requested_by, priority)
                    VALUES (%s, %s, %s) RETURNING request_id
                    """,
                    (camp_id, user_id, priority),
                )
                request_id = cursor.fetchone()[0]
                for resource_id, quantity in cleaned:
                    cursor.execute(
                        """
                        INSERT INTO request_item (request_id, resource_id, quantity)
                        SELECT %s, resource_id, %s
                          FROM resource WHERE resource_id = %s
                        RETURNING resource_id
                        """,
                        (request_id, quantity, resource_id),
                    )
                    if cursor.fetchone() is None:
                        raise ValueError("One of the selected supplies no longer exists.")
    finally:
        connection.close()
    return request_id


def user_request_history(user_id, open_only=False):
    """List only this user's requests and their requested supply summaries."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT role, is_active FROM user_account WHERE user_id = %s",
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT q.request_id, q.request_date, q.priority, q.status,
                           c.name, r.name,
                           COALESCE(string_agg(
                               res.name || ': ' || qi.quantity || ' ' || res.unit,
                               ', ' ORDER BY res.name
                           ), 'No items')
                      FROM request q
                      JOIN camp c USING (camp_id)
                      JOIN region r USING (region_id)
                      LEFT JOIN request_item qi USING (request_id)
                      LEFT JOIN resource res USING (resource_id)
                     WHERE q.requested_by = %s
                       AND (%s = FALSE OR q.status <> 'Delivered')
                     GROUP BY q.request_id, q.request_date, q.priority, q.status,
                              c.name, r.name
                     ORDER BY CASE WHEN q.priority = 'Urgent' THEN 0 ELSE 1 END,
                              q.request_date DESC
                    """,
                    (user_id, open_only),
                )
                return cursor.fetchall()
    finally:
        connection.close()


def request_tracking(user_id, request_id):
    """Read status history only when the request belongs to the signed-in user."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active FROM user_account WHERE user_id = %s
                    """,
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT q.request_id, q.priority, q.status, q.request_date,
                           c.name, r.name, s.status
                      FROM request q JOIN camp c USING (camp_id)
                      JOIN region r USING (region_id)
                      LEFT JOIN LATERAL (
                          SELECT status
                            FROM shipment
                           WHERE request_id = q.request_id
                           ORDER BY dispatch_date DESC, shipment_id DESC
                           LIMIT 1
                      ) s ON TRUE
                     WHERE q.request_id = %s AND q.requested_by = %s
                    """,
                    (request_id, user_id),
                )
                request = cursor.fetchone()
                if request is None:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT new_status, changed_at
                      FROM request_status_history
                     WHERE request_id = %s
                     ORDER BY changed_at, history_id
                    """,
                    (request_id,),
                )
                history = cursor.fetchall()
        return request, history
    finally:
        connection.close()


def logistics_pending_requests(actor_id):
    """Return urgent-first pending requests to authorized Logistics staff."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.role, u.is_active, d.name
                      FROM user_account u
                      LEFT JOIN department d USING (department_id)
                     WHERE u.user_id = %s
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or not (
                    actor[0] == "Admin"
                    or (actor[0] == "Staff" and actor[2] == "Logistics")
                ):
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT q.request_id, q.priority, q.request_date,
                           c.name, r.name, r.district,
                           COALESCE(string_agg(
                               res.name || ': ' || qi.quantity || ' ' || res.unit,
                               ', ' ORDER BY res.name
                           ), 'No requested items')
                      FROM request q
                      JOIN camp c USING (camp_id)
                      JOIN region r USING (region_id)
                      LEFT JOIN request_item qi USING (request_id)
                      LEFT JOIN resource res USING (resource_id)
                     WHERE q.status = 'Pending'
                     GROUP BY q.request_id, q.priority, q.request_date,
                              c.name, r.name, r.district
                     ORDER BY CASE WHEN q.priority = 'Urgent' THEN 0 ELSE 1 END,
                              q.request_date, q.request_id
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def logistics_choices(actor_id, request_id):
    """Return same-region warehouses and dispatch vehicles/drivers after auth."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.role, u.is_active, d.name
                      FROM user_account u
                      LEFT JOIN department d USING (department_id)
                     WHERE u.user_id = %s
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or not (
                    actor[0] == "Admin"
                    or (actor[0] == "Staff" and actor[2] == "Logistics")
                ):
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT r.region_id
                      FROM request q
                      JOIN camp c USING (camp_id)
                      JOIN region r USING (region_id)
                     WHERE q.request_id = %s AND q.status = 'Pending'
                    """,
                    (request_id,),
                )
                request = cursor.fetchone()
                if request is None:
                    raise ValueError("This request is no longer pending.")
                region_id = request[0]
                cursor.execute(
                    """
                    SELECT warehouse_id, name
                      FROM warehouse
                     WHERE region_id = %s
                     ORDER BY name
                    """,
                    (region_id,),
                )
                warehouses = cursor.fetchall()
                cursor.execute(
                    "SELECT vehicle_id, plate_no, type FROM vehicle ORDER BY plate_no"
                )
                vehicles = cursor.fetchall()
                cursor.execute(
                    "SELECT driver_id, name FROM driver ORDER BY name"
                )
                drivers = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT qi.resource_id, res.name, qi.quantity, res.unit
                      FROM request_item qi
                      JOIN resource res USING (resource_id)
                     WHERE qi.request_id = %s
                     ORDER BY res.name
                    """,
                    (request_id,),
                )
                items = cursor.fetchall()
                return warehouses, vehicles, drivers, items
    finally:
        connection.close()


def dispatch_request(actor_id, request_id, warehouse_id, vehicle_id, driver_id):
    """Allocate request supplies through the locking PostgreSQL procedure."""
    connection = get_connection()
    shipment_id = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CALL auto_allocate(%s, %s, %s, %s, %s, NULL)",
                    (request_id, warehouse_id, vehicle_id, driver_id, actor_id),
                )
                result = cursor.fetchone()
                if result is None or result[0] is None:
                    raise RuntimeError("auto_allocate did not return a shipment identifier.")
                shipment_id = result[0]
    except psycopg2.Error as error:
        if error.pgcode == "42501":
            raise AuthenticationError("You do not have permission.") from error
        if error.pgcode == "P0001":
            raise ValueError(error.diag.message_primary) from error
        raise
    finally:
        connection.close()
    return shipment_id


def logistics_shipment_history(actor_id):
    """List shipment progress after rechecking Logistics/Admin permissions."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.role, u.is_active, d.name
                      FROM user_account u
                      LEFT JOIN department d USING (department_id)
                     WHERE u.user_id = %s
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or not (
                    actor[0] == "Admin"
                    or (actor[0] == "Staff" and actor[2] == "Logistics")
                ):
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT s.shipment_id, s.request_id, q.priority, s.status,
                           s.dispatch_date, w.name, c.name, r.name,
                           v.plate_no, d.name
                      FROM shipment s
                      JOIN request q USING (request_id)
                      JOIN camp c USING (camp_id)
                      JOIN region r USING (region_id)
                      JOIN warehouse w USING (warehouse_id)
                      JOIN vehicle v USING (vehicle_id)
                      JOIN driver d USING (driver_id)
                     ORDER BY s.dispatch_date DESC, s.shipment_id DESC
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def update_shipment_status(actor_id, shipment_id, new_status):
    """Advance one shipment through its permitted Logistics status transitions."""
    transitions = {
        "Assigned": "Dispatched",
        "Dispatched": "On the way",
        "On the way": "Delivered",
    }
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.role, u.is_active, d.name
                      FROM user_account u
                      LEFT JOIN department d USING (department_id)
                     WHERE u.user_id = %s
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or not (
                    actor[0] == "Admin"
                    or (actor[0] == "Staff" and actor[2] == "Logistics")
                ):
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    "SELECT status FROM shipment WHERE shipment_id = %s FOR UPDATE",
                    (shipment_id,),
                )
                shipment = cursor.fetchone()
                if shipment is None:
                    raise ValueError("Shipment not found.")
                current_status = shipment[0]
                if transitions.get(current_status) != new_status:
                    raise ValueError(
                        f"Shipment status cannot move from {current_status} to {new_status}."
                    )
                _set_activity_actor(cursor, actor_id)
                cursor.execute(
                    "UPDATE shipment SET status = %s WHERE shipment_id = %s",
                    (new_status, shipment_id),
                )
                if new_status == "Delivered":
                    cursor.execute(
                        """
                        UPDATE request
                           SET status = 'Delivered'
                         WHERE request_id = (SELECT request_id FROM shipment WHERE shipment_id = %s)
                        """,
                        (shipment_id,),
                    )
    finally:
        connection.close()


def _require_helpline_staff(cursor, actor_id):
    """Verify an active Staff/Admin account before helpline-desk access."""
    cursor.execute(
        """
        SELECT u.role, u.is_active
          FROM user_account AS u
         WHERE u.user_id = %s
         FOR UPDATE
        """,
        (actor_id,),
    )
    actor = cursor.fetchone()
    if not actor or not actor[1] or actor[0] not in ("Admin", "Staff"):
        raise AuthenticationError("You do not have permission.")


def start_conversation(user_id, body, camp_id=None):
    """Create a user's conversation and one automatic acknowledgement."""
    body = body.strip()
    if not body:
        raise ValueError("Enter a message first.")
    if len(body) > 4000:
        raise ValueError("Messages must be 4000 characters or fewer.")
    connection = get_connection()
    conversation_id = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active FROM user_account
                     WHERE user_id = %s FOR UPDATE
                    """,
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                if camp_id is not None:
                    cursor.execute(
                        "SELECT camp_id FROM camp WHERE camp_id = %s AND status = 'Active'",
                        (camp_id,),
                    )
                    if cursor.fetchone() is None:
                        raise ValueError("Choose an active camp.")
                _set_activity_actor(cursor, user_id)
                cursor.execute(
                    """
                    INSERT INTO conversation (user_id, camp_id)
                    VALUES (%s, %s) RETURNING conversation_id
                    """,
                    (user_id, camp_id),
                )
                conversation_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO message (conversation_id, sender_user_id, body)
                    VALUES (%s, %s, %s)
                    """,
                    (conversation_id, user_id, body),
                )
                cursor.execute(
                    """
                    INSERT INTO message
                        (conversation_id, sender_user_id, body, is_system)
                    VALUES (%s, %s, %s, TRUE)
                    """,
                    (conversation_id, user_id,
                     "We received your message. A staff member will reply soon."),
                )
    finally:
        connection.close()
    return conversation_id


def user_conversations(user_id):
    """List only conversations belonging to the signed-in Normal User."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT role, is_active FROM user_account WHERE user_id = %s",
                    (user_id,),
                )
                account = cursor.fetchone()
                if not account or account[0] != "User" or not account[1]:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT c.conversation_id, c.status, c.created_at,
                           COALESCE((
                               SELECT body FROM message
                                WHERE conversation_id = c.conversation_id
                                ORDER BY sent_at DESC, message_id DESC LIMIT 1
                           ), '')
                      FROM conversation c
                     WHERE c.user_id = %s
                     ORDER BY c.created_at DESC, c.conversation_id DESC
                    """,
                    (user_id,),
                )
                return cursor.fetchall()
    finally:
        connection.close()


def conversation_messages(actor_id, conversation_id):
    """Read messages only for the owner or an active Staff/Admin account."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active FROM user_account WHERE user_id = %s
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1]:
                    raise AuthenticationError("You do not have permission.")
                if actor[0] == "User":
                    cursor.execute(
                        """
                        SELECT conversation_id FROM conversation
                         WHERE conversation_id = %s AND user_id = %s
                        """,
                        (conversation_id, actor_id),
                    )
                elif actor[0] in ("Staff", "Admin"):
                    cursor.execute(
                        """
                        SELECT conversation_id FROM conversation
                         WHERE conversation_id = %s
                        """,
                        (conversation_id,),
                    )
                else:
                    raise AuthenticationError("You do not have permission.")
                if cursor.fetchone() is None:
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT m.message_id, m.sender_user_id,
                           CASE WHEN m.is_system THEN 'ReliefLink' ELSE u.name END,
                           CASE WHEN m.is_system THEN 'System' ELSE u.role END,
                           m.body, m.sent_at
                      FROM message m
                      JOIN user_account u ON u.user_id = m.sender_user_id
                     WHERE m.conversation_id = %s
                     ORDER BY m.sent_at, m.message_id
                    """,
                    (conversation_id,),
                )
                return cursor.fetchall()
    finally:
        connection.close()


def send_conversation_reply(actor_id, conversation_id, body):
    """Send a reply from the conversation owner or an active staff member."""
    body = body.strip()
    if not body:
        raise ValueError("Enter a message first.")
    if len(body) > 4000:
        raise ValueError("Messages must be 4000 characters or fewer.")
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active FROM user_account
                     WHERE user_id = %s FOR UPDATE
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or actor[0] not in ("User", "Staff", "Admin"):
                    raise AuthenticationError("You do not have permission.")
                cursor.execute(
                    """
                    SELECT user_id, status FROM conversation
                     WHERE conversation_id = %s FOR UPDATE
                    """,
                    (conversation_id,),
                )
                conversation = cursor.fetchone()
                if conversation is None:
                    raise AuthenticationError("You do not have permission.")
                is_owner = actor[0] == "User" and conversation[0] == actor_id
                is_staff = actor[0] in ("Staff", "Admin")
                if not (is_owner or is_staff):
                    raise AuthenticationError("You do not have permission.")
                if conversation[1] == "Closed":
                    raise ValueError("This conversation is closed.")
                _set_activity_actor(cursor, actor_id)
                cursor.execute(
                    """
                    INSERT INTO message (conversation_id, sender_user_id, body)
                    VALUES (%s, %s, %s)
                    """,
                    (conversation_id, actor_id, body),
                )
    finally:
        connection.close()


def staff_open_conversations(actor_id):
    """List open conversations to all active Staff and Admin accounts."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_helpline_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT c.conversation_id, c.created_at, u.name,
                           COALESCE(camp.name, 'No camp selected'),
                           COALESCE((
                               SELECT body FROM message
                                WHERE conversation_id = c.conversation_id
                                ORDER BY sent_at DESC, message_id DESC LIMIT 1
                           ), '')
                      FROM conversation c
                      JOIN user_account u ON u.user_id = c.user_id
                      LEFT JOIN camp ON camp.camp_id = c.camp_id
                     WHERE c.status = 'Open'
                     ORDER BY c.created_at DESC, c.conversation_id DESC
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def close_conversation(actor_id, conversation_id):
    """Close a conversation as Staff/Admin or as its owning Normal User."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, is_active FROM user_account WHERE user_id = %s
                    """,
                    (actor_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1]:
                    raise AuthenticationError("You do not have permission.")
                if actor[0] in ("Staff", "Admin"):
                    _require_helpline_staff(cursor, actor_id)
                    cursor.execute(
                        "SELECT user_id FROM conversation WHERE conversation_id = %s",
                        (conversation_id,),
                    )
                elif actor[0] == "User":
                    cursor.execute(
                        """
                        SELECT user_id FROM conversation
                         WHERE conversation_id = %s AND user_id = %s
                        """,
                        (conversation_id, actor_id),
                    )
                else:
                    raise AuthenticationError("You do not have permission.")
                if cursor.fetchone() is None:
                    raise AuthenticationError("You do not have permission.")
                _set_activity_actor(cursor, actor_id)
                cursor.execute(
                    "UPDATE conversation SET status = 'Closed' WHERE conversation_id = %s",
                    (conversation_id,),
                )
    finally:
        connection.close()


def call_log_rows(actor_id):
    """List call records to active staff and administrators only."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_helpline_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT cl.call_id, cl.caller_name, cl.caller_phone,
                           r.name, r.district, cl.need, cl.outcome, cl.called_at
                      FROM call_log cl JOIN region r USING (region_id)
                     ORDER BY cl.called_at DESC, cl.call_id DESC
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def create_call_record(actor_id, caller_name, caller_phone, region_id, need, outcome):
    """Record an externally handled call as an active Staff/Admin member."""
    values = [caller_name.strip(), caller_phone.strip(), need.strip(), outcome.strip()]
    if any(not value for value in values):
        raise ValueError("Fill in every call record field.")
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_helpline_staff(cursor, actor_id)
                _set_activity_actor(cursor, actor_id)
                cursor.execute(
                    """
                    INSERT INTO call_log
                        (logged_by, caller_name, caller_phone, region_id, need, outcome)
                    SELECT %s, %s, %s, region_id, %s, %s
                      FROM region WHERE region_id = %s
                    RETURNING call_id
                    """,
                    (actor_id, values[0], values[1], values[2], values[3], region_id),
                )
                created = cursor.fetchone()
                if created is None:
                    raise ValueError("Choose a valid affected place.")
                return created[0]
    finally:
        connection.close()


def department_stock(staff_id, alerts_only=False):
    """Read exact inventory only for Warehouse staff or an active Admin."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.role, u.is_active, d.name
                      FROM user_account u
                      LEFT JOIN department d USING (department_id)
                     WHERE u.user_id = %s
                    """,
                    (staff_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or actor[0] not in ("Admin", "Staff"):
                    raise AuthenticationError("You do not have permission.")
                if actor[0] == "Staff" and actor[2] != "Warehouse":
                    raise AuthenticationError("You do not have permission.")

                if alerts_only:
                    cursor.execute(
                        """
                        SELECT a.alert_id, w.name, r.name, a.message, a.created_at
                          FROM alert a JOIN warehouse w USING (warehouse_id)
                          JOIN resource r USING (resource_id)
                         ORDER BY a.created_at DESC
                        """
                    )
                else:
                    cursor.execute(
                        """
                        SELECT w.name, r.name, i.quantity, r.unit
                          FROM inventory i JOIN warehouse w USING (warehouse_id)
                          JOIN resource r USING (resource_id)
                         ORDER BY w.name, r.name
                        """
                    )
                return cursor.fetchall()
    finally:
        connection.close()


def staff_record_donation(staff_id, donor_name, donor_phone, warehouse_id, items):
    """Let assigned Warehouse staff receive a donation using the stock trigger."""
    donor_name, donor_phone = donor_name.strip(), donor_phone.strip()
    if not donor_name or not donor_phone or not items:
        raise ValueError("Fill in donor details and choose at least one supply.")
    cleaned_items = [(int(resource_id), _positive_quantity(quantity))
                     for resource_id, quantity in items]
    connection = get_connection()
    donation_id = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.role, u.is_active, d.name FROM user_account u
                    LEFT JOIN department d USING (department_id)
                    WHERE u.user_id = %s FOR UPDATE OF u
                    """,
                    (staff_id,),
                )
                actor = cursor.fetchone()
                if not actor or not actor[1] or not (
                    actor[0] == "Admin" or
                    (actor[0] == "Staff" and actor[2] == "Warehouse")
                ):
                    raise AuthenticationError("You do not have permission.")
                _set_activity_actor(cursor, staff_id)
                cursor.execute(
                    """
                    INSERT INTO donor (name, phone, type)
                    VALUES (%s, %s, 'Individual') RETURNING donor_id
                    """,
                    (donor_name, donor_phone),
                )
                donor_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO donation (donor_id, warehouse_id)
                    SELECT %s, warehouse_id FROM warehouse WHERE warehouse_id = %s
                    RETURNING donation_id
                    """,
                    (donor_id, warehouse_id),
                )
                created = cursor.fetchone()
                if created is None:
                    raise ValueError("Choose a valid warehouse.")
                donation_id = created[0]
                for resource_id, quantity in cleaned_items:
                    cursor.execute(
                        """
                        INSERT INTO donation_item (donation_id, resource_id, quantity)
                        SELECT %s, resource_id, %s FROM resource WHERE resource_id = %s
                        RETURNING resource_id
                        """,
                        (donation_id, quantity, resource_id),
                    )
                    if cursor.fetchone() is None:
                        raise ValueError("Choose a valid supply.")
    finally:
        connection.close()
    return donation_id


def authenticate_admin(username, password, pin):
    """Check the database role and credentials while locking the account row."""
    username = username.strip()
    if not username or not password or not pin:
        raise ValueError("Enter your username, password, and security PIN.")

    connection = get_connection()
    result = None
    error_message = None
    try:
        with connection:
            with connection.cursor() as cursor:
                # Lock the account so parallel attempts cannot bypass lockout.
                cursor.execute(
                    """
                    SELECT user_id, name, username, role, is_active,
                           failed_attempts,
                           (locked_until > CURRENT_TIMESTAMP) AS is_locked,
                           (locked_until <= CURRENT_TIMESTAMP) AS lock_expired,
                           (crypt(%s, password_hash) = password_hash) AS password_matches,
                           (security_pin_hash IS NOT NULL
                            AND crypt(%s, security_pin_hash) = security_pin_hash) AS pin_matches
                      FROM user_account
                     WHERE username = %s
                     FOR UPDATE
                    """,
                    (password, pin, username),
                )
                account = cursor.fetchone()

                if account is None:
                    _write_activity(cursor, None, "admin_login_failure")
                    error_message = "Incorrect username, password, or security PIN."
                else:
                    (
                        user_id,
                        name,
                        account_username,
                        role,
                        is_active,
                        failed_attempts,
                        is_locked,
                        lock_expired,
                        password_matches,
                        pin_matches,
                    ) = account

                    if role != ADMIN_ROLE:
                        _write_activity(cursor, user_id, "admin_login_role_mismatch")
                        error_message = "This is not an Admin account."
                    elif not is_active:
                        _write_activity(cursor, user_id, "admin_login_failure")
                        error_message = "This administrator account is disabled."
                    elif is_locked:
                        _write_activity(cursor, user_id, "admin_login_failure")
                        error_message = "Account locked, try again later."
                    else:
                        if lock_expired:
                            failed_attempts = 0
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = 0, locked_until = NULL
                                 WHERE user_id = %s
                                """,
                                (user_id,),
                            )

                        if not (password_matches and pin_matches):
                            failed_attempts += 1
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = %s,
                                       locked_until = CASE
                                           WHEN %s >= %s
                                           THEN CURRENT_TIMESTAMP + INTERVAL '15 minutes'
                                           ELSE NULL
                                       END
                                 WHERE user_id = %s
                                """,
                                (failed_attempts, failed_attempts, MAX_FAILED_ATTEMPTS, user_id),
                            )
                            _write_activity(cursor, user_id, "admin_login_failure")
                            error_message = (
                                "Account locked, try again later."
                                if failed_attempts >= MAX_FAILED_ATTEMPTS
                                else "Incorrect username, password, or security PIN."
                            )
                        else:
                            cursor.execute(
                                """
                                UPDATE user_account
                                   SET failed_attempts = 0, locked_until = NULL
                                 WHERE user_id = %s
                                """,
                                (user_id,),
                            )
                            _write_activity(cursor, user_id, "admin_login_success")
                            result = AdminIdentity(
                                user_id, name, account_username, role
                            )
    finally:
        connection.close()

    if error_message:
        raise AuthenticationError(error_message)
    return result


def reset_admin_credentials(username, recovery_key, new_password, new_pin):
    """Verify the recovery key, replace credentials, and rotate the key."""
    username = username.strip()
    if not username or not recovery_key:
        raise ValueError("Enter your username and recovery key.")
    validate_password(new_password)
    validate_pin(new_pin)

    new_recovery_key = generate_recovery_key()
    connection = get_connection()
    error_message = None
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, name, username, role, is_active,
                           failed_attempts,
                           (locked_until > CURRENT_TIMESTAMP) AS is_locked,
                           (locked_until <= CURRENT_TIMESTAMP) AS lock_expired,
                           (crypt(%s, recovery_key_hash) = recovery_key_hash)
                               AS recovery_key_matches
                      FROM user_account
                     WHERE username = %s AND role = %s
                     FOR UPDATE
                    """,
                    (recovery_key, username, ADMIN_ROLE),
                )
                account = cursor.fetchone()

                if account is None:
                    _write_activity(cursor, None, "admin_recovery_failure")
                    error_message = "The username or recovery key is not valid."
                else:
                    (
                        user_id,
                        name,
                        account_username,
                        role,
                        is_active,
                        failed_attempts,
                        is_locked,
                        lock_expired,
                        recovery_key_matches,
                    ) = account

                    if not is_active:
                        _write_activity(cursor, user_id, "admin_recovery_failure")
                        error_message = "This administrator account is disabled."
                    elif is_locked:
                        _write_activity(cursor, user_id, "admin_recovery_failure")
                        error_message = "Account locked, try again later."
                    elif not recovery_key_matches:
                        if lock_expired:
                            failed_attempts = 0
                        failed_attempts += 1
                        cursor.execute(
                            """
                            UPDATE user_account
                               SET failed_attempts = %s,
                                   locked_until = CASE
                                       WHEN %s >= %s
                                       THEN CURRENT_TIMESTAMP + INTERVAL '15 minutes'
                                       ELSE NULL
                                   END
                             WHERE user_id = %s
                            """,
                            (failed_attempts, failed_attempts, MAX_FAILED_ATTEMPTS, user_id),
                        )
                        _write_activity(cursor, user_id, "admin_recovery_failure")
                        error_message = (
                            "Account locked, try again later."
                            if failed_attempts >= MAX_FAILED_ATTEMPTS
                            else "The username or recovery key is not valid."
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE user_account
                               SET password_hash = crypt(%s, gen_salt('bf')),
                                   security_pin_hash = crypt(%s, gen_salt('bf')),
                                   recovery_key_hash = crypt(%s, gen_salt('bf')),
                                   failed_attempts = 0,
                                   locked_until = NULL
                             WHERE user_id = %s
                            """,
                            (new_password, new_pin, new_recovery_key, user_id),
                        )
                        _write_activity(cursor, user_id, "admin_recovery_success")
    finally:
        connection.close()

    if error_message:
        raise AuthenticationError(error_message)
    identity = AdminIdentity(user_id, name, account_username, role)
    return identity, new_recovery_key


# ===== Window-Function Reports & Additional Department Services =====

def report_top_donors(actor_id):
    """Rank donors by total donated quantity using DENSE_RANK()."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT
                        d.name AS donor_name,
                        d.type AS donor_type,
                        COALESCE(SUM(di.quantity), 0) AS total_donated_quantity,
                        COUNT(DISTINCT don.donation_id) AS total_donations,
                        DENSE_RANK() OVER (ORDER BY COALESCE(SUM(di.quantity), 0) DESC) AS rank
                    FROM donor d
                    LEFT JOIN donation don ON don.donor_id = d.donor_id
                    LEFT JOIN donation_item di ON di.donation_id = don.donation_id
                    GROUP BY d.donor_id, d.name, d.type
                    ORDER BY rank, d.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def report_average_delivery_time(actor_id):
    """Calculate average dispatch and delivery time by region using window aggregates."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT
                        r.name AS region_name,
                        COUNT(s.shipment_id) AS total_shipments,
                        ROUND(AVG(EXTRACT(EPOCH FROM (s.dispatch_date - q.request_date)) / 3600)::numeric, 2) AS avg_hours_to_dispatch
                    FROM shipment s
                    JOIN request q ON q.request_id = s.request_id
                    JOIN camp c ON c.camp_id = q.camp_id
                    JOIN region r ON r.region_id = c.region_id
                    GROUP BY r.region_id, r.name
                    ORDER BY r.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def report_camp_shortfall(actor_id):
    """Rank camps by total unmet resource shortfall using RANK() OVER ()."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT
                        c.name AS camp_name,
                        r.name AS region_name,
                        c.population,
                        res.name AS resource_name,
                        res.unit,
                        (c.population * res.daily_need_per_person * 3) AS three_day_need,
                        COALESCE(SUM(qi.quantity), 0) AS pending_quantity,
                        GREATEST(0, (c.population * res.daily_need_per_person * 3) - COALESCE(SUM(qi.quantity), 0)) AS shortfall,
                        RANK() OVER (ORDER BY GREATEST(0, (c.population * res.daily_need_per_person * 3) - COALESCE(SUM(qi.quantity), 0)) DESC) AS rank
                    FROM camp c
                    JOIN region r ON r.region_id = c.region_id
                    CROSS JOIN resource res
                    LEFT JOIN request q ON q.camp_id = c.camp_id AND q.status = 'Pending'
                    LEFT JOIN request_item qi ON qi.request_id = q.request_id AND qi.resource_id = res.resource_id
                    WHERE c.status = 'Active' AND res.daily_need_per_person > 0
                    GROUP BY c.camp_id, c.name, r.name, c.population, res.resource_id, res.name, res.unit, res.daily_need_per_person
                    ORDER BY rank, c.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def _require_admin_or_staff(cursor, actor_id):
    """Verify an active Staff or Admin identity."""
    cursor.execute(
        "SELECT role, is_active FROM user_account WHERE user_id = %s",
        (actor_id,),
    )
    row = cursor.fetchone()
    if not row or not row[1] or row[0] not in ("Admin", "Staff"):
        raise AuthenticationError("You do not have permission.")


def list_camps_detail(actor_id):
    """List camps with region, district, population, and status for Camp Relief staff."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT c.camp_id, c.name, r.name, r.district, c.population, c.status
                      FROM camp c JOIN region r USING (region_id)
                     ORDER BY r.name, c.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def list_volunteers(actor_id):
    """List local contact and volunteer records for Camp Relief staff."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT lc.local_contact_id, lc.name, lc.phone_number,
                           lc.contact_type, r.name, lc.description, lc.is_active
                      FROM local_contact lc JOIN region r USING (region_id)
                     ORDER BY r.name, lc.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def list_donors(actor_id):
    """List donors, donor details, and contribution counts for Donations staff."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT d.donor_id, d.name, d.phone, d.type,
                           COUNT(don.donation_id) AS donation_count
                      FROM donor d
                      LEFT JOIN donation don USING (donor_id)
                     GROUP BY d.donor_id, d.name, d.phone, d.type
                     ORDER BY d.name
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def list_all_donations(actor_id):
    """List all donations with donor name, warehouse, date, and supply summary."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin_or_staff(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT don.donation_id, don.donation_date, d.name, w.name,
                           COALESCE(string_agg(res.name || ': ' || di.quantity, ', '), 'No items')
                      FROM donation don
                      JOIN donor d USING (donor_id)
                      JOIN warehouse w USING (warehouse_id)
                      LEFT JOIN donation_item di USING (donation_id)
                      LEFT JOIN resource res USING (resource_id)
                     GROUP BY don.donation_id, don.donation_date, d.name, w.name
                     ORDER BY don.donation_date DESC
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()


def toggle_local_contact_active(actor_id, contact_id):
    """Toggle is_active status of a local contact row as Admin."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                _set_activity_actor(cursor, actor_id)
                cursor.execute(
                    "UPDATE local_contact SET is_active = NOT is_active WHERE local_contact_id = %s",
                    (contact_id,),
                )
    finally:
        connection.close()


def toggle_helpline_active(actor_id, helpline_id):
    """Toggle is_active status of a helpline row as Admin."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                _set_activity_actor(cursor, actor_id)
                cursor.execute(
                    "UPDATE helpline SET is_active = NOT is_active WHERE helpline_id = %s",
                    (helpline_id,),
                )
    finally:
        connection.close()


def activity_log_rows(actor_id):
    """Fetch recent activity log entries for Admin audit review."""
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                _require_admin(cursor, actor_id)
                cursor.execute(
                    """
                    SELECT al.log_id, al.logged_at, COALESCE(u.username, 'System') AS actor,
                           al.action, al.table_name, al.record_id
                      FROM activity_log al
                      LEFT JOIN user_account u USING (user_id)
                     ORDER BY al.logged_at DESC, al.log_id DESC
                     LIMIT 100
                    """
                )
                return cursor.fetchall()
    finally:
        connection.close()

