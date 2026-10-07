"""Analytical reports page displaying window-function SQL results."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    report_average_delivery_time,
    report_camp_shortfall,
    report_top_donors,
)


def _staff_home(app, identity):
    if identity.role == "Admin":
        from relieflink.start import AdminHomePage
        app.show_page(AdminHomePage, identity)
    else:
        from relieflink.start import StaffHomePage
        app.show_page(StaffHomePage, identity)


class AnalyticalReportsPage(ttk.Frame):
    """Show window-function analytical reports: Top Donors, Avg Delivery Time, Camp Shortfalls."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(28, 20))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(self, text="Analytical Reports", font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self,
            text="SQL Window-Function Analytics (DENSE_RANK, AVG OVER, RANK OVER)",
            foreground="#607D8B",
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky="nsew")

        # Tab 1: Top Donors
        self.donors_frame = ttk.Frame(self.notebook, padding=10)
        self.donors_frame.columnconfigure(0, weight=1)
        self.donors_frame.rowconfigure(0, weight=1)
        self.donors_list = tk.Listbox(self.donors_frame, font=("Segoe UI", 10))
        self.donors_list.grid(row=0, column=0, sticky="nsew")
        self.notebook.add(self.donors_frame, text="Top Donors (DENSE_RANK)")

        # Tab 2: Average Delivery Time
        self.delivery_frame = ttk.Frame(self.notebook, padding=10)
        self.delivery_frame.columnconfigure(0, weight=1)
        self.delivery_frame.rowconfigure(0, weight=1)
        self.delivery_list = tk.Listbox(self.delivery_frame, font=("Segoe UI", 10))
        self.delivery_list.grid(row=0, column=0, sticky="nsew")
        self.notebook.add(self.delivery_frame, text="Delivery Times (AVG OVER)")

        # Tab 3: Camps Ranked by Shortfall
        self.shortfall_frame = ttk.Frame(self.notebook, padding=10)
        self.shortfall_frame.columnconfigure(0, weight=1)
        self.shortfall_frame.rowconfigure(0, weight=1)
        self.shortfall_list = tk.Listbox(self.shortfall_frame, font=("Segoe UI", 10))
        self.shortfall_list.grid(row=0, column=0, sticky="nsew")
        self.notebook.add(self.shortfall_frame, text="Camp Shortfalls (RANK)")

        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=3, column=0, sticky="w", pady=4
        )

        controls = ttk.Frame(self)
        controls.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(controls, text="Refresh Reports", command=self.load_all).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            controls,
            text="Back to Home",
            command=lambda: _staff_home(app, identity),
        ).pack(side="left")

        self.load_all()

    def load_all(self):
        self.error.set("")
        try:
            # 1. Load Top Donors
            donors = report_top_donors(self.identity.user_id)
            self.donors_list.delete(0, tk.END)
            for donor_name, donor_type, total_qty, donations_count, rank in donors:
                self.donors_list.insert(
                    tk.END,
                    f"Rank #{rank} | {donor_name} ({donor_type}) — Total Qty: {total_qty} — Donations: {donations_count}",
                )
            if not donors:
                self.donors_list.insert(tk.END, "No donor records found.")

            # 2. Load Delivery Times
            deliveries = report_average_delivery_time(self.identity.user_id)
            self.delivery_list.delete(0, tk.END)
            for region_name, count, avg_dispatch_hrs in deliveries:
                self.delivery_list.insert(
                    tk.END,
                    f"Region: {region_name} | Shipments: {count} | Avg Dispatch Time: {avg_dispatch_hrs or 0} hrs",
                )
            if not deliveries:
                self.delivery_list.insert(tk.END, "No shipment delivery data yet.")

            # 3. Load Camp Shortfalls
            shortfalls = report_camp_shortfall(self.identity.user_id)
            self.shortfall_list.delete(0, tk.END)
            for camp_name, region_name, pop, res_name, unit, need, pending, shortfall, rank in shortfalls:
                self.shortfall_list.insert(
                    tk.END,
                    f"Rank #{rank} | {camp_name} ({region_name}) — {res_name}: Shortfall = {shortfall} {unit} (Need: {need}, Pending: {pending})",
                )
            if not shortfalls:
                self.shortfall_list.insert(tk.END, "No active camp shortfall records.")

        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load analytical reports. Check database connection.")
                print(f"ReliefLink report load error: {error}")
