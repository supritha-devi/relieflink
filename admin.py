"""Administrator setup pages for disaster areas and public contacts."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    activity_log_rows,
    admin_catalog_choices,
    admin_catalog_rows,
    create_camp,
    create_disaster,
    create_disaster_area,
    create_helpline,
    create_local_contact,
    create_region,
    toggle_helpline_active,
    toggle_local_contact_active,
)


CATALOGS = (
    "disasters",
    "places",
    "affected areas",
    "camps",
    "local contacts",
    "helplines",
)

FIELDS = {
    "disasters": (
        ("name", "Disaster name", "entry"),
        ("type", "Type", "entry"),
        ("severity", "Severity", ("Low", "Moderate", "High", "Critical")),
        ("start_date", "Start date (YYYY-MM-DD)", "entry"),
        ("end_date", "End date (optional, YYYY-MM-DD)", "entry"),
        ("description", "Description", "entry"),
    ),
    "places": (
        ("name", "Place name", "entry"),
        ("district", "District", "entry"),
        ("state", "State (optional)", "entry"),
    ),
    "affected areas": (
        ("disaster", "Disaster", "disasters"),
        ("place", "Affected place", "places"),
    ),
    "camps": (
        ("affected_area", "Affected disaster and place", "affected_areas"),
        ("name", "Camp name", "entry"),
        ("population", "Camp population", "entry"),
    ),
    "local contacts": (
        ("place", "Place", "places"),
        ("name", "Contact name", "entry"),
        ("contact_type", "Contact type", ("Person", "Group")),
        ("phone", "Phone number", "entry"),
        ("description", "Description (optional)", "entry"),
    ),
    "helplines": (
        ("name", "Helpline name", "entry"),
        ("phone", "Phone number", "entry"),
        ("level", "Level", ("National", "State", "District", "Local", "Camp")),
        ("contact_type", "Contact type (for local or camp numbers)", ("", "Person", "Group")),
        ("region", "Place (for district or local numbers)", "optional_places"),
        ("camp", "Camp (for camp numbers)", "optional_camps"),
    ),
}


class AdminCatalogHub(ttk.Frame):
    """Open an administrator-managed disaster or public-contact catalog."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(32, 24))
        self.app = app
        self.identity = identity
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Disaster areas and helplines",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text="Create disasters and affected places, then add camps, local contacts, and helplines.",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=(6, 18))
        for index, catalog in enumerate(CATALOGS):
            ttk.Button(
                self,
                text=f"Manage {catalog.title()}",
                command=lambda selected=catalog: self.app.show_page(
                    AdminCatalogPage, identity, selected
                ),
            ).grid(row=index + 2, column=0, sticky="ew", pady=4)
        
        row_offset = len(CATALOGS) + 2
        ttk.Button(
            self,
            text="System Activity Log",
            style="Primary.TButton",
            command=lambda: self.app.show_page(AdminActivityLogPage, identity),
        ).grid(row=row_offset, column=0, sticky="ew", pady=(10, 4))

        ttk.Button(
            self,
            text="Back to Admin home",
            command=lambda: self.open_admin_home(identity),
        ).grid(row=row_offset + 1, column=0, sticky="ew", pady=(10, 0))

    def open_admin_home(self, identity):
        from relieflink.start import AdminHomePage

        self.app.show_page(AdminHomePage, identity)


class AdminCatalogPage(ttk.Frame):
    """List a catalog and open its add form, always checking Admin permissions."""

    def __init__(self, app, identity, catalog):
        super().__init__(app, padding=(32, 24))
        self.app, self.identity, self.catalog = app, identity, catalog
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text=f"Manage {catalog.title()}",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text="Changes are written to PostgreSQL and recorded in the activity log.",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))
        self.listbox = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.listbox.grid(row=2, column=0, sticky="nsew")
        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, sticky="ew", pady=12)
        ttk.Button(buttons, text=f"Add {catalog[:-1] if catalog.endswith('s') else catalog}",
                   command=lambda: self.app.show_page(
                       AdminCatalogFormPage, identity, catalog
                   )).pack(side="left", padx=(0, 8))

        if catalog in ("local contacts", "helplines"):
            ttk.Button(buttons, text="Enable / Disable Selected",
                       command=self.toggle_selected).pack(side="left", padx=(0, 8))

        ttk.Button(buttons, text="Back to Admin home",
                   command=lambda: self.open_admin_home(identity)
                   ).pack(side="left")
        self.load_rows()

    def toggle_selected(self):
        selected = self.listbox.curselection()
        if not selected or not hasattr(self, "rows") or not self.rows:
            return
        row_id = self.rows[selected[0]][0]
        try:
            if self.catalog == "local contacts":
                toggle_local_contact_active(self.identity.user_id, row_id)
            elif self.catalog == "helplines":
                toggle_helpline_active(self.identity.user_id, row_id)
            self.load_rows()
        except (AuthenticationError, psycopg2.Error) as error:
            print(f"ReliefLink admin toggle error: {error}")
        self.load_rows()

    def open_admin_home(self, identity):
        from relieflink.start import AdminHomePage

        self.app.show_page(AdminHomePage, identity)

    def load_rows(self):
        try:
            self.rows = admin_catalog_rows(self.identity.user_id, self.catalog)
            self.listbox.delete(0, tk.END)
            for row in self.rows:
                self.listbox.insert(tk.END, " — ".join(
                    str(value) for value in row if value is not None
                ))
            if not self.rows:
                self.listbox.insert(tk.END, "No records yet.")
        except AuthenticationError as error:
            self.app.logout(str(error))
        except psycopg2.Error as error:
            self.listbox.delete(0, tk.END)
            self.listbox.insert(tk.END, "Could not load this catalog. Check the database.")
            print(f"ReliefLink admin catalog database error: {error}")


class AdminCatalogFormPage(ttk.Frame):
    """Validated catalog form that uses database-backed dropdowns and callbacks."""

    def __init__(self, app, identity, catalog):
        super().__init__(app, padding=(32, 24))
        self.app, self.identity, self.catalog = app, identity, catalog
        self.columnconfigure(0, weight=1)
        self.inputs = {}
        self.choices = {}
        ttk.Label(self, text=f"Add {catalog[:-1] if catalog.endswith('s') else catalog}",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="Required fields are checked before saving.",
                  wraplength=650).grid(row=1, column=0, sticky="w", pady=(5, 10))
        self.configured_fields = FIELDS[catalog]
        self.error = tk.StringVar(value="")
        for index, (key, label, kind) in enumerate(self.configured_fields):
            row = 2 + index * 2
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(5, 1))
            if kind == "entry":
                variable = tk.StringVar()
                widget = ttk.Entry(self, textvariable=variable)
                self.inputs[key] = variable
            elif isinstance(kind, tuple):
                variable = tk.StringVar()
                widget = ttk.Combobox(self, textvariable=variable, values=kind,
                                      state="readonly")
                self.inputs[key] = variable
            else:
                widget = ttk.Combobox(self, state="readonly")
                rows = self._choice_rows(key, kind)
                self.choices[key] = (widget, rows)
                widget.configure(values=[item[-1] for item in rows])
                if kind.startswith("optional_") and rows:
                    widget.current(0)
            widget.grid(row=row + 1, column=0, sticky="ew")

        action_row = 2 + len(self.configured_fields) * 2
        ttk.Label(self, textvariable=self.error, foreground="#C62828",
                  wraplength=650).grid(row=action_row, column=0, sticky="w", pady=8)
        ttk.Button(self, text="Save", command=self.submit).grid(
            row=action_row + 1, column=0, sticky="ew"
        )
        ttk.Button(
            self, text="Back",
            command=lambda: self.app.show_page(AdminCatalogPage, identity, catalog),
        ).grid(row=action_row + 2, column=0, sticky="ew", pady=(8, 0))

    def _choice_rows(self, key, choice_type):
        optional = choice_type.startswith("optional_")
        source = choice_type.removeprefix("optional_")
        try:
            rows = admin_catalog_choices(self.identity.user_id, source)
            return [(None, "— None —")] + rows if optional else rows
        except (AuthenticationError, psycopg2.Error) as error:
            self.error.set("Could not load choices. Verify Admin access and database setup.")
            print(f"ReliefLink admin dropdown error: {error}")
            return []

    def _selected_id(self, key):
        widget, rows = self.choices[key]
        index = widget.current()
        if index < 0:
            raise ValueError("Choose every required option.")
        return rows[index]

    def submit(self):
        try:
            values = {key: variable.get().strip() for key, variable in self.inputs.items()}
            if any(not value for key, value in values.items()
                   if key not in ("end_date", "description", "state", "contact_type")):
                raise ValueError("Fill in every required box.")

            actor_id = self.identity.user_id
            if self.catalog == "disasters":
                create_disaster(actor_id, values["name"], values["type"],
                                values["severity"], values["start_date"],
                                values["end_date"], values["description"])
            elif self.catalog == "places":
                create_region(actor_id, values["name"], values["district"], values["state"])
            elif self.catalog == "affected areas":
                disaster = self._selected_id("disaster")
                region = self._selected_id("place")
                create_disaster_area(actor_id, disaster[0], region[0])
            elif self.catalog == "camps":
                area = self._selected_id("affected_area")
                create_camp(actor_id, area[0], area[1], values["name"], values["population"])
            elif self.catalog == "local contacts":
                region = self._selected_id("place")
                create_local_contact(actor_id, region[0], values["name"],
                                     values["contact_type"], values["phone"],
                                     values["description"])
            elif self.catalog == "helplines":
                level = values["level"]
                region_id = None
                camp_id = None
                contact_type = None
                if level in ("District", "Local"):
                    region = admin_catalog_choices(actor_id, "places")
                    if not region:
                        raise ValueError("Add a place before this helpline.")
                    region_id = region[0][0]
                if level == "Camp":
                    camps = admin_catalog_choices(actor_id, "camps")
                    if not camps:
                        raise ValueError("Add a camp before this helpline.")
                    camp_id = camps[0][0]
                create_helpline(actor_id, values["name"], values["phone"],
                                level, contact_type, region_id, camp_id)

            self.app.show_page(AdminCatalogPage, self.identity, self.catalog)
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not save this record. Check the selected values.")
            print(f"ReliefLink admin catalog save error: {error}")


class AdminActivityLogPage(ttk.Frame):
    """Display system database activity log for Admin review."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="System Activity Log", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.log_list = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.log_list.grid(row=1, column=0, sticky="nsew", pady=12)

        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w", pady=4
        )

        controls = ttk.Frame(self)
        controls.grid(row=3, column=0, sticky="ew")
        ttk.Button(controls, text="Refresh", command=self.load).pack(side="left", padx=(0, 6))
        ttk.Button(
            controls,
            text="Back to Admin Home",
            command=lambda: self.open_admin_home(),
        ).pack(side="left")

        self.load()

    def open_admin_home(self):
        from relieflink.start import AdminHomePage
        self.app.show_page(AdminHomePage, self.identity)

    def load(self):
        try:
            rows = activity_log_rows(self.identity.user_id)
            self.log_list.delete(0, tk.END)
            for log_id, logged_at, actor, action, table_name, record_id in rows:
                rec = f"Record #{record_id}" if record_id else "Global"
                self.log_list.insert(
                    tk.END,
                    f"[{logged_at:%Y-%m-%d %H:%M:%S}] Log #{log_id} — Actor: {actor} — Action: {action} — Table: {table_name} ({rec})",
                )
            if not rows:
                self.log_list.insert(tk.END, "No activity log entries.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load system activity log.")
                print(f"ReliefLink activity log error: {error}")

