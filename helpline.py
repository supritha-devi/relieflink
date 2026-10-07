"""User and Staff messaging, conversation inbox, and external call records."""

import tkinter as tk
from tkinter import ttk

import psycopg2

from relieflink.auth import (
    AuthenticationError,
    call_log_rows,
    close_conversation,
    conversation_messages,
    create_call_record,
    public_affected_places,
    send_conversation_reply,
    staff_open_conversations,
    start_conversation,
    user_conversations,
)


def _staff_home(app, identity):
    from relieflink.start import StaffHomePage

    app.show_page(StaffHomePage, identity)


class UserHelplinePage(ttk.Frame):
    """Start a public user's first support message."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(32, 24))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Send a message to the relief team",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="If life is in danger, call 112 first.",
                  foreground="#C62828", font=("Segoe UI", 11, "bold")
                  ).grid(row=1, column=0, sticky="w", pady=(6, 14))
        ttk.Label(self, text="Your message").grid(row=2, column=0, sticky="w")
        self.body = tk.Text(self, height=7, wrap="word", font=("Segoe UI", 11))
        self.body.grid(row=3, column=0, sticky="ew", pady=(4, 10))
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=4, column=0, sticky="w", pady=4
        )
        ttk.Button(self, text="Send message", command=self.submit).grid(
            row=5, column=0, sticky="ew"
        )
        ttk.Button(
            self, text="My messages",
            command=lambda: app.show_page(UserConversationListPage, identity),
        ).grid(row=6, column=0, sticky="ew", pady=6)
        ttk.Button(self, text="Back to home",
                   command=lambda: _user_home(app, identity)
                   ).grid(row=7, column=0, sticky="ew")

    def submit(self):
        try:
            conversation_id = start_conversation(
                self.identity.user_id, self.body.get("1.0", "end").strip()
            )
            self.app.show_page(
                ConversationPage, self.identity, conversation_id, False
            )
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not send the message. Check the database.")
            print(f"ReliefLink message send error: {error}")


class UserConversationListPage(ttk.Frame):
    """List only the logged-in user's conversations."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="My messages",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.rows_view = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.rows_view.grid(row=1, column=0, sticky="nsew", pady=12)
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Button(self, text="Open selected conversation",
                   command=self.open_selected).grid(row=3, column=0, sticky="ew")
        ttk.Button(self, text="Back to home",
                   command=lambda: _user_home(app, identity)
                   ).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.load()

    def load(self):
        try:
            self.rows = user_conversations(self.identity.user_id)
            self.rows_view.delete(0, tk.END)
            for conversation_id, status, created, latest in self.rows:
                self.rows_view.insert(
                    tk.END, f"Conversation {conversation_id} — {status} — {latest}"
                )
            if not self.rows:
                self.rows_view.insert(tk.END, "You have no conversations yet.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load your messages.")
                print(f"ReliefLink user conversation list error: {error}")

    def open_selected(self):
        selected = self.rows_view.curselection()
        if not selected or not self.rows:
            self.error.set("Choose one of your conversations.")
            return
        self.app.show_page(
            ConversationPage, self.identity, self.rows[selected[0]][0], False
        )


class StaffInboxPage(ttk.Frame):
    """Open conversation inbox for any active Staff department or Admin."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 22))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Open messages",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.rows_view = tk.Listbox(self, height=16, font=("Segoe UI", 10))
        self.rows_view.grid(row=1, column=0, sticky="nsew", pady=12)
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Button(self, text="Open selected conversation",
                   command=self.open_selected).grid(row=3, column=0, sticky="ew")
        ttk.Button(self, text="Refresh inbox", command=self.load).grid(
            row=4, column=0, sticky="ew", pady=6
        )
        ttk.Button(self, text="View call log",
                   command=lambda: app.show_page(CallLogPage, identity)
                   ).grid(row=5, column=0, sticky="ew")
        ttk.Button(self, text="Back to staff home",
                   command=lambda: _staff_home(app, identity)
                   ).grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.load()

    def load(self):
        try:
            self.rows = staff_open_conversations(self.identity.user_id)
            self.rows_view.delete(0, tk.END)
            for conversation_id, created, name, camp, latest in self.rows:
                self.rows_view.insert(
                    tk.END, f"#{conversation_id} — {name} — {camp} — {latest}"
                )
            if not self.rows:
                self.rows_view.insert(tk.END, "No open conversations.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load the message inbox.")
                print(f"ReliefLink staff inbox error: {error}")

    def open_selected(self):
        selected = self.rows_view.curselection()
        if not selected or not self.rows:
            self.error.set("Choose an open conversation.")
            return
        self.app.show_page(
            ConversationPage, self.identity, self.rows[selected[0]][0], True
        )


class ConversationPage(ttk.Frame):
    """Refresh messages, send permitted replies, and let staff close conversations."""

    def __init__(self, app, identity, conversation_id, staff_view):
        super().__init__(app, padding=(28, 20))
        self.app, self.identity = app, identity
        self.conversation_id, self.staff_view = conversation_id, staff_view
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text=f"Conversation #{conversation_id}",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.messages = tk.Text(
            self, height=17, wrap="word", state="disabled", font=("Segoe UI", 10)
        )
        self.messages.grid(row=1, column=0, sticky="nsew", pady=10)
        ttk.Label(self, text="Reply").grid(row=2, column=0, sticky="w")
        self.reply = tk.Text(self, height=3, wrap="word", font=("Segoe UI", 10))
        self.reply.grid(row=3, column=0, sticky="ew", pady=(3, 8))
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=4, column=0, sticky="w", pady=4
        )
        controls = ttk.Frame(self)
        controls.grid(row=5, column=0, sticky="ew")
        ttk.Button(controls, text="Send reply", command=self.send).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(controls, text="Refresh", command=self.load).pack(
            side="left", padx=6
        )
        if staff_view:
            ttk.Button(controls, text="Close conversation",
                       command=self.close).pack(side="left", padx=6)
            ttk.Button(
                self, text="Back to inbox",
                command=lambda: app.show_page(StaffInboxPage, identity),
            ).grid(row=6, column=0, sticky="ew", pady=(8, 0))
        else:
            ttk.Button(
                self, text="Back to my messages",
                command=lambda: app.show_page(UserConversationListPage, identity),
            ).grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.load()

    def load(self):
        try:
            rows = conversation_messages(self.identity.user_id, self.conversation_id)
            self.messages.configure(state="normal")
            self.messages.delete("1.0", tk.END)
            for _, _, sender, role, body, sent_at in rows:
                self.messages.insert(
                    tk.END, f"{sender} ({role}) — {sent_at:%Y-%m-%d %H:%M}\n{body}\n\n"
                )
            self.messages.configure(state="disabled")
            self.messages.see(tk.END)
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not refresh this conversation.")
                print(f"ReliefLink conversation refresh error: {error}")

    def send(self):
        try:
            send_conversation_reply(
                self.identity.user_id,
                self.conversation_id,
                self.reply.get("1.0", "end").strip(),
            )
            self.reply.delete("1.0", tk.END)
            self.error.set("")
            self.load()
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not send the reply. Check the database.")
            print(f"ReliefLink message reply error: {error}")

    def close(self):
        try:
            close_conversation(self.identity.user_id, self.conversation_id)
            self.app.show_page(StaffInboxPage, self.identity)
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not close the conversation.")
                print(f"ReliefLink conversation close error: {error}")


class CallLogPage(ttk.Frame):
    """Read and add external call records as active Staff or Admin."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(28, 20))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Call log",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.rows_view = tk.Listbox(self, height=13, font=("Segoe UI", 10))
        self.rows_view.grid(row=1, column=0, sticky="nsew", pady=10)
        self.error = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.error, foreground="#C62828").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Button(self, text="Add call record",
                   command=lambda: app.show_page(AddCallRecordPage, identity)
                   ).grid(row=3, column=0, sticky="ew")
        ttk.Button(self, text="Refresh", command=self.load).grid(
            row=4, column=0, sticky="ew", pady=6
        )
        ttk.Button(self, text="Back to inbox",
                   command=lambda: app.show_page(StaffInboxPage, identity)
                   ).grid(row=5, column=0, sticky="ew")
        self.load()

    def load(self):
        try:
            self.rows = call_log_rows(self.identity.user_id)
            self.rows_view.delete(0, tk.END)
            for call_id, name, phone, region, district, need, outcome, called_at in self.rows:
                self.rows_view.insert(
                    tk.END,
                    f"{called_at:%Y-%m-%d %H:%M} — {name}, {phone} — "
                    f"{region}, {district} — Need: {need} — Outcome: {outcome}",
                )
            if not self.rows:
                self.rows_view.insert(tk.END, "No call records yet.")
        except (AuthenticationError, psycopg2.Error) as error:
            if isinstance(error, AuthenticationError):
                self.error.set(str(error))
            else:
                self.error.set("Could not load the call log.")
                print(f"ReliefLink call-log lookup error: {error}")


class AddCallRecordPage(ttk.Frame):
    """Validate and save a handled phone call against an affected place."""

    def __init__(self, app, identity):
        super().__init__(app, padding=(30, 20))
        self.app, self.identity = app, identity
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Add call record",
                  font=("Segoe UI", 19, "bold")).grid(row=0, column=0, sticky="w")
        self.fields = {}
        row = 1
        for key, label in (
            ("name", "Caller name"),
            ("phone", "Caller phone"),
            ("need", "Caller need"),
            ("outcome", "Call outcome"),
        ):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=(5, 1))
            variable = tk.StringVar()
            ttk.Entry(self, textvariable=variable).grid(row=row + 1, column=0, sticky="ew")
            self.fields[key] = variable
            row += 2
        try:
            self.places = public_affected_places()
        except psycopg2.Error as error:
            self.places = []
            print(f"ReliefLink call-record place lookup error: {error}")
        ttk.Label(self, text="Affected place").grid(row=row, column=0, sticky="w")
        self.place_choice = ttk.Combobox(
            self, values=[name for _, name in self.places], state="readonly"
        )
        self.place_choice.grid(row=row + 1, column=0, sticky="ew")
        row += 2
        self.error = tk.StringVar(value="Calls are recorded here; the app does not place phone calls.")
        ttk.Label(self, textvariable=self.error, foreground="#607D8B",
                  wraplength=650).grid(row=row, column=0, sticky="w", pady=8)
        ttk.Button(self, text="Save call record", command=self.submit).grid(
            row=row + 1, column=0, sticky="ew"
        )
        ttk.Button(self, text="Back to call log",
                   command=lambda: app.show_page(CallLogPage, identity)
                   ).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))

    def submit(self):
        try:
            place_index = self.place_choice.current()
            if place_index < 0:
                raise ValueError("Choose an affected place.")
            call_id = create_call_record(
                self.identity.user_id,
                self.fields["name"].get(),
                self.fields["phone"].get(),
                self.places[place_index][0],
                self.fields["need"].get(),
                self.fields["outcome"].get(),
            )
            self.app.show_page(CallLogPage, self.identity)
            print(f"ReliefLink call record {call_id} saved.")
        except (AuthenticationError, ValueError) as error:
            self.error.set(str(error))
        except psycopg2.Error as error:
            self.error.set("Could not save the call record.")
            print(f"ReliefLink call-record error: {error}")
