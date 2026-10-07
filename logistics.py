"""Logistics request allocation, shipment confirmation, and shipment history."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    dispatch_request,
    logistics_choices,
    logistics_pending_requests,
    logistics_shipment_history,
    update_shipment_status,
)


def _staff_home(app, identity):
    from relieflink.start import StaffHomePage

    app.show_page(StaffHomePage, identity)


class PendingRequestsPage(ttk.Frame):
    """Show urgent-first pending requests and start a stock allocation."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Pending requests",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.request_list = tk.Listbox(self, height=17, font=("Segoe UI", 10))
        self.request_list.grid(row=1, column=0, sticky="nsew", pady=12)
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828",
                  wraplength=650).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(self, text="Dispatch selected request",
                   command=self.open_dispatch).grid(row=3, column=0, sticky="ew")
        ttk.Button(self, text="Refresh",
                   command=self.load_requests).grid(row=4, column=0, sticky="ew", pady=6)
        ttk.Button(self, text="Back to staff home",
                   command=lambda: _staff_home(app, identity)
                   ).grid(row=5, column=0, sticky="ew")
        self.load_requests()

    def load_requests(self):
        try:
            self.rows = logistics_pending_requests(self.identity.user_id)
            self.request_list.delete(0, tk.END)
            for request_id, priority, created, camp, region, district, items in self.rows:
                self.request_list.insert(
                    tk.END,
                    f"RL-{request_id} — {priority} — {camp}, {region}, {district} — {items}",
                )
            if not self.rows:
                self.request_list.insert(tk.END, "No pending requests.")
        except AuthenticationError as error:
            self.app.logout(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not load pending requests. Check the database.")
            print(f"ReliefLink pending request error: {error}")

    def open_dispatch(self):
        selected = self.request_list.curselection()
        if not selected or not self.rows:
            self.error.set("Choose a pending request first.")
            return
        self.app.show_page(DispatchRequestPage, self.identity, self.rows[selected[0]])


class DispatchRequestPage(ttk.Frame):
    """Select a local warehouse, vehicle, and driver before confirming dispatch."""

    def __init__(self, app, identity, request_row):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity, self.request_row = app, identity, request_row
        self.columnconfigure(0, weight=1)
        request_id, priority, _, camp, region, district, items = request_row
        ttk.Label(
            self,
            text=f"Dispatch request RL-{request_id}",
            font=("Segoe UI", 19, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text=f"{priority}  ·  {camp}  ·  {region}, {district}\n{items}",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))
        try:
            self.warehouses, self.vehicles, self.drivers, requested_items = (
                logistics_choices(identity.user_id, request_id)
            )
        except (AuthenticationError, ValueError) as error:
            app.logout(str(error))
            return
        except psycopg2.Error as error:
            app.logout("Could not load dispatch choices. Check the database migrations.")
            print(f"ReliefLink dispatch choices error: {error}")
            return

        self._choice("Same-region warehouse", "warehouse", self.warehouses, 2)
        self._choice(
            "Vehicle",
            "vehicle",
            [(row[0], f"{row[1]} — {row[2]}") for row in self.vehicles],
            4,
        )
        self._choice(
            "Driver",
            "driver",
            [(row[0], row[1]) for row in self.drivers],
            6,
        )
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828",
                  wraplength=650).grid(row=8, column=0, sticky="w", pady=8)
        ttk.Button(self, text="Confirm dispatch", style="Primary.TButton",
                   command=self.submit).grid(row=9, column=0, sticky="ew")
        ttk.Button(
            self, text="Back to pending requests",
            command=lambda: app.show_page(PendingRequestsPage, identity),
        ).grid(row=10, column=0, sticky="ew", pady=(8, 0))

    def _choice(self, label, key, rows, row):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(5, 1))
        widget = ttk.Combobox(
            self, values=[item[1] for item in rows], state="readonly"
        )
        widget.grid(row=row + 1, column=0, sticky="ew")
        self.__dict__.setdefault("choices", {})[key] = (widget, rows)

    def submit(self):
        try:
            selected = {}
            for key, (widget, rows) in self.choices.items():
                index = widget.current()
                if index < 0:
                    raise ValueError(f"Choose a {key}.")
                selected[key] = rows[index][0]
            shipment_id = dispatch_request(
                self.identity.user_id,
                self.request_row[0],
                selected["warehouse"],
                selected["vehicle"],
                selected["driver"],
            )
            self.app.show_page(DispatchCompletePage, self.identity, shipment_id)
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            if error.pgcode == "42501":
                self.error.set("You do not have permission.")
            else:
                self.error.set("Dispatch failed. Check stock and selected vehicle/driver.")
            print(f"ReliefLink dispatch error: {error}")


class DispatchCompletePage(ttk.Frame):
    """Confirm transaction completion and provide navigation to shipment history."""

    def __init__(self, app, identity, shipment_id):
        super().__init__(app, padding=(32, 26))
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Shipment dispatched",
                  font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text=f"Shipment reference: RL-S{shipment_id}. The request status was updated.",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=14)
        ttk.Button(
            self, text="View shipment history",
            command=lambda: app.show_page(ShipmentHistoryPage, identity),
        ).grid(row=2, column=0, sticky="ew")
        ttk.Button(
            self, text="Back to Logistics home",
            command=lambda: _staff_home(app, identity),
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))


class ShipmentHistoryPage(ttk.Frame):
    """Show and advance shipment progress only to Logistics staff and Admin."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Shipment history",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.shipments = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.shipments.grid(row=1, column=0, sticky="nsew", pady=12)
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828",
                  wraplength=650).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(
            self, text="Advance selected shipment",
            command=self.advance_selected,
        ).grid(row=3, column=0, sticky="ew")
        ttk.Button(
            self, text="Refresh", command=self.load_shipments,
        ).grid(row=4, column=0, sticky="ew", pady=6)
        ttk.Button(
            self, text="Back to Logistics home",
            command=lambda: _staff_home(app, identity),
        ).grid(row=5, column=0, sticky="ew")
        self.load_shipments()

    def load_shipments(self):
        try:
            self.rows = logistics_shipment_history(self.identity.user_id)
            self.shipments.delete(0, tk.END)
            self.next_status = {}
            next_step = {
                "Assigned": "Dispatched",
                "Dispatched": "On the way",
                "On the way": "Delivered",
            }
            for row in self.rows:
                (shipment_id, request_id, priority, status, date, warehouse,
                 camp, region, vehicle, driver) = row
                self.shipments.insert(
                    tk.END,
                    f"RL-S{shipment_id} — Request RL-{request_id} ({priority}) — "
                    f"{status} — {camp}, {region} — {warehouse} — "
                    f"{vehicle} — {driver} — {date:%Y-%m-%d %H:%M}",
                )
                if status in next_step:
                    self.next_status[shipment_id] = next_step[status]
            if not self.rows:
                self.shipments.insert(tk.END, "No shipments yet.")
        except AuthenticationError as error:
            self.app.logout(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not load shipment history. Check the database.")
            print(f"ReliefLink shipment history error: {error}")

    def advance_selected(self):
        selected = self.shipments.curselection()
        if not selected or not self.rows:
            self.error.set("Choose a shipment first.")
            return
        row = self.rows[selected[0]]
        shipment_id = row[0]
        new_status = self.next_status.get(shipment_id)
        if new_status is None:
            self.error.set("No further status update is available for this shipment.")
            return
        try:
            update_shipment_status(self.identity.user_id, shipment_id, new_status)
            self.error.set(f"Shipment RL-S{shipment_id} marked {new_status}.")
            self.load_shipments()
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
            self.load_shipments()
        except psycopg2.Error as error:
            if error.pgcode == "42501":
                self.app.logout("You do not have permission.")
            else:
                self.error.set("Could not update shipment status.")
                print(f"ReliefLink shipment status error: {error}")
