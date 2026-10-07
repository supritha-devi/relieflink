"""Stage 2 Tkinter screens for administrator setup and sign-in."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    admin_is_configured,
    authenticate_admin,
    authenticate_staff,
    authenticate_user,
    change_staff_credentials,
    create_first_admin,
    create_staff,
    list_departments,
    list_staff,
    public_relief_information,
    register_user,
    require_department,
    reset_admin_credentials,
    update_staff,
)

SESSION_TIMEOUT_MS = 10 * 60 * 1000


NAVY = "#12355B"
BLUE = "#1F6AA5"
BACKGROUND = "#F5F7FA"
TEXT = "#263238"
MUTED = "#607D8B"
GREEN = "#2E7D32"


class ReliefLinkApp(tk.Tk):
    """A small page navigator for the current administrator-authentication stage."""

    def __init__(self):
        super().__init__()
        self.title("ReliefLink — Disaster Relief Management")
        self.geometry("760x720")
        self.minsize(620, 600)
        self.configure(background=BACKGROUND)

        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.style.configure("TFrame", background=BACKGROUND)
        self.style.configure("TLabel", background=BACKGROUND, foreground=TEXT, font=("Segoe UI", 11))
        self.style.configure("Title.TLabel", font=("Segoe UI", 27, "bold"), foreground=NAVY)
        self.style.configure("Subtitle.TLabel", font=("Segoe UI", 11), foreground=MUTED)
        self.style.configure("Heading.TLabel", font=("Segoe UI", 19, "bold"), foreground=NAVY)
        self.style.configure(
            "TButton",
            font=("Segoe UI", 11),
            padding=(14, 10),
            background=BLUE,
            foreground="white",
            borderwidth=0,
        )
        self.style.map(
            "TButton",
            background=[("active", NAVY), ("disabled", "#CFD8DC")],
            foreground=[("disabled", MUTED)],
        )
        self.style.configure(
            "Primary.TButton",
            background=NAVY,
            foreground="white",
            font=("Segoe UI", 11, "bold"),
        )
        self.style.map("Primary.TButton", background=[("active", BLUE)])
        self.style.configure(
            "Emergency.TButton",
            background="#C62828",
            foreground="white",
            font=("Segoe UI", 11, "bold"),
        )
        self.style.map("Emergency.TButton", background=[("active", "#8E0000")])
        self.style.configure("TEntry", padding=8, font=("Segoe UI", 11))

        self.current_page = None
        self.session_identity = None
        self._session_after_id = None
        self.start_message = ""
        self.bind_all("<KeyPress>", self._reset_session_timeout, add="+")
        self.bind_all("<Button>", self._reset_session_timeout, add="+")
        self.show_page(StartPage)

    def start_session(self, identity):
        """Start the shared ten-minute inactivity timer after a successful login."""
        self.session_identity = identity
        self._reset_session_timeout()

    def _reset_session_timeout(self, _event=None):
        if self.session_identity is None:
            return
        if self._session_after_id is not None:
            self.after_cancel(self._session_after_id)
        self._session_after_id = self.after(SESSION_TIMEOUT_MS, self._session_expired)

    def _session_expired(self):
        self._session_after_id = None
        self.logout("Your session expired due to inactivity.")

    def logout(self, message=""):
        """Destroy the protected page and return to the public start page."""
        if self._session_after_id is not None:
            self.after_cancel(self._session_after_id)
            self._session_after_id = None
        self.session_identity = None
        self.start_message = message
        self.show_page(StartPage)

    def show_page(self, page_type, *args):
        """Replace the current full-screen page with a new page."""
        if self.current_page is not None:
            self.current_page.destroy()
        self.current_page = page_type(self, *args)
        self.current_page.pack(fill="both", expand=True)


class BasePage(ttk.Frame):
    """Shared page layout and inline, non-modal validation messages."""

    def __init__(self, app):
        super().__init__(app, padding=(36, 28))
        self.app = app
        self.columnconfigure(0, weight=1)

    def header(self, title, helper=None):
        ttk.Label(self, text=title, style="Heading.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        if helper:
            ttk.Label(
                self,
                text=helper,
                style="Subtitle.TLabel",
                wraplength=660,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(0, 20))

    def error_label(self, row):
        self.error_text = tk.StringVar(value="")
        self.error_label_widget = ttk.Label(
            self, textvariable=self.error_text, foreground="#C62828", wraplength=660
        )
        self.error_label_widget.grid(row=row, column=0, sticky="w", pady=(14, 8))

    def show_error(self, message):
        self.error_text.set(message)

    def show_database_error(self, error):
        self.show_error(
            "ReliefLink could not complete the database operation. Check the "
            "PostgreSQL service, password, and required SQL migration, then try again."
        )
        print(f"ReliefLink database error: {error}")


class StartPage(BasePage):
    """Choose the admin setup, login, or recovery form."""

    def __init__(self, app):
        super().__init__(app)
        ttk.Label(self, text="ReliefLink", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(20, 4)
        )
        ttk.Label(
            self,
            text="Disaster Relief Resource Distribution and Management System",
            style="Subtitle.TLabel",
            wraplength=660,
        ).grid(row=1, column=0, sticky="w", pady=(0, 44))
        ttk.Label(self, text="Who are you?", style="Heading.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 20)
        )
        ttk.Button(
            self,
            text="Admin — First Time",
            style="Primary.TButton",
            command=lambda: self.app.show_page(AdminSetupPage),
        ).grid(row=3, column=0, sticky="ew", pady=7)
        ttk.Button(
            self,
            text="Admin — Already Set Up",
            command=lambda: self.app.show_page(AdminLoginPage),
        ).grid(row=4, column=0, sticky="ew", pady=7)
        ttk.Button(
            self,
            text="Reset Admin Password with Recovery Key",
            command=lambda: self.app.show_page(AdminRecoveryPage),
        ).grid(row=5, column=0, sticky="ew", pady=7)
        ttk.Button(
            self,
            text="Normal User — Log in",
            command=lambda: self.app.show_page(UserLoginPage),
        ).grid(row=6, column=0, sticky="ew", pady=7)
        ttk.Button(
            self,
            text="Normal User — Register",
            command=lambda: self.app.show_page(UserRegisterPage),
        ).grid(row=7, column=0, sticky="ew", pady=7)
        ttk.Button(
            self,
            text="Staff",
            command=lambda: self.app.show_page(StaffLoginPage),
        ).grid(row=8, column=0, sticky="ew", pady=7)
        ttk.Label(
            self,
            text=self.app.start_message
            or "Administrator and user roles are verified against the database.",
            style="Subtitle.TLabel",
            wraplength=660,
        ).grid(row=9, column=0, sticky="w", pady=(24, 0))


class FormPage(BasePage):
    """Build consistently labeled fields without putting SQL in GUI handlers."""

    def add_fields(self, fields, start_row=2):
        self.values = {}
        for offset, (key, label, secret) in enumerate(fields):
            row = start_row + offset * 2
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(6, 2))
            variable = tk.StringVar()
            entry = ttk.Entry(
                self,
                textvariable=variable,
                show="*" if secret else "",
            )
            entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 4))
            self.values[key] = variable
        return start_row + len(fields) * 2

    def value(self, field):
        return self.values[field].get()

    def back_button(self, row):
        ttk.Button(
            self, text="Back", command=lambda: self.app.show_page(StartPage)
        ).grid(row=row, column=0, sticky="w", pady=(16, 0))


class AdminSetupPage(FormPage):
    """Collect the first administrator and present its new recovery key once."""

    def __init__(self, app):
        super().__init__(app)
        self.header(
            "Set up administrator",
            "The Admin is the disaster management officer. Create the only "
            "administrator account for this ReliefLink database.",
        )
        row = self.add_fields(
            [
                ("name", "Full name", False),
                ("officer_id", "Officer ID", False),
                ("username", "Username (3–32 letters, numbers, dots, dashes, or underscores)", False),
                ("password", "Password (12+ characters with upper/lowercase, a number, and a symbol)", True),
                ("confirm_password", "Confirm password", True),
                ("pin", "Security PIN (6 digits)", True),
                ("confirm_pin", "Confirm security PIN", True),
            ]
        )
        self.error_label(row)
        ttk.Button(
            self,
            text="Create administrator",
            style="Primary.TButton",
            command=self.submit,
        ).grid(row=row + 1, column=0, sticky="ew", pady=(5, 0))
        self.back_button(row + 2)

    def submit(self):
        if any(not self.value(field).strip() for field in self.values):
            self.show_error("Fill in every box.")
            return
        if self.value("password") != self.value("confirm_password"):
            self.show_error("Passwords do not match.")
            return
        if self.value("pin") != self.value("confirm_pin"):
            self.show_error("Security PINs do not match.")
            return
        try:
            if admin_is_configured():
                self.show_error("An administrator already exists. Please log in.")
                return
            identity, recovery_key = create_first_admin(
                self.value("name"),
                self.value("officer_id"),
                self.value("username"),
                self.value("password"),
                self.value("pin"),
            )
            self.app.show_page(RecoveryKeyPage, identity, recovery_key, True)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class AdminLoginPage(FormPage):
    """Authenticate an administrator using database role, password, and PIN."""

    def __init__(self, app):
        super().__init__(app)
        self.header("Admin login", "Enter the username, password, and security PIN for your Admin account.")
        row = self.add_fields(
            [
                ("username", "Username", False),
                ("password", "Password", True),
                ("pin", "Security PIN", True),
            ]
        )
        self.error_label(row)
        ttk.Button(
            self,
            text="Sign in as administrator",
            style="Primary.TButton",
            command=self.submit,
        ).grid(row=row + 1, column=0, sticky="ew")
        ttk.Button(
            self,
            text="Forgot password? Use recovery key",
            command=lambda: self.app.show_page(AdminRecoveryPage),
        ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))
        self.back_button(row + 3)

    def submit(self):
        try:
            identity = authenticate_admin(
                self.value("username"),
                self.value("password"),
                self.value("pin"),
            )
            self.app.start_session(identity)
            self.app.show_page(AdminHomePage, identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class UserLoginPage(FormPage):
    """Sign in using a normal user's username/email and password."""

    def __init__(self, app):
        super().__init__(app)
        self.header("Normal user login", "Sign in to view your ReliefLink account.")
        row = self.add_fields(
            [
                ("identifier", "Username or email", False),
                ("password", "Password", True),
            ]
        )
        self.error_label(row)
        ttk.Button(
            self,
            text="Log in",
            style="Primary.TButton",
            command=self.submit,
        ).grid(row=row + 1, column=0, sticky="ew")
        ttk.Button(
            self,
            text="Create a normal user account",
            command=lambda: self.app.show_page(UserRegisterPage),
        ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))
        self.back_button(row + 3)

    def submit(self):
        try:
            identity = authenticate_user(
                self.value("identifier"),
                self.value("password"),
            )
            self.app.start_session(identity)
            self.app.show_page(UserHomePage, identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class UserRegisterPage(FormPage):
    """Create a public account that is always assigned the User role."""

    def __init__(self, app):
        super().__init__(app)
        self.header(
            "Create a normal user account",
            "New registrations always receive the Normal User role.",
        )
        row = self.add_fields(
            [
                ("name", "Full name", False),
                ("phone", "Phone number", False),
                ("username", "Username", False),
                ("email", "Email address", False),
                ("password", "Password (12+ characters with upper/lowercase, a number, and a symbol)", True),
                ("confirm_password", "Confirm password", True),
            ]
        )
        self.error_label(row)
        ttk.Button(
            self,
            text="Register",
            style="Primary.TButton",
            command=self.submit,
        ).grid(row=row + 1, column=0, sticky="ew")
        self.back_button(row + 2)

    def submit(self):
        if any(not self.value(field).strip() for field in self.values):
            self.show_error("Fill in every box.")
            return
        if self.value("password") != self.value("confirm_password"):
            self.show_error("Passwords do not match.")
            return
        try:
            identity = register_user(
                self.value("name"),
                self.value("phone"),
                self.value("username"),
                self.value("email"),
                self.value("password"),
            )
            self.app.start_session(identity)
            self.app.show_page(UserHomePage, identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class StaffLoginPage(FormPage):
    """Sign in staff and load their assigned department from the database."""

    def __init__(self, app):
        super().__init__(app)
        self.header("Staff login", "Enter your assigned staff username, password, and security PIN.")
        row = self.add_fields(
            [
                ("username", "Username", False),
                ("password", "Password", True),
                ("pin", "Security PIN", True),
            ]
        )
        self.error_label(row)
        ttk.Button(self, text="Staff sign in", style="Primary.TButton",
                   command=self.submit).grid(row=row + 1, column=0, sticky="ew")
        self.back_button(row + 2)

    def submit(self):
        try:
            identity = authenticate_staff(
                self.value("username"), self.value("password"), self.value("pin")
            )
            self.app.start_session(identity)
            if identity.must_change_password:
                self.app.show_page(StaffCredentialChangePage, identity, True)
            else:
                self.app.show_page(StaffHomePage, identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class StaffCredentialChangePage(FormPage):
    """Force the first-login staff member to choose their own password and PIN."""

    def __init__(self, app, identity, forced=False):
        super().__init__(app)
        self.identity = identity
        self.forced = forced
        self.header(
            "Set your own password and PIN",
            "Choose credentials only you know. Both are required before "
            "continuing." if forced else "Update your staff credentials.",
        )
        row = self.add_fields(
            [
                ("old_password", "Current password", True),
                ("old_pin", "Current security PIN", True),
                ("new_password", "New password (12+ characters)", True),
                ("confirm_password", "Confirm new password", True),
                ("new_pin", "New security PIN (6 digits)", True),
                ("confirm_pin", "Confirm new security PIN", True),
            ]
        )
        self.error_label(row)
        ttk.Button(self, text="Save new credentials", style="Primary.TButton",
                   command=self.submit).grid(row=row + 1, column=0, sticky="ew")
        if not forced:
            ttk.Button(self, text="Back to staff home",
                       command=lambda: self.app.show_page(StaffHomePage, identity)
                       ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))

    def submit(self):
        if any(not self.value(field) for field in self.values):
            self.show_error("Fill in every box.")
            return
        if self.value("new_password") != self.value("confirm_password"):
            self.show_error("Passwords do not match.")
            return
        if self.value("new_pin") != self.value("confirm_pin"):
            self.show_error("Security PINs do not match.")
            return
        try:
            change_staff_credentials(
                self.identity.user_id,
                self.value("old_password"),
                self.value("old_pin"),
                self.value("new_password"),
                self.value("new_pin"),
            )
            updated_identity = type(self.identity)(
                self.identity.user_id,
                self.identity.name,
                self.identity.username,
                self.identity.department_id,
                self.identity.department_name,
                "Staff",
                False,
            )
            self.app.start_session(updated_identity)
            self.app.show_page(StaffHomePage, updated_identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class StaffHomePage(BasePage):
    """Present only the staff department's options and shared helpline desk."""

    def __init__(self, app, identity):
        super().__init__(app)
        self.identity = identity
        self.header("ReliefLink — Staff", f"Department: {identity.department_name}")
        ttk.Label(self, text=f"Welcome, {identity.name}.", style="Heading.TLabel"
                  ).grid(row=2, column=0, sticky="w", pady=(4, 16))
        options = {
            "Logistics": ("Pending requests", "Shipment history"),
            "Warehouse": ("Warehouse stock", "Low-stock alerts", "Receive donation"),
            "Camp Relief": ("Camp details", "Camp requests", "Volunteers"),
            "Donations": ("Donors", "Donation history"),
        }.get(identity.department_name, ())
        row = 3
        for option in options:
            ttk.Button(
                self,
                text=option,
                command=lambda page=option: self.open_department_page(page),
            ).grid(row=row, column=0, sticky="ew", pady=4)
            row += 1
        ttk.Button(
            self, text="Helpline desk — Messages and Call log",
            command=self.open_helpline_desk,
        ).grid(row=row, column=0, sticky="ew", pady=(14, 4))
        row += 1
        ttk.Button(
            self, text="Analytical Reports (Window Functions)",
            style="Primary.TButton",
            command=self.open_reports,
        ).grid(row=row, column=0, sticky="ew", pady=4)
        row += 1
        ttk.Button(
            self, text="Change my password and PIN",
            command=lambda: self.app.show_page(StaffCredentialChangePage, identity, False),
        ).grid(row=row, column=0, sticky="ew", pady=4)
        row += 1
        ttk.Button(self, text="Log out", command=self.app.logout
                   ).grid(row=row, column=0, sticky="ew", pady=4)

    def open_reports(self):
        from relieflink.reports import AnalyticalReportsPage
        self.app.show_page(AnalyticalReportsPage, self.identity)

    def open_department_page(self, page_name):
        try:
            require_department(self.identity.user_id, self.identity.department_name)
            if self.identity.department_name == "Logistics":
                from relieflink.logistics import (
                    PendingRequestsPage,
                    ShipmentHistoryPage,
                )

                if page_name == "Pending requests":
                    self.app.show_page(PendingRequestsPage, self.identity)
                    return
                if page_name == "Shipment history":
                    self.app.show_page(ShipmentHistoryPage, self.identity)
                    return
            if self.identity.department_name == "Warehouse":
                from relieflink.supply import (
                    StaffReceiveDonationPage,
                    StaffWarehousePage,
                )

                if page_name == "Warehouse stock":
                    self.app.show_page(StaffWarehousePage, self.identity, False)
                    return
                if page_name == "Low-stock alerts":
                    self.app.show_page(StaffWarehousePage, self.identity, True)
                    return
                if page_name == "Receive donation":
                    self.app.show_page(StaffReceiveDonationPage, self.identity)
                    return
            if self.identity.department_name == "Camp Relief":
                from relieflink.camp import (
                    CampDetailsPage,
                    CampRequestsPage,
                    VolunteersPage,
                )

                if page_name == "Camp details":
                    self.app.show_page(CampDetailsPage, self.identity)
                    return
                if page_name == "Camp requests":
                    self.app.show_page(CampRequestsPage, self.identity)
                    return
                if page_name == "Volunteers":
                    self.app.show_page(VolunteersPage, self.identity)
                    return
            if self.identity.department_name == "Donations":
                from relieflink.donations_staff import (
                    StaffDonationHistoryPage,
                    StaffDonorsPage,
                )

                if page_name == "Donors":
                    self.app.show_page(StaffDonorsPage, self.identity)
                    return
                if page_name == "Donation history":
                    self.app.show_page(StaffDonationHistoryPage, self.identity)
                    return
            self.app.show_page(StaffFeaturePage, self.identity, page_name,
                               self.identity.department_name)
        except AuthenticationError as error:
            self.app.logout(str(error))
        except psycopg2.Error as error:
            self.app.logout("Could not verify staff permissions. Please sign in again.")
            print(f"ReliefLink staff authorization error: {error}")

    def open_helpline_desk(self):
        from relieflink.helpline import StaffInboxPage

        self.app.show_page(StaffInboxPage, self.identity)


class StaffFeaturePage(BasePage):
    """Department page placeholder with server-side permission recheck."""

    def __init__(self, app, identity, page_name, department):
        super().__init__(app)
        self.header(page_name, f"Authorized department: {department}")
        ttk.Label(
            self,
            text="This department feature is being added in its scheduled project stage.",
            style="Subtitle.TLabel",
            wraplength=650,
        ).grid(row=2, column=0, sticky="w", pady=(12, 18))
        ttk.Button(self, text="Back to staff home",
                   command=lambda: self.app.show_page(StaffHomePage, identity)
                   ).grid(row=3, column=0, sticky="ew")


class UserHomePage(BasePage):
    """Show a normal user's own account and public relief information."""

    def __init__(self, app, identity):
        super().__init__(app)
        self.header("ReliefLink", f"Welcome, {identity.name}.")
        ttk.Label(
            self,
            text="You are signed in as a Normal User.",
            style="Subtitle.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(0, 16))
        ttk.Button(
            self,
            text="View public disasters and helplines",
            style="Primary.TButton",
            command=lambda: self.app.show_page(PublicInformationPage, identity),
        ).grid(row=3, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="I want to donate",
            command=self.open_donation_page,
        ).grid(row=4, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="I need supplies",
            command=lambda: self.open_request_page("Normal"),
        ).grid(row=5, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="URGENT — I need help",
            style="Emergency.TButton",
            command=lambda: self.open_request_page("Urgent"),
        ).grid(row=6, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="Where is my help?",
            command=self.open_request_history,
        ).grid(row=7, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="My donation history",
            command=self.open_donation_history,
        ).grid(row=8, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="Message the relief team",
            command=self.open_helpline_page,
        ).grid(row=9, column=0, sticky="ew", pady=6)
        ttk.Button(
            self,
            text="Log out",
            command=self.app.logout,
        ).grid(row=10, column=0, sticky="ew", pady=6)

    def open_donation_page(self):
        from relieflink.supply import UserDonationPage

        self.app.show_page(UserDonationPage, self.identity)

    def open_donation_history(self):
        from relieflink.supply import DonationHistoryPage

        self.app.show_page(DonationHistoryPage, self.identity)

    def open_request_page(self, priority):
        from relieflink.requests import UserRequestPage

        self.app.show_page(UserRequestPage, self.identity, priority)

    def open_request_history(self):
        from relieflink.requests import UserRequestHistoryPage

        self.app.show_page(UserRequestHistoryPage, self.identity)

    def open_helpline_page(self):
        from relieflink.helpline import UserHelplinePage

        self.app.show_page(UserHelplinePage, self.identity)


class PublicInformationPage(BasePage):
    """Show public incidents, camps, and helplines without private stock values."""

    def __init__(self, app, identity):
        super().__init__(app)
        self.header("Public relief information")
        try:
            disasters, helplines = public_relief_information()
        except psycopg2.Error as error:
            app.logout()
            app.start_message = (
                "Could not load public relief information. Check the database connection."
            )
            print(f"ReliefLink public information database error: {error}")
            return

        emergency = tk.Frame(self, bg="#C62828", padx=16, pady=10)
        emergency.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        tk.Label(
            emergency,
            text="EMERGENCY  |  If life is in danger, call 112 first.",
            bg="#C62828",
            fg="white",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        ).pack(fill="x")

        body = ttk.Frame(self)
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        canvas = tk.Canvas(body, background=BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content = ttk.Frame(canvas, padding=(2, 2, 12, 8))
        content_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.columnconfigure(0, weight=1)

        def resize_content(event):
            canvas.itemconfigure(content_id, width=event.width)

        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind("<Configure>", resize_content)

        disasters_section = ttk.LabelFrame(
            content, text="Active disasters and camps", padding=10
        )
        disasters_section.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        disasters_section.columnconfigure(0, weight=1)
        if disasters:
            for index, (name, kind, severity, region, district, camp, population) in enumerate(disasters):
                card = ttk.Frame(disasters_section, padding=(8, 5))
                card.grid(row=index, column=0, sticky="ew", pady=2)
                ttk.Label(
                    card, text=f"{name}  ·  {kind}  ·  {severity}",
                    font=("Segoe UI", 10, "bold"),
                ).pack(anchor="w")
                place = f"{region}, {district}"
                if camp:
                    place += f"  ·  {camp}  ·  {population} people"
                ttk.Label(card, text=place, foreground=MUTED).pack(anchor="w")
        else:
            ttk.Label(
                disasters_section, text="No active disaster information is available."
            ).grid(row=0, column=0, sticky="w")

        levels = ("National", "State", "District", "Local", "Camp")
        for section_index, level in enumerate(levels, start=1):
            section = ttk.LabelFrame(content, text=f"{level} helplines", padding=10)
            section.grid(row=section_index, column=0, sticky="ew", pady=4)
            section.columnconfigure(0, weight=1)
            matching = [entry for entry in helplines if entry[2] == level]
            if not matching:
                ttk.Label(section, text=f"No {level.lower()} numbers listed.").grid(
                    row=0, column=0, sticky="w"
                )
                continue

            for entry_index, entry in enumerate(matching):
                name, phone, _, region, camp, contact_type = entry
                card = ttk.Frame(section, padding=(9, 7))
                card.grid(row=entry_index, column=0, sticky="ew", pady=3)
                card.columnconfigure(0, weight=1)
                ttk.Label(
                    card, text=name, font=("Segoe UI", 10, "bold")
                ).grid(row=0, column=0, sticky="w")
                ttk.Label(
                    card,
                    text=phone,
                    foreground=BLUE,
                    font=("Segoe UI", 13, "bold"),
                ).grid(row=1, column=0, sticky="w", pady=(2, 0))
                details = "  ·  ".join(
                    value for value in (contact_type, region, camp) if value
                )
                if details:
                    ttk.Label(card, text=details, foreground=MUTED).grid(
                        row=2, column=0, sticky="w"
                    )

        ttk.Button(
            self,
            text="Back to home",
            command=lambda: self.app.show_page(UserHomePage, identity),
        ).grid(row=4, column=0, sticky="ew", pady=(10, 0))


class AdminRecoveryPage(FormPage):
    """Replace both Admin credentials using the saved recovery key."""

    def __init__(self, app):
        super().__init__(app)
        self.header(
            "Reset administrator credentials",
            "Use the recovery key shown during setup (or the latest credential "
            "reset) to choose a new password and PIN.",
        )
        row = self.add_fields(
            [
                ("username", "Admin username", False),
                ("recovery_key", "Recovery key", True),
                ("password", "New password", True),
                ("confirm_password", "Confirm new password", True),
                ("pin", "New security PIN (6 digits)", True),
                ("confirm_pin", "Confirm new security PIN", True),
            ]
        )
        self.error_label(row)
        ttk.Button(
            self,
            text="Reset credentials",
            style="Primary.TButton",
            command=self.submit,
        ).grid(row=row + 1, column=0, sticky="ew")
        self.back_button(row + 2)

    def submit(self):
        if any(not self.value(field).strip() for field in self.values):
            self.show_error("Fill in every box.")
            return
        if self.value("password") != self.value("confirm_password"):
            self.show_error("Passwords do not match.")
            return
        if self.value("pin") != self.value("confirm_pin"):
            self.show_error("Security PINs do not match.")
            return
        try:
            identity, recovery_key = reset_admin_credentials(
                self.value("username"),
                self.value("recovery_key"),
                self.value("password"),
                self.value("pin"),
            )
            self.app.show_page(RecoveryKeyPage, identity, recovery_key, False)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class RecoveryKeyPage(BasePage):
    """Show a random recovery key only in the successful setup/reset screen."""

    def __init__(self, app, identity, recovery_key, first_setup):
        super().__init__(app)
        self.recovery_key = recovery_key
        self.header(
            "Save your recovery key",
            "This key is shown only once. Store it somewhere safe. It is not "
            "saved in plain text, and a credential reset will replace it.",
        )
        ttk.Label(
            self,
            text=f"Administrator: {identity.name} ({identity.username})",
        ).grid(row=2, column=0, sticky="w", pady=(0, 12))
        self.key_text = tk.StringVar(value=recovery_key)
        self.key_entry = ttk.Entry(self, textvariable=self.key_text, state="readonly")
        self.key_entry.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.message = tk.StringVar(
            value="Copy and save this key before continuing."
        )
        ttk.Label(self, textvariable=self.message, foreground=GREEN).grid(
            row=4, column=0, sticky="w", pady=(0, 10)
        )
        ttk.Button(self, text="Copy recovery key", command=self.copy_key).grid(
            row=5, column=0, sticky="w", pady=(0, 14)
        )
        ttk.Button(
            self,
            text="Continue to Admin login",
            style="Primary.TButton",
            command=self.finish,
        ).grid(row=6, column=0, sticky="ew")

    def copy_key(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.recovery_key)
        self.message.set("Recovery key copied. Save it in a secure place.")

    def finish(self):
        self.recovery_key = ""
        self.key_text.set("")
        self.app.show_page(AdminLoginPage)


class AdminHomePage(BasePage):
    """Confirm database-backed administrator access for this build stage."""

    def __init__(self, app, identity):
        super().__init__(app)
        self.identity = identity
        self.header("ReliefLink", "Administrator sign-in successful.")
        ttk.Label(
            self,
            text=f"Welcome, {identity.name}.",
            style="Heading.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(12, 8))
        ttk.Label(
            self,
            text="Your administrator role was verified by the database. "
            "Use the management tools below to coordinate relief operations.",
            style="Subtitle.TLabel",
            wraplength=660,
        ).grid(row=3, column=0, sticky="w", pady=(0, 22))
        ttk.Button(
            self,
            text="Manage Staff",
            style="Primary.TButton",
            command=lambda: self.app.show_page(StaffManagementPage, identity),
        ).grid(row=4, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            self,
            text="Manage disasters, places, camps and helplines",
            command=lambda: self.open_disaster_catalog(identity),
        ).grid(row=5, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            self,
            text="Manage resources and warehouses",
            command=lambda: self.open_supply_catalog(identity),
        ).grid(row=6, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            self,
            text="Helpline desk — Messages and Call log",
            command=self.open_helpline_desk,
        ).grid(row=7, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            self,
            text="Analytical Reports (Window Functions)",
            style="Primary.TButton",
            command=self.open_reports,
        ).grid(row=8, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            self,
            text="Log out",
            command=self.app.logout,
        ).grid(row=9, column=0, sticky="ew")

    def open_reports(self):
        from relieflink.reports import AnalyticalReportsPage
        self.app.show_page(AnalyticalReportsPage, self.identity)

    def open_disaster_catalog(self, identity):
        from relieflink.admin import AdminCatalogHub

        self.app.show_page(AdminCatalogHub, identity)

    def open_supply_catalog(self, identity):
        from relieflink.supply import AdminSupplyHub

        self.app.show_page(AdminSupplyHub, identity)

    def open_helpline_desk(self):
        from relieflink.helpline import StaffInboxPage

        self.app.show_page(StaffInboxPage, self.identity)


class StaffManagementPage(BasePage):
    """Admin-only staff list and staff-creation entry point."""

    def __init__(self, app, identity):
        super().__init__(app)
        self.identity = identity
        self.header("Manage Staff", "Staff access and departments are controlled by the Admin.")
        ttk.Button(self, text="Add staff", style="Primary.TButton",
                   command=lambda: self.app.show_page(AddStaffPage, identity)
                   ).grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.staff_list = tk.Listbox(self, height=12, font=("Segoe UI", 10))
        self.staff_list.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)
        controls = ttk.Frame(self)
        controls.grid(row=4, column=0, sticky="ew", pady=8)
        ttk.Button(controls, text="Change department", command=self.change_department
                   ).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="Enable / disable", command=self.toggle_active
                   ).pack(side="left", padx=6)
        ttk.Button(controls, text="Reset password and PIN",
                   command=lambda: self.reset_credentials()
                   ).pack(side="left", padx=6)
        ttk.Button(self, text="Back to Admin home",
                   command=lambda: self.app.show_page(AdminHomePage, identity)
                   ).grid(row=5, column=0, sticky="ew")
        self.load_staff()

    def load_staff(self):
        try:
            self.staff_rows = list_staff(self.identity.user_id)
            self.staff_list.delete(0, tk.END)
            for row in self.staff_rows:
                user_id, name, username, department, active, created = row
                state = "Active" if active else "Disabled"
                self.staff_list.insert(tk.END, f"{name} ({username}) — {department} — {state}")
        except (AuthenticationError, psycopg2.Error) as error:
            self.show_database_error(error)

    def selected_staff(self):
        selected = self.staff_list.curselection()
        if not selected:
            self.show_error("Choose a staff member first.")
            return None
        return self.staff_rows[selected[0]]

    def change_department(self):
        staff = self.selected_staff()
        if staff:
            self.app.show_page(StaffDepartmentPage, self.identity, staff)

    def toggle_active(self):
        staff = self.selected_staff()
        if not staff:
            return
        try:
            update_staff(self.identity.user_id, staff[0], active=not staff[4])
            self.load_staff()
        except (AuthenticationError, ValueError, psycopg2.Error) as error:
            self.show_error(str(error))

    def reset_credentials(self):
        staff = self.selected_staff()
        if staff:
            self.app.show_page(StaffResetPage, self.identity, staff)


class AddStaffPage(FormPage):
    """Create a staff account in an Admin-selected department."""

    def __init__(self, app, identity):
        super().__init__(app)
        self.identity = identity
        self.header("Add staff", "Temporary credentials must be changed at first sign-in.")
        try:
            self.departments = list_departments()
        except psycopg2.Error as error:
            self.show_database_error(error)
            self.departments = []
        row = self.add_fields(
            [
                ("name", "Name", False),
                ("phone", "Phone", False),
                ("username", "Username", False),
                ("password", "Temporary password (12+ characters)", True),
                ("pin", "Temporary PIN (6 digits)", True),
            ]
        )
        ttk.Label(self, text="Department").grid(row=row, column=0, sticky="w", pady=(6, 2))
        self.department_names = [name for _, name in self.departments]
        self.department_choice = ttk.Combobox(
            self, values=self.department_names, state="readonly"
        )
        self.department_choice.grid(row=row + 1, column=0, sticky="ew")
        self.error_label(row + 2)
        ttk.Button(self, text="Create staff account", style="Primary.TButton",
                   command=self.submit).grid(row=row + 3, column=0, sticky="ew")
        ttk.Button(self, text="Back to staff list",
                   command=lambda: self.app.show_page(StaffManagementPage, identity)
                   ).grid(row=row + 4, column=0, sticky="ew", pady=(8, 0))

    def submit(self):
        try:
            index = self.department_choice.current()
            if index < 0:
                raise ValueError("Choose a department.")
            staff_id = create_staff(
                self.identity.user_id,
                self.value("name"),
                self.value("phone"),
                self.value("username"),
                self.value("password"),
                self.value("pin"),
                self.departments[index][0],
            )
            self.app.show_page(StaffManagementPage, self.identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)


class StaffDepartmentPage(BasePage):
    """Reassign one staff member to an existing department."""

    def __init__(self, app, identity, staff):
        super().__init__(app)
        self.identity, self.staff = identity, staff
        self.header("Change staff department", f"Selected staff: {staff[1]} ({staff[2]})")
        try:
            self.departments = list_departments()
        except psycopg2.Error as error:
            self.show_database_error(error)
            self.departments = []
        self.choice = ttk.Combobox(self, values=[name for _, name in self.departments],
                                   state="readonly")
        self.choice.grid(row=2, column=0, sticky="ew", pady=12)
        self.error_label(3)
        ttk.Button(self, text="Save department", style="Primary.TButton",
                   command=self.submit).grid(row=4, column=0, sticky="ew")
        ttk.Button(self, text="Back",
                   command=lambda: self.app.show_page(StaffManagementPage, identity)
                   ).grid(row=5, column=0, sticky="ew", pady=8)

    def submit(self):
        index = self.choice.current()
        if index < 0:
            self.show_error("Choose a department.")
            return
        try:
            update_staff(self.identity.user_id, self.staff[0],
                         department_id=self.departments[index][0])
            self.app.show_page(StaffManagementPage, self.identity)
        except (AuthenticationError, ValueError, psycopg2.Error) as error:
            self.show_error(str(error))


class StaffResetPage(FormPage):
    """Issue temporary staff credentials and require a first-login change."""

    def __init__(self, app, identity, staff):
        super().__init__(app)
        self.identity, self.staff = identity, staff
        self.header("Reset staff credentials", f"New temporary credentials for {staff[1]}.")
        row = self.add_fields(
            [
                ("password", "Temporary password (12+ characters)", True),
                ("pin", "Temporary PIN (6 digits)", True),
            ]
        )
        self.error_label(row)
        ttk.Button(self, text="Reset credentials", style="Primary.TButton",
                   command=self.submit).grid(row=row + 1, column=0, sticky="ew")
        ttk.Button(self, text="Back",
                   command=lambda: self.app.show_page(StaffManagementPage, identity)
                   ).grid(row=row + 2, column=0, sticky="ew", pady=8)

    def submit(self):
        try:
            update_staff(
                self.identity.user_id, self.staff[0],
                temporary_password=self.value("password"),
                temporary_pin=self.value("pin"),
            )
            self.app.show_page(StaffManagementPage, self.identity)
        except (AuthenticationError, ValueError) as error:
            self.show_error(str(error))
        except psycopg2.Error as error:
            self.show_database_error(error)
