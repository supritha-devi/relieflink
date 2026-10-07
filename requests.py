"""Normal-user request creation, history, and progress pages."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    public_affected_places,
    request_catalog_for_region,
    request_tracking,
    submit_relief_request,
    user_request_history,
)


DAYS_OF_COVER = 3


def _user_home(app, identity):
    from relieflink.start import UserHomePage

    app.show_page(UserHomePage, identity)


class UserRequestPage(ttk.Frame):
    """Choose an affected place, camp, and resource quantities for a request."""

    def __init__(self, app, identity, priority="Normal"):
        super().__init__(app, padding=(30, 20))
        self.app, self.identity, self.priority = app, identity, priority
        self.columnconfigure(0, weight=1)
        self.rowconfigure(7, weight=1)
        title = "Urgent help request" if priority == "Urgent" else "Request supplies"
        ttk.Label(self, text=title, font=("Segoe UI", 19, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        description = (
            "If life is in danger, call 112 first. Urgent requests are marked for staff."
            if priority == "Urgent"
            else "Choose the affected place and camp, then review the suggested three-day supply amounts."
        )
        ttk.Label(self, text=description, wraplength=650).grid(
            row=1, column=0, sticky="w", pady=(5, 12)
        )
        self.error = tk.StringVar(value="")
        try:
            self.places = public_affected_places()
        except psycopg2.Error as error:
            self.places = []
            self.error.set("Could not load affected places. Check the database.")
            print(f"ReliefLink request places error: {error}")
        ttk.Label(self, text="Affected place").grid(
            row=2, column=0, sticky="w", pady=(4, 1)
        )
        self.place_choice = ttk.Combobox(
            self, values=[name for _, name in self.places], state="readonly"
        )
        self.place_choice.grid(row=3, column=0, sticky="ew")
        self.place_choice.bind("<<ComboboxSelected>>", self.load_camps)

        ttk.Label(self, text="Camp").grid(
            row=4, column=0, sticky="w", pady=(7, 1)
        )
        self.camp_choice = ttk.Combobox(self, state="readonly")
        self.camp_choice.grid(row=5, column=0, sticky="ew")
        self.camp_choice.bind("<<ComboboxSelected>>", self.show_resources)

        self.resources_frame = ttk.Frame(self)
        self.resources_frame.grid(row=7, column=0, sticky="nsew", pady=(8, 4))
        self.resources_frame.columnconfigure(1, weight=1)
        self.resources = []
        self.camps = []
        self.quantities = {}
        ttk.Label(self, textvariable=self.error, foreground="#C62828",
                  wraplength=650).grid(row=8, column=0, sticky="w", pady=5)
        ttk.Button(self, text="Review request", command=self.review).grid(
            row=9, column=0, sticky="ew"
        )
        ttk.Button(self, text="Back to home",
                   command=lambda: _user_home(app, identity)
                   ).grid(row=10, column=0, sticky="ew", pady=(7, 0))

    def load_camps(self, _event=None):
        self.error.set("")
        place_index = self.place_choice.current()
        self.camp_choice.set("")
        self.camp_choice.configure(values=[])
        self.camps, self.resources, self.quantities = [], [], {}
        for child in self.resources_frame.winfo_children():
            child.destroy()
        if place_index < 0:
            return
        try:
            self.camps, self.resources = request_catalog_for_region(
                self.identity.user_id, self.places[place_index][0]
            )
            self.camp_choice.configure(values=[camp[1] for camp in self.camps])
            if not self.camps:
                self.error.set("There are no active camps in this place yet.")
        except (AuthenticationError, psycopg2.Error) as error:
            self.error.set(str(error) if isinstance(error, AuthenticationError)
                           else "Could not load camps and supplies.")
            print(f"ReliefLink request choices error: {error}")

    def show_resources(self, _event=None):
        for child in self.resources_frame.winfo_children():
            child.destroy()
        self.quantities = {}
        camp_index = self.camp_choice.current()
        if camp_index < 0:
            return
        population = self.camps[camp_index][2]
        ttk.Label(
            self.resources_frame,
            text=f"Suggested amount covers {DAYS_OF_COVER} days for {population} people.",
            wraplength=640,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 7))
        for index, (resource_id, name, unit, per_person_daily) in enumerate(
            self.resources, start=1
        ):
            suggested = (
                Decimal(population) * per_person_daily * Decimal(DAYS_OF_COVER)
            ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            quantity = tk.StringVar(value=format(suggested, "f").rstrip("0").rstrip(".") or "0")
            self.quantities[resource_id] = (quantity, suggested, name)
            ttk.Label(self.resources_frame, text=f"{name} ({unit})").grid(
                row=index, column=0, sticky="w", padx=(0, 6), pady=2
            )
            ttk.Button(
                self.resources_frame, text="−", width=3,
                command=lambda rid=resource_id: self.adjust(rid, -1),
            ).grid(row=index, column=1, sticky="e", padx=2)
            ttk.Entry(
                self.resources_frame, textvariable=quantity, width=13
            ).grid(row=index, column=2, sticky="ew", padx=2)
            ttk.Button(
                self.resources_frame, text="+", width=3,
                command=lambda rid=resource_id: self.adjust(rid, 1),
            ).grid(row=index, column=3, sticky="w", padx=2)

    def adjust(self, resource_id, direction):
        quantity, _, _ = self.quantities[resource_id]
        try:
            amount = Decimal(quantity.get() or "0") + Decimal(direction)
            quantity.set(format(max(Decimal(0), amount), "f"))
        except InvalidOperation:
            quantity.set("0")

    def review(self):
        try:
            place_index = self.place_choice.current()
            camp_index = self.camp_choice.current()
            if place_index < 0:
                raise ValueError("Choose an affected place first.")
            if camp_index < 0:
                raise ValueError("Choose your camp first.")
            items, warnings = [], []
            for resource_id, (variable, suggested, name) in self.quantities.items():
                try:
                    amount = Decimal(variable.get())
                except InvalidOperation as error:
                    raise ValueError(f"Enter a valid amount for {name}.") from error
                if not amount.is_finite() or amount < 0:
                    raise ValueError(f"Enter a non-negative amount for {name}.")
                if amount > 0:
                    items.append((resource_id, amount))
                if amount > suggested:
                    warnings.append(f"{name} is above the suggested three-day need.")
            if not items:
                raise ValueError("Choose at least one supply.")
            self.app.show_page(
                RequestReviewPage,
                self.identity,
                self.places[place_index][0],
                self.places[place_index][1],
                self.camps[camp_index],
                items,
                self.priority,
                warnings,
            )
        except ValueError as error:
            self.error.set(str(error))


class RequestReviewPage(ttk.Frame):
    """Review requested quantities and persist only after explicit confirmation."""

    def __init__(self, app, identity, region_id, place_name, camp, items, priority, warnings):
        super().__init__(app, padding=(32, 24))
        self.app, self.identity = app, identity
        self.region_id = region_id
        self.place_name, self.camp, self.items = place_name, camp, items
        self.priority = priority
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Review and send request",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        details = [
            f"Priority: {priority}",
            f"Place: {place_name}",
            f"Camp: {camp[1]}",
            f"People: {camp[2]}",
            "",
            "Requested supplies:",
        ]
        details.extend(f"- {name}: {quantity}" for _, quantity, name in self._named_items())
        details.extend(["", "If life is in danger, call 112 first."])
        if warnings:
            details.extend(["", "Need warnings:"] + warnings)
        ttk.Label(self, text="\n".join(details), wraplength=650, justify="left").grid(
            row=1, column=0, sticky="w", pady=16
        )
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w", pady=6
        )
        ttk.Button(self, text="Send request", style="Primary.TButton",
                   command=self.submit).grid(row=3, column=0, sticky="ew")
        ttk.Button(self, text="Back to edit request",
                   command=lambda: self._edit()).grid(row=4, column=0, sticky="ew", pady=7)

    def _named_items(self):
        from relieflink.auth import public_supply_resources

        names = {resource_id: name for resource_id, name, _ in public_supply_resources()}
        return [(resource_id, quantity, names.get(resource_id, "Supply"))
                for resource_id, quantity in self.items]

    def _edit(self):
        from relieflink.requests import UserRequestPage

        self.app.show_page(UserRequestPage, self.identity, self.priority)

    def submit(self):
        try:
            request_id = submit_relief_request(
                self.identity.user_id,
                self.region_id,
                self.camp[0],
                [(resource_id, quantity) for resource_id, quantity, _ in self._named_items()],
                self.priority,
            )
            from relieflink.requests import RequestSentPage

            self.app.show_page(RequestSentPage, self.identity, request_id)
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not send the request. Check the database and try again.")
            print(f"ReliefLink request error: {error}")


class RequestSentPage(ttk.Frame):
    """Confirm a newly created request and offer immediate status tracking."""

    def __init__(self, app, identity, request_id):
        super().__init__(app, padding=(32, 28))
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Request received",
                  font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text=f"Your request number is RL-{request_id}. Keep it for your records.",
            wraplength=650,
        ).grid(row=1, column=0, sticky="w", pady=14)
        ttk.Button(
            self,
            text="Track this request",
            command=lambda: app.show_page(RequestTrackingPage, identity, request_id),
        ).grid(row=2, column=0, sticky="ew")
        ttk.Button(
            self, text="Back to home",
            command=lambda: _user_home(app, identity),
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))


class UserRequestHistoryPage(ttk.Frame):
    """Display and open only the signed-in user's relief requests."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Where is my help?",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.requests = tk.Listbox(self, height=17, font=("Segoe UI", 10))
        self.requests.grid(row=1, column=0, sticky="nsew", pady=12)
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Button(self, text="Track selected request",
                   command=self.open_tracking).grid(row=3, column=0, sticky="ew")
        ttk.Button(self, text="Back to home",
                   command=lambda: _user_home(app, identity)
                   ).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        try:
            self.rows = user_request_history(identity.user_id, open_only=True)
            for request_id, date, priority, status, camp, region, items in self.rows:
                self.requests.insert(
                    tk.END,
                    f"RL-{request_id} — {priority} — {status} — {camp}, {region} — {items}",
                )
            if not self.rows:
                self.requests.insert(tk.END, "You have no open requests.")
        except (AuthenticationError, psycopg2.Error) as error:
            self.rows = []
            self.requests.insert(tk.END, "Could not load your requests.")
            print(f"ReliefLink request history error: {error}")

    def open_tracking(self):
        selection = self.requests.curselection()
        if not selection or not self.rows:
            self.error.set("Choose one of your open requests first.")
            return
        request_id = self.rows[selection[0]][0]
        self.app.show_page(RequestTrackingPage, self.identity, request_id)


class RequestTrackingPage(ttk.Frame):
    """Show request status events after checking ownership in PostgreSQL."""

    def __init__(self, app, identity, request_id):
        super().__init__(app, padding=(30, 22))
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Request tracking",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.content = ttk.Frame(self)
        self.content.grid(row=1, column=0, sticky="ew", pady=(14, 18))
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Button(
            self, text="Refresh",
            command=lambda: self.load(identity.user_id, request_id),
        ).grid(row=3, column=0, sticky="ew")
        ttk.Button(
            self, text="Back to requests",
            command=lambda: app.show_page(UserRequestHistoryPage, identity),
        ).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.load(identity.user_id, request_id)

    def load(self, user_id, request_id):
        for child in self.content.winfo_children():
            child.destroy()
        try:
            request, history = request_tracking(user_id, request_id)
            (number, priority, status, requested_at, camp, region,
             shipment_status) = request
            color = "#C62828" if priority == "Urgent" else "#263238"
            ttk.Label(
                self.content,
                text=f"Request RL-{number} — {priority}",
                foreground=color,
                font=("Segoe UI", 12, "bold"),
            ).grid(row=0, column=0, sticky="w", pady=3)
            ttk.Label(self.content, text=f"{camp}, {region}").grid(
                row=1, column=0, sticky="w", pady=3
            )
            ttk.Label(self.content, text=f"Requested {requested_at:%Y-%m-%d %H:%M}").grid(
                row=2, column=0, sticky="w", pady=3
            )
            latest_event = history[-1][0] if history else status
            shipment_status = shipment_status or ""
            steps = (
                ("Request received", True),
                ("Stock checked", status in ("Dispatched", "Delivered")),
                ("Truck assigned", bool(shipment_status)),
                ("On the way", shipment_status in ("On the way", "Delivered")),
                ("Delivered", status == "Delivered"),
            )
            for index, (label, complete) in enumerate(steps, start=3):
                marker = "✓" if complete else "○"
                ttk.Label(
                    self.content,
                    text=f"{marker}  {label}",
                    foreground="#2E7D32" if complete else "#607D8B",
                ).grid(row=index, column=0, sticky="w", pady=3)
            ttk.Label(
                self.content,
                text=f"Current request status: {status}. Latest history event: {latest_event}.",
                wraplength=650,
            ).grid(row=8, column=0, sticky="w", pady=(10, 0))
        except AuthenticationError as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not load request tracking. Check the database.")
            print(f"ReliefLink request tracking error: {error}")
