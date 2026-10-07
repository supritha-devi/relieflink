"""Camp Relief department pages: camp details, camp supply requests, and volunteer management."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    list_camps_detail,
    list_volunteers,
    public_affected_places,
    create_local_contact,
)


def _staff_home(app, identity):
    from relieflink.start import StaffHomePage
    app.show_page(StaffHomePage, identity)


class CampDetailsPage(ttk.Frame):
    """View active camps, locations, population, and status."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Relief Camps Details", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.camps_list = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.camps_list.grid(row=1, column=0, sticky="nsew", pady=12)

        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w", pady=4
        )

        controls = ttk.Frame(self)
        controls.grid(row=3, column=0, sticky="ew")
        ttk.Button(controls, text="Refresh", command=self.load).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="Back to Staff Home", command=lambda: _staff_home(app, identity)).pack(
            side="left"
        )

        self.load()

    def load(self):
        try:
            rows = list_camps_detail(self.identity.user_id)
            self.camps_list.delete(0, tk.END)
            for camp_id, name, region, district, population, status in rows:
                self.camps_list.insert(
                    tk.END,
                    f"Camp #{camp_id}: {name} — {region}, {district} — Population: {population} — Status: {status}",
                )
            if not rows:
                self.camps_list.insert(tk.END, "No camp records found.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load camp details.")
                print(f"ReliefLink camp details load error: {error}")


class CampRequestsPage(ttk.Frame):
    """View requests associated with relief camps or initiate a camp request."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text="Camp Relief Requests", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self,
            text="Camp Relief staff can initiate or track camp supply requests for active camps.",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        ttk.Button(
            self,
            text="Submit Urgent Supply Request for Camp",
            style="Primary.TButton",
            command=self.open_urgent_request,
        ).grid(row=2, column=0, sticky="ew", pady=6)

        ttk.Button(
            self,
            text="View Pending Logistics Requests",
            command=self.open_logistics_pending,
        ).grid(row=3, column=0, sticky="ew", pady=6)

        ttk.Button(
            self, text="Back to Staff Home", command=lambda: _staff_home(app, identity)
        ).grid(row=4, column=0, sticky="ew", pady=(12, 0))

    def open_urgent_request(self):
        from relieflink.requests import UserRequestPage
        self.app.show_page(UserRequestPage, self.identity, "Urgent")

    def open_logistics_pending(self):
        from relieflink.logistics import PendingRequestsPage
        self.app.show_page(PendingRequestsPage, self.identity)


class VolunteersPage(ttk.Frame):
    """View and register relief volunteers / local contact persons."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Volunteers & Local Contacts", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.volunteer_list = tk.Listbox(self, height=14, font=("Segoe UI", 10))
        self.volunteer_list.grid(row=1, column=0, sticky="nsew", pady=12)

        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w", pady=4
        )

        controls = ttk.Frame(self)
        controls.grid(row=3, column=0, sticky="ew")
        ttk.Button(controls, text="Register New Volunteer", command=self.open_add_form).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(controls, text="Refresh", command=self.load).pack(side="left", padx=6)
        ttk.Button(controls, text="Back to Staff Home", command=lambda: _staff_home(app, identity)).pack(
            side="left", padx=6
        )

        self.load()

    def load(self):
        try:
            rows = list_volunteers(self.identity.user_id)
            self.volunteer_list.delete(0, tk.END)
            for cid, name, phone, ctype, region, desc, active in rows:
                status = "Active" if active else "Disabled"
                self.volunteer_list.insert(
                    tk.END,
                    f"{name} ({ctype}) — Phone: {phone} — Region: {region} — Status: {status} ({desc or 'No desc'})",
                )
            if not rows:
                self.volunteer_list.insert(tk.END, "No volunteers recorded yet.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load volunteers list.")
                print(f"ReliefLink volunteer list error: {error}")

    def open_add_form(self):
        self.app.show_page(AddVolunteerPage, self.identity)


class AddVolunteerPage(ttk.Frame):
    """Add a volunteer / local contact for a region."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text="Register Volunteer / Local Contact", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.fields = {}
        row = 1
        for key, label in (
            ("name", "Full Name"),
            ("phone", "Phone Number"),
            ("description", "Role / Notes (optional)"),
        ):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(4, 1))
            val = tk.StringVar()
            ttk.Entry(self, textvariable=val).grid(row=row + 1, column=0, sticky="ew")
            self.fields[key] = val
            row += 2

        try:
            self.places = public_affected_places()
        except psycopg2.Error:
            self.places = []

        ttk.Label(self, text="Region / Place").grid(row=row, column=0, sticky="w", pady=(4, 1))
        self.place_choice = ttk.Combobox(
            self, values=[p[1] for p in self.places], state="readonly"
        )
        self.place_choice.grid(row=row + 1, column=0, sticky="ew")
        row += 2

        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=row, column=0, sticky="w", pady=6
        )

        ttk.Button(self, text="Save Volunteer", style="Primary.TButton", command=self.submit).grid(
            row=row + 1, column=0, sticky="ew"
        )
        ttk.Button(
            self, text="Back to Volunteers List", command=lambda: app.show_page(VolunteersPage, identity)
        ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))

    def submit(self):
        name = self.fields["name"].get().strip()
        phone = self.fields["phone"].get().strip()
        desc = self.fields["description"].get().strip()
        place_idx = self.place_choice.current()

        if not name or not phone or place_idx < 0:
            self.error.set("Fill in name, phone, and select a region.")
            return

        try:
            create_local_contact(
                self.identity.user_id,
                self.places[place_idx][0],
                name,
                "Person",
                phone,
                desc,
            )
            self.app.show_page(VolunteersPage, self.identity)
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not save volunteer record.")
            print(f"ReliefLink add volunteer error: {error}")
