"""Donations department screens: donor directory and donation history processing."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    list_all_donations,
    list_donors,
)


def _staff_home(app, identity):
    from relieflink.start import StaffHomePage
    app.show_page(StaffHomePage, identity)


class StaffDonorsPage(ttk.Frame):
    """View registered donors and total donation contributions."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Donor Directory", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.donors_list = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.donors_list.grid(row=1, column=0, sticky="nsew", pady=12)

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
            rows = list_donors(self.identity.user_id)
            self.donors_list.delete(0, tk.END)
            for donor_id, name, phone, dtype, count in rows:
                phone_display = phone or "No phone"
                self.donors_list.insert(
                    tk.END,
                    f"Donor #{donor_id}: {name} ({dtype}) — Phone: {phone_display} — Total Donations: {count}",
                )
            if not rows:
                self.donors_list.insert(tk.END, "No donors recorded yet.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load donor directory.")
                print(f"ReliefLink donor directory load error: {error}")


class StaffDonationHistoryPage(ttk.Frame):
    """View and inspect all incoming supply donations across warehouses."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Donations Processing & History", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.donations_list = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.donations_list.grid(row=1, column=0, sticky="nsew", pady=12)

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
            rows = list_all_donations(self.identity.user_id)
            self.donations_list.delete(0, tk.END)
            for don_id, don_date, donor_name, warehouse_name, items in rows:
                self.donations_list.insert(
                    tk.END,
                    f"Donation RL-{don_id} — {don_date:%Y-%m-%d %H:%M} — Donor: {donor_name} — Drop-off: {warehouse_name} — Items: {items}",
                )
            if not rows:
                self.donations_list.insert(tk.END, "No donation records found.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load donations history.")
                print(f"ReliefLink donation history error: {error}")
