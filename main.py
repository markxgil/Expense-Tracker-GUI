import os
import sys
import uuid
import csv
import sqlite3
import hashlib
import configparser
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from tkcalendar import DateEntry

# ---------------- Configuration ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
DB_FILE = os.path.join(BASE_DIR, "finance.db")

# ---------------- Theme Constants ----------------
APP_BG_COLOR = ("#E3E5E8", "#121212")
GLASS_CARD_COLOR = ("#FFFFFF", "#1e1e1e")
GLASS_BORDER_COLOR = ("#C0C5CE", "#333333")
ACCENT_COLOR = "#3B8ED0"
TEXT_COLOR = ("#1a1a1a", "#e0e0e0")

CATEGORY_COLOR_MAP = {
    'Food': '#FF6B6B', 'Transport': '#4ECDC4', 'Entertainment': '#FFA94D',
    'Shopping': '#9B5DE5', 'Bills': '#F9C74F', 'Other': '#A0AEC0',
    'Salary': '#2EC4B6', 'Gift': '#70E000', 'Freelance': '#3A86FF'
}
DEFAULT_CATEGORY_COLOR = '#B0BEC5'

def category_color(cat):
    return CATEGORY_COLOR_MAP.get(cat, DEFAULT_CATEGORY_COLOR)

# ---------------- Config & Session Management ----------------
def save_config_value(section, key, value):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if section not in config:
        config[section] = {}
    config[section][key] = value
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def get_config_value(section, key):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if section in config and key in config[section]:
        return config[section][key]
    return None

def clear_config_section(section):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if section in config:
        del config[section]
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

# ---------------- Database Management ----------------
def get_db_connection():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        messagebox.showerror("Database Error", f"Connection failed: {e}")
        return None

def initialize_db():
    """Initializes the database tables and handles schema migrations."""
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor()

    try:
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                budget REAL DEFAULT 0
            )
        """)
        
        # Schema Check: Ensure 'budget' column exists (for older DB versions)
        cursor.execute("PRAGMA table_info(users)")
        if 'budget' not in [col[1] for col in cursor.fetchall()]:
            cursor.execute("ALTER TABLE users ADD COLUMN budget REAL DEFAULT 0")

        # Transactions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                username TEXT,
                date TEXT,
                type TEXT,
                category TEXT,
                description TEXT,
                amount REAL,
                FOREIGN KEY(username) REFERENCES users(username)
            )
        """)
        
        # Schema Check: Ensure 'username' column exists
        cursor.execute("PRAGMA table_info(transactions)")
        if 'username' not in [col[1] for col in cursor.fetchall()]:
            cursor.execute("ALTER TABLE transactions ADD COLUMN username TEXT")
            cursor.execute("UPDATE transactions SET username = 'admin' WHERE username IS NULL")

        conn.commit()
    except sqlite3.Error as e:
        messagebox.showerror("Initialization Error", str(e))
    finally:
        conn.close()

# ---------------- Logic Controllers ----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    if not username or not password:
        return False, "Fields cannot be empty"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash, budget) VALUES (?, ?, 0)",
                       (username, hash_password(password)))
        conn.commit()
        conn.close()
        return True, "User registered successfully"
    except sqlite3.IntegrityError:
        return False, "Username already exists"
    except sqlite3.Error as e:
        return False, str(e)

def login_user(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        return row and row[0] == hash_password(password)
    except sqlite3.Error:
        return False

def user_exists(username):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except sqlite3.Error:
        return False

def get_user_budget(username):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT budget FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.0
    except sqlite3.Error:
        return 0.0

def set_user_budget(username, amount):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET budget = ? WHERE username = ?", (amount, username))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False

def load_transactions(username):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, type, category, description, amount 
            FROM transactions WHERE username = ? ORDER BY date DESC
        """, (username,))
        rows = cursor.fetchall()
        conn.close()
        keys = ['id', 'date', 'type', 'category', 'description', 'amount']
        return [dict(zip(keys, row)) for row in rows]
    except sqlite3.Error:
        return []

def save_transaction(tx, username):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO transactions (id, username, date, type, category, description, amount)
        VALUES (:id, :username, :date, :type, :category, :description, :amount)
    """, {**tx, 'username': username})
    conn.commit()
    conn.close()

def update_transaction(tx, username):
    conn = get_db_connection()
    conn.execute("""
        UPDATE transactions 
        SET date=:date, type=:type, category=:category, description=:description, amount=:amount 
        WHERE id=:id AND username=:username
    """, {**tx, 'username': username})
    conn.commit()
    conn.close()

def delete_transaction(tx_id, username):
    conn = get_db_connection()
    conn.execute("DELETE FROM transactions WHERE id = ? AND username = ?", (tx_id, username))
    conn.commit()
    conn.close()

# ---------------- UI Components ----------------

class GlassCard(ctk.CTkFrame):
    """A custom frame styled to look like a glass card."""
    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=20, fg_color=GLASS_CARD_COLOR,border_width=2, border_color=GLASS_BORDER_COLOR, **kwargs)

class SetBudgetDialog(ctk.CTkToplevel):
    """Modal dialog for setting the monthly budget."""
    def __init__(self, parent, current_budget):
        super().__init__(parent)
        self.title("Set Monthly Budget")
        self.geometry("350x280")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.current_budget = current_budget
        self._build_ui()

    def _build_ui(self):
        f = GlassCard(self)
        f.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(f, text="Monthly Budget", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(f, text=f"Current Limit: ₹{self.current_budget:,.2f}", font=ctk.CTkFont(size=13), text_color="gray").pack(pady=(0, 20))

        self.amount_entry = ctk.CTkEntry(f, placeholder_text="Enter new amount", height=45, justify="center", font=ctk.CTkFont(size=16))
        self.amount_entry.pack(fill="x", padx=30, pady=(0, 25))
        if self.current_budget > 0:
            self.amount_entry.insert(0, str(int(self.current_budget)))

        b_frame = ctk.CTkFrame(f, fg_color="transparent")
        b_frame.pack(fill="x", padx=30, pady=(0, 20))
        
        ctk.CTkButton(b_frame, text="Cancel", width=100, fg_color="transparent", border_width=1, border_color=ACCENT_COLOR, text_color=ACCENT_COLOR, command=self.destroy).pack(side="left")
        ctk.CTkButton(b_frame, text="Save Budget", width=120, fg_color=ACCENT_COLOR, command=self._save).pack(side="right")
        self.amount_entry.focus_set()

    def _save(self):
        try:
            val = float(self.amount_entry.get())
            if val < 0: raise ValueError
            self.result = val
            self.destroy()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid positive number.")

class AddEditTransactionDialog(ctk.CTkToplevel):
    """Modal dialog for adding or editing a transaction."""
    def __init__(self, parent, transaction=None):
        super().__init__(parent)
        self.title("Transaction")
        self.geometry("400x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.tx_id = transaction['id'] if transaction else None
        
        self.type_var = ctk.StringVar(value=transaction['type'] if transaction else 'Expense')
        self.cat_var = ctk.StringVar(value=transaction['category'] if transaction else 'Food')
        
        self.edit_data = transaction 
        self.initial_date = datetime.now()
        if transaction and transaction['date']:
            try:
                self.initial_date = datetime.strptime(transaction['date'], "%Y-%m-%d")
            except ValueError: pass
        
        self._build_ui()

    def _build_ui(self):
        f = GlassCard(self)
        f.pack(fill="both", expand=True, padx=20, pady=20)
        f.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(f, text="Transaction Details", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 20))

        self.type_seg = ctk.CTkSegmentedButton(f, values=["Expense", "Income"], variable=self.type_var, command=self._update_cats)
        self.type_seg.pack(fill="x", padx=20, pady=(0, 15))
        
        date_frame = ctk.CTkFrame(f, fg_color="transparent")
        date_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        self.date_entry = DateEntry(date_frame, width=12, background=ACCENT_COLOR, foreground='white', borderwidth=2, year=self.initial_date.year, month=self.initial_date.month, day=self.initial_date.day, date_pattern='y-mm-dd')
        self.date_entry.pack(fill="x", ipady=4)
        
        self.cat_menu = ctk.CTkOptionMenu(f, values=['Food'], variable=self.cat_var, height=40)
        self.cat_menu.pack(fill="x", padx=20, pady=(0, 15))

        self.desc_entry = ctk.CTkEntry(f, placeholder_text="Description", height=40)
        self.desc_entry.pack(fill="x", padx=20, pady=(0, 15))

        self.amt_entry = ctk.CTkEntry(f, placeholder_text="Amount", height=40)
        self.amt_entry.pack(fill="x", padx=20, pady=(0, 25))
        
        if self.edit_data:
            self.desc_entry.insert(0, self.edit_data['description'])
            self.amt_entry.insert(0, str(self.edit_data['amount']))

        b_frame = ctk.CTkFrame(f, fg_color="transparent")
        b_frame.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(b_frame, text="Cancel", fg_color="transparent", border_width=1, border_color=ACCENT_COLOR, text_color=ACCENT_COLOR, width=100, command=self.destroy).pack(side="left")
        ctk.CTkButton(b_frame, text="Save", fg_color=ACCENT_COLOR, width=100, command=self._save).pack(side="right")
        self._update_cats()

    def _update_cats(self, _=None):
        cats = ['Food', 'Entertainment', 'Shopping', 'Transport', 'Bills', 'Other'] if self.type_var.get() == 'Expense' else ['Salary', 'Gift', 'Freelance', 'Other']
        self.cat_menu.configure(values=cats)
        if self.cat_var.get() not in cats: self.cat_var.set(cats[0])

    def _save(self):
        try:
            d = self.date_entry.get_date().strftime("%Y-%m-%d")
            desc = self.desc_entry.get().strip()
            amt = float(self.amt_entry.get().strip())
            if amt <= 0: raise ValueError
            
            self.result = {'id': self.tx_id, 'date': d, 'type': self.type_var.get(), 'category': self.cat_var.get(), 'description': desc, 'amount': amt}
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid data. Amount must be positive.")

class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, on_login_success):
        super().__init__(master, fg_color="transparent")
        self.on_login_success = on_login_success
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.card = GlassCard(self, width=400, height=530)
        self.card.grid(row=0, column=0)
        self.card.grid_propagate(False)

        content = ctk.CTkFrame(self.card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=40, pady=50)

        ctk.CTkLabel(content, text="Welcome Back", font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"), text_color=TEXT_COLOR).pack(pady=(10, 5))
        ctk.CTkLabel(content, text="Sign in to continue", font=ctk.CTkFont(family="Segoe UI", size=14), text_color="gray").pack(pady=(0, 30))

        self.user_entry = ctk.CTkEntry(content, placeholder_text="Username", height=50, corner_radius=15, border_width=1)
        self.user_entry.pack(fill="x", pady=(0, 20))
        self.pass_entry = ctk.CTkEntry(content, placeholder_text="Password", show="•", height=50, corner_radius=15, border_width=1)
        self.pass_entry.pack(fill="x", pady=(0, 20))

        self.remember_var = ctk.BooleanVar(value=False)
        self.remember_cb = ctk.CTkCheckBox(content, text="Remember Me", variable=self.remember_var, font=ctk.CTkFont(size=12), text_color="gray", border_width=2, checkbox_width=20, checkbox_height=20)
        self.remember_cb.pack(fill="x", pady=(0, 20))

        self.login_btn = ctk.CTkButton(content, text="Login", height=50, corner_radius=15, fg_color=ACCENT_COLOR, hover_color="#327ab0", font=ctk.CTkFont(size=15, weight="bold"), command=self.attempt_login)
        self.login_btn.pack(fill="x", pady=(0, 15))

        self.register_btn = ctk.CTkButton(content, text="Create Account", height=50, corner_radius=15, fg_color="transparent", border_width=1, border_color=ACCENT_COLOR, text_color=ACCENT_COLOR, font=ctk.CTkFont(size=14, weight="bold"), command=self.attempt_register)
        self.register_btn.pack(fill="x")

    def attempt_login(self):
        user = self.user_entry.get().strip()
        pw = self.pass_entry.get().strip()
        if login_user(user, pw):
            if self.remember_var.get():
                save_config_value('Auth', 'user', user)
            else:
                clear_config_section('Auth')
            self.on_login_success(user)
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")

    def attempt_register(self):
        success, msg = register_user(self.user_entry.get().strip(), self.pass_entry.get().strip())
        if success:
            messagebox.showinfo("Success", msg + "\nPlease login now.")
        else:
            messagebox.showerror("Error", msg)

class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master, username, logout_callback):
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.username = username
        self.logout_callback = logout_callback
        
        self._create_header()
        self._create_dashboard()
        self._create_transactions_area()
        self._update_treeview_style()
        self.update_dashboard()
        self.budget_alert_shown = False

    def _create_header(self):
        header = GlassCard(self, height=70)
        header.pack(fill="x", padx=20, pady=(15, 10))
        header.grid_columnconfigure(0, weight=1)
        
        inner_frame = ctk.CTkFrame(header, fg_color="transparent")
        inner_frame.pack(fill="both", expand=True, padx=20)
        
        title = ctk.CTkLabel(inner_frame, text="Expense Tracker", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"))
        title.pack(side="left", pady=15)

        controls_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        controls_frame.pack(side="right", pady=15)

        ctk.CTkButton(controls_frame, text="Set Monthly Budget", width=140, height=32, corner_radius=16, fg_color="transparent", border_width=1, border_color=ACCENT_COLOR, text_color=ACCENT_COLOR, command=self._open_budget_dialog).pack(side="left", padx=(0, 10))

        theme_val = get_config_value('Settings', 'theme') or "System"
        self.theme_var = ctk.StringVar(value=theme_val)
        ctk.CTkOptionMenu(controls_frame, values=["Light", "Dark", "System"], width=110, height=32, corner_radius=16, variable=self.theme_var, command=self._on_theme_change).pack(side="left", padx=(0, 10))

        ctk.CTkButton(controls_frame, text="Logout", width=90, height=32, corner_radius=16, fg_color="#ef5350", hover_color="#d32f2f", command=self._logout).pack(side="left")

    def _logout(self):
        clear_config_section('Auth')
        self.logout_callback()

    def _open_budget_dialog(self):
        current_budget = get_user_budget(self.username)
        dlg = SetBudgetDialog(self, current_budget)
        self.wait_window(dlg)
        if dlg.result is not None:
            if set_user_budget(self.username, dlg.result):
                self.update_dashboard()
            else:
                messagebox.showerror("Error", "Could not save budget.")

    def _on_theme_change(self, choice):
        ctk.set_appearance_mode(choice)
        save_config_value('Settings', 'theme', choice)
        self._update_treeview_style()
        self.update_dashboard()

    def _update_treeview_style(self):
        mode = ctk.get_appearance_mode()
        style = ttk.Style()
        style.theme_use('default')

        if mode == "Dark":
            bg_color, fg_color = "#1e1e1e", "#e0e0e0"
            header_bg, header_fg = "#333333", "#ffffff"
        else:
            bg_color, fg_color = "#ffffff", "#1a1a1a"
            header_bg, header_fg = "#E3E5E8", "#1a1a1a"

        style.configure("Custom.Treeview", background=bg_color, foreground=fg_color, fieldbackground=bg_color, rowheight=35, borderwidth=0, font=('Segoe UI', 11))
        style.configure("Custom.Treeview.Heading", background=header_bg, foreground=header_fg, relief="flat", font=('Segoe UI', 12, 'bold'))
        style.map('Treeview', background=[('selected', ACCENT_COLOR)], foreground=[('selected', 'white')])

    def _create_dashboard(self):
        dash_container = ctk.CTkFrame(self, fg_color="transparent")
        dash_container.pack(fill="x", padx=20, pady=5)

        # Summary Cards
        cards_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 10))
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.balance_label = self._create_card(cards_frame, 0, "Total Balance")
        self.income_label = self._create_card(cards_frame, 1, "Total Income", text_color="#27ae60")
        
        # Budget Card
        budget_card = GlassCard(cards_frame)
        budget_card.grid(row=0, column=2, sticky="nsew", padx=(0, 10))
        b_head = ctk.CTkFrame(budget_card, fg_color="transparent")
        b_head.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(b_head, text="Monthly Budget", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray").pack(side="left")
        self.budget_percent_label = ctk.CTkLabel(b_head, text="0%", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray")
        self.budget_percent_label.pack(side="right")
        self.budget_bar = ctk.CTkProgressBar(budget_card, height=10, corner_radius=5)
        self.budget_bar.pack(fill="x", padx=20, pady=(0, 10))
        b_det = ctk.CTkFrame(budget_card, fg_color="transparent")
        b_det.pack(fill="x", padx=20, pady=(0, 15))
        self.budget_spent_label = ctk.CTkLabel(b_det, text="Spent: ₹0", font=ctk.CTkFont(size=12))
        self.budget_spent_label.pack(side="left")
        self.budget_rem_label = ctk.CTkLabel(b_det, text="Left: ₹0", font=ctk.CTkFont(size=12))
        self.budget_rem_label.pack(side="right")

        self.expense_label = self._create_card(cards_frame, 3, "Total Expenses", text_color="#eb5757")

        # Charts
        charts_frame = ctk.CTkFrame(dash_container, fg_color="transparent")
        charts_frame.pack(fill="x")
        charts_frame.grid_columnconfigure((0, 1), weight=1)
        # --- FIX: Unpack 3 values now ---
        self.fig_bar, self.ax_bar, self.canvas_bar = self._create_chart(charts_frame, 0, "Income vs Expense")
        self.fig_pie, self.ax_pie, self.canvas_pie = self._create_chart(charts_frame, 1, "Spending Breakdown")

    def _create_card(self, parent, col, title, text_color=None):
        card = GlassCard(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14, weight="bold"), text_color="gray").pack(anchor="w", padx=20, pady=(15,5))
        lbl = ctk.CTkLabel(card, text="₹0.00", font=ctk.CTkFont(size=24, weight="bold"), text_color=text_color)
        lbl.pack(anchor="w", padx=20, pady=(0,15))
        return lbl

    def _create_chart(self, parent, col, title):
        card = GlassCard(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(10, 0))
        fig = Figure(figsize=(5, 2.5), dpi=100)
        ax = fig.add_subplot(111)
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.get_tk_widget().configure(highlightthickness=0, bd=0)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        # --- FIX: Return fig as well ---
        return fig, ax, canvas

    def _create_transactions_area(self):
        frame = GlassCard(self)
        frame.pack(fill="both", expand=True, padx=20, pady=(20, 20))
        
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 10))
        ctk.CTkLabel(header, text="Recent Transactions", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        btns = ctk.CTkFrame(header, fg_color="transparent")
        btns.pack(side="right")
        
        ctk.CTkButton(btns, text="+ Add Transaction", width=150, height=36, fg_color=ACCENT_COLOR, hover_color="#327ab0", font=ctk.CTkFont(size=13, weight="bold"), command=self.open_add_dialog).pack(side="left", padx=(0, 12))
        
        self.edit_btn = ctk.CTkButton(btns, text="Edit", width=80, height=32, state="disabled", fg_color="transparent", border_width=1, border_color=ACCENT_COLOR, text_color=ACCENT_COLOR, command=self._edit_selected_transaction)
        self.edit_btn.pack(side="left", padx=(0, 10))
        
        self.delete_btn = ctk.CTkButton(btns, text="Delete", width=80, height=32, state="disabled", fg_color="transparent", border_width=1, border_color="#ef5350", text_color="#ef5350", command=self._delete_selected_transaction)
        self.delete_btn.pack(side="left", padx=(0, 25))
        
        ctk.CTkButton(btns, text="Export CSV", width=110, height=32, fg_color="#2e7d32", hover_color="#1b5e20", command=self.export_csv).pack(side="left")

        tree_container = ctk.CTkFrame(frame, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        columns = ('date', 'type', 'category', 'description', 'amount')
        self.tree = ttk.Treeview(tree_container, columns=columns, show='headings', style="Custom.Treeview")
        self.tree.pack(side="left", fill="both", expand=True)
        
        vsb = ctk.CTkScrollbar(tree_container, orientation="vertical", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)

        for col in columns: self.tree.heading(col, text=col.capitalize())
        self.tree.column('date', width=100, anchor='center')
        self.tree.column('type', width=80, anchor='center')
        self.tree.column('category', width=120, anchor='center')
        self.tree.column('description', width=400, anchor='w')
        self.tree.column('amount', width=120, anchor='e')

        self.tree.bind("<Button-3>", self._on_right_click_tree)
        self.tree.bind("<Double-1>", self._on_double_click_edit)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def export_csv(self):
        transactions = load_transactions(self.username)
        if not transactions:
            messagebox.showinfo("Info", "No data to export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['id','date','type','category','description','amount'])
                    writer.writeheader()
                    writer.writerows(transactions)
                messagebox.showinfo("Success", f"Exported {len(transactions)} rows.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _on_tree_select(self, event):
        if self.tree.selection():
            self.edit_btn.configure(state="normal", fg_color=ACCENT_COLOR, text_color="white")
            self.delete_btn.configure(state="normal", fg_color="#ef5350", text_color="white")
        else:
            self.edit_btn.configure(state="disabled", fg_color="transparent", text_color=ACCENT_COLOR)
            self.delete_btn.configure(state="disabled", fg_color="transparent", text_color="#ef5350")

    def _on_right_click_tree(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Edit", command=self._edit_selected_transaction)
            menu.add_command(label="Delete", command=self._delete_selected_transaction)
            menu.tk_popup(event.x_root, event.y_root)

    def _on_double_click_edit(self, event):
        if self.tree.identify_row(event.y):
            self._edit_selected_transaction()

    def _delete_selected_transaction(self):
        selected = self.tree.selection()
        if selected:
            if messagebox.askyesno("Confirm", "Delete transaction?"):
                delete_transaction(selected[0], self.username)
                self.update_dashboard()

    def _edit_selected_transaction(self):
        selected = self.tree.selection()
        if selected:
            tx = next((t for t in load_transactions(self.username) if t['id'] == selected[0]), None)
            if tx:
                dlg = AddEditTransactionDialog(self, transaction=tx)
                self.wait_window(dlg)
                if dlg.result:
                    update_transaction(dlg.result, self.username)
                    self.update_dashboard()

    def open_add_dialog(self):
        dlg = AddEditTransactionDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result['id'] = str(uuid.uuid4())
            save_transaction(dlg.result, self.username)
            self.update_dashboard()

    def update_dashboard(self):
        transactions = load_transactions(self.username)
        total_income = sum(t['amount'] for t in transactions if t['type'] == 'Income')
        total_expenses = sum(t['amount'] for t in transactions if t['type'] == 'Expense')

        self.balance_label.configure(text=f"₹{total_income - total_expenses:,.2f}")
        self.income_label.configure(text=f"₹{total_income:,.2f}")
        self.expense_label.configure(text=f"₹{total_expenses:,.2f}")

        # Budget Logic
        user_budget = get_user_budget(self.username)
        current_month = datetime.now().strftime("%Y-%m")
        monthly_expense = sum(t['amount'] for t in transactions 
                              if t['type'] == 'Expense' and t['date'].startswith(current_month))

        if user_budget > 0:
            ratio = monthly_expense / user_budget
            percent = min(ratio, 1.0)
            color = ACCENT_COLOR if ratio < 0.75 else ("#FFA94D" if ratio < 0.9 else "#ef5350")
            
            self.budget_bar.configure(progress_color=color)
            self.budget_bar.set(percent)
            self.budget_percent_label.configure(text=f"{int(ratio*100)}%", text_color=color)
            self.budget_spent_label.configure(text=f"Spent: ₹{monthly_expense:,.0f}")
            
            rem = user_budget - monthly_expense
            if rem < 0:
                self.budget_rem_label.configure(text=f"Over: ₹{abs(rem):,.0f}", text_color="#ef5350")
            else:
                self.budget_rem_label.configure(text=f"Left: ₹{rem:,.0f}", text_color="gray")
        else:
            self.budget_bar.set(0)
            self.budget_percent_label.configure(text="N/A", text_color="gray")
            self.budget_spent_label.configure(text="No Budget Set")
            self.budget_rem_label.configure(text="")

        if user_budget > 0 and monthly_expense >= user_budget and not self.budget_alert_shown:
            messagebox.showwarning(
                "Budget Alert",
                "⚠ You have exceeded your monthly budget!"
            )
            self.budget_alert_shown = True
        if monthly_expense < user_budget:
            self.budget_alert_shown = False


        # Treeview
        for i in self.tree.get_children(): self.tree.delete(i)
        for t in transactions:
            self.tree.insert('', 'end', iid=t['id'], values=(t['date'], t['type'], t['category'], t['description'], f"₹{t['amount']:,.2f}"))
        self._on_tree_select(None)

        # Charts
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg = GLASS_CARD_COLOR[1] if is_dark else GLASS_CARD_COLOR[0]
        fg = "white" if is_dark else "black"

        # Bar Chart
        self.ax_bar.clear()
        self.fig_bar.patch.set_facecolor(bg)
        self.ax_bar.set_facecolor(bg)
        self.canvas_bar.get_tk_widget().configure(bg=bg)
        
        bar_x = ['Income', 'Expense']
        bar_y = [total_income, total_expenses]
        self.ax_bar.bar(bar_x, bar_y, color=['#27ae60', '#eb5757'], width=0.5)
        self.ax_bar.tick_params(colors=fg)
        self.ax_bar.spines['bottom'].set_color(fg)
        for s in ['top', 'right', 'left']: self.ax_bar.spines[s].set_visible(False)
        self.ax_bar.get_yaxis().set_visible(False)
        for i, v in enumerate(bar_y):
            self.ax_bar.text(i, v, f"₹{v:,.0f}", ha='center', va='bottom', color=fg, fontweight='bold')
        self.fig_bar.tight_layout()
        self.canvas_bar.draw()

        # Pie Chart
        self.ax_pie.clear()
        self.fig_pie.patch.set_facecolor(bg)
        self.ax_pie.set_facecolor(bg)
        self.canvas_pie.get_tk_widget().configure(bg=bg)
        
        ex_map = {}
        for t in transactions:
            if t['type'] == 'Expense':
                ex_map[t['category']] = ex_map.get(t['category'], 0) + t['amount']

        if ex_map:
            colors = [category_color(k) for k in ex_map.keys()]
            wedges, _, _ = self.ax_pie.pie(ex_map.values(), startangle=90, autopct='%1.0f%%', 
                                           colors=colors, textprops={'color': fg}, 
                                           wedgeprops={'linewidth': 1, 'edgecolor': bg})
            self.ax_pie.add_artist(plt.Circle((0,0),0.70,fc=bg))
            leg = self.ax_pie.legend(wedges, ex_map.keys(), loc="center left", bbox_to_anchor=(0.9, 0, 0.5, 1), frameon=False)
            plt.setp(leg.get_texts(), color=fg)
        else:
            self.ax_pie.text(0.5, 0.5, "No Expenses", ha='center', va='center', color=fg)
        
        self.fig_pie.tight_layout()
        self.canvas_pie.draw()

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Expense Tracker")
        self.geometry("1280x720")
        
        theme = get_config_value('Settings', 'theme') or "System"
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.configure(fg_color=APP_BG_COLOR)

        initialize_db()
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=0, sticky="nsew")

        remembered = get_config_value('Auth', 'user')
        if remembered and user_exists(remembered):
            self.show_dash(remembered)
        else:
            self.show_login()

    def show_login(self):
        self._clear()
        LoginFrame(self.container, self.show_dash).pack(fill="both", expand=True)

    def show_dash(self, username): 
        self._clear()
        DashboardFrame(self.container, username, self.show_login).pack(fill="both", expand=True)

    def _clear(self):
        for w in self.container.winfo_children(): w.destroy()

if __name__ == "__main__":
    MainApp().mainloop()