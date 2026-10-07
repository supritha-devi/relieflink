"""Stage 6 resource, warehouse, donation, and inventory pages."""

from decimal import Decimal
import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    admin_supply_rows,
    create_resource,
    create_warehouse,
    department_stock,
    donate_supplies,
    list_departments,
    public_dropoff_warehouses,
    public_supply_resources,
    staff_record_donation,
    user_donation_history,
)


def _return_to_user_home(app, identity):
    from relieflink.start import UserHomePage

    app.show_page(UserHomePage, identity)


def _return_to_admin_home(app, identity):
    from relieflink.start import AdminHomePage

    app.show_page(AdminHomePage, identity)


class AdminSupplyHub(ttk.Frame):
    """Admin navigation for resources and warehouses."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(32, 24))
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Resources and warehouses",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text="Manage the relief supplies and their drop-off locations.",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=(6, 18))
        for row, catalog in enumerate(("resources", "warehouses"), start=2):
            ttk.Button(
                self,
                text=f"Manage {catalog.title()}",
                command=lambda selected=catalog: app.show_page(
                    AdminSupplyListPage, identity, selected
                ),
            ).grid(row=row, column=0, sticky="ew", pady=5)
        ttk.Button(
            self, text="Back to Admin home",
            command=lambda: _return_to_admin_home(app, identity),
        ).grid(row=4, column=0, sticky="ew", pady=(14, 0))


class AdminSupplyListPage(ttk.Frame):
    """Display a protected resource or warehouse catalog."""

    def __init__(self, app, identity, catalog):
        super().__init__(app, padding=(32, 24))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.app, self.identity, self.catalog = app, identity, catalog
        ttk.Label(self, text=f"Manage {catalog.title()}",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.rows_view = tk.Listbox(self, height=15, font=("Segoe UI", 10))
        self.rows_view.grid(row=2, column=0, sticky="nsew", pady=(12, 12))
        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Button(
            actions, text=f"Add {catalog[:-1]}",
            command=lambda: app.show_page(AdminSupplyFormPage, identity, catalog),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions, text="Back",
            command=lambda: app.show_page(AdminSupplyHub, identity),
        ).pack(side="left")
        self.load()

    def load(self):
        try:
            rows = admin_supply_rows(self.identity.user_id, self.catalog)
            self.rows_view.delete(0, tk.END)
            for row in rows:
                self.rows_view.insert(tk.END, " — ".join(str(value) for value in row))
            if not rows:
                self.rows_view.insert(tk.END, "No records yet.")
        except AuthenticationError as error:
            self.app.logout(str(error))
        except psycopg2.Error as error:
            self.rows_view.insert(tk.END, "Could not load records. Check the database.")
            print(f"ReliefLink supply catalog error: {error}")


class AdminSupplyFormPage(ttk.Frame):
    """Add a resource or warehouse using Admin-authorized DB functions."""

    def __init__(self, app, identity, catalog):
        super().__init__(app, padding=(32, 24))
        self.app, self.identity, self.catalog = app, identity, catalog
        self.columnconfigure(0, weight=1)
        ttk.Label(
            self,
            text=f"Add {catalog[:-1]}",
            font=("Segoe UI", 19, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.fields = {}
        row = 1
        if catalog == "resources":
            self._entry("Name", "name", row); row += 2
            self._entry("Category", "category", row); row += 2
            self._entry("Unit", "unit", row); row += 2
            self._entry("Daily need per person (0 or greater)", "need", row); row += 2
        else:
            self._entry("Warehouse name", "name", row); row += 2
            self._entry("Capacity", "capacity", row); row += 2
            ttk.Label(self, text="Place").grid(row=row, column=0, sticky="w", pady=(4, 1))
            self.places = self._load_places()
            self.place_choice = ttk.Combobox(
                self, values=[name for _, name in self.places], state="readonly"
            )
            self.place_choice.grid(row=row + 1, column=0, sticky="ew")
            row += 2

        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828",
                  wraplength=650).grid(row=row, column=0, sticky="w", pady=8)
        ttk.Button(self, text="Save", command=self.submit).grid(
            row=row + 1, column=0, sticky="ew"
        )
        ttk.Button(
            self, text="Back to list",
            command=lambda: app.show_page(AdminSupplyListPage, identity, catalog),
        ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))

    def _entry(self, label, key, row):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(4, 1))
        value = tk.StringVar()
        ttk.Entry(self, textvariable=value).grid(row=row + 1, column=0, sticky="ew")
        self.fields[key] = value

    def _load_places(self):
        try:
            from relieflink.auth import supply_catalog_choices

            return supply_catalog_choices(self.identity.user_id, "places")
        except (AuthenticationError, psycopg2.Error) as error:
            self.error = tk.StringVar(
                value="Could not load places. Check the database and Admin access."
            )
            print(f"ReliefLink warehouse place lookup error: {error}")
            return []

    def submit(self):
        try:
            if self.catalog == "resources":
                create_resource(
                    self.identity.user_id,
                    self.fields["name"].get(),
                    self.fields["category"].get(),
                    self.fields["unit"].get(),
                    self.fields["need"].get(),
                )
            else:
                index = self.place_choice.current()
                if index < 0:
                    raise ValueError("Choose a place.")
                create_warehouse(
                    self.identity.user_id,
                    self.places[index][0],
                    self.fields["name"].get(),
                    self.fields["capacity"].get(),
                )
            self.app.show_page(AdminSupplyListPage, self.identity, self.catalog)
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not save the record. Check its values and migration setup.")
            print(f"ReliefLink supply save error: {error}")


class UserDonationPage(ttk.Frame):
    """Record a public donation at a need-tagged drop-off warehouse."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(32, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        ttk.Label(self, text="Donate supplies", font=("Segoe UI", 19, "bold")
                  ).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="Choose supplies and quantities, then pick a drop-off point.",
                  wraplength=650).grid(row=1, column=0, sticky="w", pady=(5, 10))
        self.errors = tk.StringVar(value="")
        try:
            self.resources = public_supply_resources()
            self.warehouses = public_dropoff_warehouses()
        except psycopg2.Error as error:
            self.resources, self.warehouses = [], []
            self.errors.set("Could not load donation choices. Check the database.")
            print(f"ReliefLink donation choices error: {error}")

        ttk.Label(self, text="Supplies to donate").grid(
            row=2, column=0, sticky="w", pady=(4, 2)
        )
        supplies = ttk.Frame(self)
        supplies.grid(row=3, column=0, sticky="ew")
        supplies.columnconfigure(1, weight=1)
        self.quantities = {}
        if self.resources:
            for index, (resource_id, name, unit) in enumerate(self.resources):
                ttk.Label(supplies, text=f"{name} ({unit})").grid(
                    row=index, column=0, sticky="w", padx=(0, 8), pady=3
                )
                quantity = tk.StringVar(value="0")
                ttk.Entry(supplies, textvariable=quantity, width=16).grid(
                    row=index, column=1, sticky="ew", pady=3
                )
                self.quantities[resource_id] = quantity
        else:
            ttk.Label(supplies, text="No supplies have been added yet.").grid(
                row=0, column=0, sticky="w"
            )

        row = 4
        ttk.Label(self, text="Drop-off point").grid(
            row=row, column=0, sticky="w", pady=(8, 2)
        )
        self.warehouse_choice = ttk.Combobox(
            self,
            values=[
                f"{name} — {region}, {district} — {tags}"
                for _, name, region, district, tags in self.warehouses
            ],
            state="readonly",
        )
        self.warehouse_choice.grid(row=row + 1, column=0, sticky="ew")
        ttk.Label(self, textvariable=self.errors, foreground="#C62828",
                  wraplength=650).grid(row=row + 2, column=0, sticky="w", pady=8)
        ttk.Button(self, text="Confirm donation", command=self.submit).grid(
            row=row + 3, column=0, sticky="ew"
        )
        ttk.Button(self, text="Back to home",
                   command=lambda: _return_to_user_home(app, identity)
                   ).grid(row=row + 4, column=0, sticky="ew", pady=(8, 0))

    def submit(self):
        try:
            selected_items = []
            for resource_id, value in self.quantities.items():
                amount = Decimal(value.get() or "0")
                if not amount.is_finite() or amount < 0:
                    raise ValueError("Enter a valid non-negative supply amount.")
                if amount > 0:
                    selected_items.append((resource_id, amount))
            warehouse_index = self.warehouse_choice.current()
            if warehouse_index < 0:
                raise ValueError("Choose a drop-off point.")
            donation_id = donate_supplies(
                self.identity.user_id,
                self.warehouses[warehouse_index][0],
                selected_items,
            )
            self.app.show_page(DonationThanksPage, self.identity, donation_id)
        except (AuthenticationError, ValueError, ArithmeticError) as error:
            self.errors.set(str(error))
        except psycopg2.Error as error:
            self.errors.set("Could not record your donation. Check the database and try again.")
            print(f"ReliefLink donation error: {error}")


class DonationThanksPage(ttk.Frame):
    """Confirm a donation and show its database identifier."""

    def __init__(self, app, identity, donation_id):
        super().__init__(app, padding=(36, 30))
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Thank you for your donation",
                  font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=f"Your donation reference is RL-{donation_id}.",
                  wraplength=650).grid(row=1, column=0, sticky="w", pady=12)
        ttk.Button(self, text="Back to home",
                   command=lambda: _return_to_user_home(app, identity)
                   ).grid(row=2, column=0, sticky="ew")


class DonationHistoryPage(ttk.Frame):
    """Display only the current user's donation history."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(32, 24))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="My donations",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        history = tk.Listbox(self, height=18, font=("Segoe UI", 10))
        history.grid(row=1, column=0, sticky="nsew", pady=12)
        try:
            rows = user_donation_history(identity.user_id)
            for donation_id, date, warehouse, items in rows:
                history.insert(tk.END, f"RL-{donation_id} — {date:%Y-%m-%d %H:%M} — "
                                       f"{warehouse} — {items}")
            if not rows:
                history.insert(tk.END, "You have not made any donations yet.")
        except (AuthenticationError, psycopg2.Error) as error:
            history.insert(tk.END, "Could not load your donation history.")
            print(f"ReliefLink donation history error: {error}")
        ttk.Button(self, text="Back to home",
                   command=lambda: _return_to_user_home(app, identity)
                   ).grid(row=2, column=0, sticky="ew")


class StaffWarehousePage(ttk.Frame):
    """Show exact warehouse inventory only after staff department revalidation."""

    def __init__(self, app, identity, alerts_only=False):
        super().__init__(app, padding=(32, 24))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        heading = "Low-stock alerts" if alerts_only else "Warehouse stock"
        ttk.Label(self, text=heading, font=("Segoe UI", 19, "bold")
                  ).grid(row=0, column=0, sticky="w")
        rows_box = tk.Listbox(self, height=18, font=("Segoe UI", 10))
        rows_box.grid(row=1, column=0, sticky="nsew", pady=12)
        try:
            rows = department_stock(identity.user_id, alerts_only=alerts_only)
            for row in rows:
                rows_box.insert(tk.END, " — ".join(str(value) for value in row))
            if not rows:
                rows_box.insert(tk.END, "No records to display.")
        except (AuthenticationError, psycopg2.Error) as error:
            app.logout("You do not have permission." if isinstance(
                error, AuthenticationError
            ) else "Could not verify Warehouse access.")
            print(f"ReliefLink warehouse access error: {error}")
            return
        ttk.Button(self, text="Back to staff home",
                   command=lambda: self._staff_home(app, identity)
                   ).grid(row=2, column=0, sticky="ew")

    @staticmethod
    def _staff_home(app, identity):
        from relieflink.start import StaffHomePage

        app.show_page(StaffHomePage, identity)


class StaffReceiveDonationPage(ttk.Frame):
    """Receive a named drop-off donation as authorized Warehouse staff."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(32, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.fields = {}
        ttk.Label(self, text="Receive donation",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        row = 1
        for key, label in (("name", "Donor name"), ("phone", "Donor phone")):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(5, 1))
            value = tk.StringVar()
            ttk.Entry(self, textvariable=value).grid(row=row + 1, column=0, sticky="ew")
            self.fields[key] = value
            row += 2
        try:
            self.warehouses = public_dropoff_warehouses()
            self.resources = public_supply_resources()
        except psycopg2.Error as error:
            self.warehouses, self.resources = [], []
            print(f"ReliefLink receive donation choices error: {error}")
        ttk.Label(self, text="Warehouse").grid(row=row, column=0, sticky="w", pady=(5, 1))
        self.warehouse_choice = ttk.Combobox(
            self,
            values=[f"{w[1]} — {w[2]}, {w[3]}" for w in self.warehouses],
            state="readonly",
        )
        self.warehouse_choice.grid(row=row + 1, column=0, sticky="ew")
        row += 2
        self.quantities = {}
        for resource_id, name, unit in self.resources:
            ttk.Label(self, text=f"{name} ({unit})").grid(
                row=row, column=0, sticky="w", pady=(4, 1)
            )
            value = tk.StringVar(value="0")
            ttk.Entry(self, textvariable=value).grid(row=row + 1, column=0, sticky="ew")
            self.quantities[resource_id] = value
            row += 2
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=row, column=0, sticky="w", pady=7
        )
        ttk.Button(self, text="Record received donation", command=self.submit
                   ).grid(row=row + 1, column=0, sticky="ew")
        ttk.Button(
            self, text="Back to Warehouse home",
            command=lambda: self._staff_home(app, identity),
        ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))

    @staticmethod
    def _staff_home(app, identity):
        from relieflink.start import StaffHomePage

        app.show_page(StaffHomePage, identity)

    def submit(self):
        try:
            selected = []
            for resource_id, variable in self.quantities.items():
                amount = Decimal(variable.get() or "0")
                if not amount.is_finite() or amount < 0:
                    raise ValueError("Enter valid non-negative amounts.")
                if amount > 0:
                    selected.append((resource_id, amount))
            warehouse_index = self.warehouse_choice.current()
            if warehouse_index < 0:
                raise ValueError("Choose a warehouse.")
            donation_id = staff_record_donation(
                self.identity.user_id,
                self.fields["name"].get(),
                self.fields["phone"].get(),
                self.warehouses[warehouse_index][0],
                selected,
            )
            self.error.set(f"Donation RL-{donation_id} received.")
        except (AuthenticationError, ValueError, ArithmeticError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not record donation. Check the database.")
            print(f"ReliefLink staff donation error: {error}")
