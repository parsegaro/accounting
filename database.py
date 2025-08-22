import sqlite3
import os
from werkzeug.security import generate_password_hash

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'clinic.db')

def get_db_connection():
    """Creates a database connection."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Drop existing tables to start fresh (for development)
    # Order is important due to foreign keys
    cursor.execute("DROP TABLE IF EXISTS journal_entries;")
    cursor.execute("DROP TABLE IF EXISTS transactions;")
    cursor.execute("DROP TABLE IF EXISTS accounts;")
    cursor.execute("DROP TABLE IF EXISTS service_payouts;")
    cursor.execute("DROP TABLE IF EXISTS services;")
    cursor.execute("DROP TABLE IF EXISTS staff;")
    cursor.execute("DROP TABLE IF EXISTS users;")

    # Create users table
    cursor.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    );
    """)

    # Create Chart of Accounts table
    cursor.execute("""
    CREATE TABLE accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL CHECK(type IN ('Asset', 'Liability', 'Equity', 'Revenue', 'Expense'))
    );
    """)

    # Create services table
    cursor.execute("""
    CREATE TABLE services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        price REAL NOT NULL,
        revenue_account_id INTEGER NOT NULL,
        FOREIGN KEY (revenue_account_id) REFERENCES accounts (id)
    );
    """)

    # Create staff table
    cursor.execute("""
    CREATE TABLE staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        payment_type TEXT NOT NULL CHECK(payment_type IN ('Monthly', 'Hourly', 'Percentage')),
        payment_rate REAL NOT NULL DEFAULT 0
    );
    """)

    # Create service_payouts table for revenue sharing
    cursor.execute("""
    CREATE TABLE service_payouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_id INTEGER NOT NULL,
        staff_id INTEGER, -- Can be NULL for clinic's share
        percentage REAL NOT NULL,
        FOREIGN KEY (service_id) REFERENCES services (id),
        FOREIGN KEY (staff_id) REFERENCES staff (id)
    );
    """)

    # Create transactions table (meta-data for a transaction)
    cursor.execute("""
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        description TEXT NOT NULL
    );
    """)

    # Create journal_entries table (the actual double-entry ledger)
    cursor.execute("""
    CREATE TABLE journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        debit REAL NOT NULL DEFAULT 0,
        credit REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (transaction_id) REFERENCES transactions (id),
        FOREIGN KEY (account_id) REFERENCES accounts (id)
    );
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()

def get_all_services():
    conn = get_db_connection()
    services = conn.execute('SELECT * FROM services ORDER BY name').fetchall()
    conn.close()
    return services

def add_service(name, price, revenue_account_id):
    conn = get_db_connection()
    conn.execute('INSERT INTO services (name, price, revenue_account_id) VALUES (?, ?, ?)',
                 (name, price, revenue_account_id))
    conn.commit()
    conn.close()

def update_service(id, name, price, revenue_account_id):
    conn = get_db_connection()
    conn.execute('UPDATE services SET name = ?, price = ?, revenue_account_id = ? WHERE id = ?',
                 (name, price, revenue_account_id, id))
    conn.commit()
    conn.close()

def delete_service(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM services WHERE id = ?', (id,))
    conn.commit()
    conn.close()

def get_staff_by_id(id):
    conn = get_db_connection()
    staff = conn.execute('SELECT * FROM staff WHERE id = ?', (id,)).fetchone()
    conn.close()
    return staff

def update_staff(id, name, payment_type, payment_rate):
    conn = get_db_connection()
    conn.execute('UPDATE staff SET name = ?, payment_type = ?, payment_rate = ? WHERE id = ?',
                 (name, payment_type, payment_rate, id))
    conn.commit()
    conn.close()

def delete_staff(id):
    conn = get_db_connection()
    # Also need to delete associated payouts
    conn.execute('DELETE FROM service_payouts WHERE staff_id = ?', (id,))
    conn.execute('DELETE FROM staff WHERE id = ?', (id,))
    conn.commit()
    conn.close()

def get_all_staff():
    conn = get_db_connection()
    staff = conn.execute('SELECT * FROM staff ORDER BY name').fetchall()
    conn.close()
    return staff

def add_staff(name, payment_type, payment_rate):
    conn = get_db_connection()
    conn.execute('INSERT INTO staff (name, payment_type, payment_rate) VALUES (?, ?, ?)',
                 (name, payment_type, payment_rate))
    conn.commit()
    conn.close()

def get_payouts_for_service(service_id):
    conn = get_db_connection()
    payouts = conn.execute("""
        SELECT sp.percentage, s.name as staff_name
        FROM service_payouts sp
        LEFT JOIN staff s ON sp.staff_id = s.id
        WHERE sp.service_id = ?
    """, (service_id,)).fetchall()
    conn.close()
    return payouts

def add_payout(service_id, staff_id, percentage):
    conn = get_db_connection()
    conn.execute('INSERT INTO service_payouts (service_id, staff_id, percentage) VALUES (?, ?, ?)',
                 (service_id, staff_id, float(percentage)))
    conn.commit()
    conn.close()

def get_service_by_id(service_id):
    conn = get_db_connection()
    service = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    conn.close()
    return service


def get_accounts():
    conn = get_db_connection()
    accounts = conn.execute('SELECT * FROM accounts ORDER BY type, name').fetchall()
    conn.close()
    return accounts

def add_account(name, type):
    conn = get_db_connection()
    conn.execute('INSERT INTO accounts (name, type) VALUES (?, ?)', (name, type))
    conn.commit()
    conn.close()

def get_account_by_id(id):
    conn = get_db_connection()
    account = conn.execute('SELECT * FROM accounts WHERE id = ?', (id,)).fetchone()
    conn.close()
    return account

def update_account(id, name, type):
    conn = get_db_connection()
    conn.execute('UPDATE accounts SET name = ?, type = ? WHERE id = ?', (name, type, id))
    conn.commit()
    conn.close()

def delete_account(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM accounts WHERE id = ?', (id,))
    conn.commit()
    conn.close()

def get_transaction_by_id(transaction_id):
    conn = get_db_connection()
    trans = conn.execute('SELECT * FROM transactions WHERE id = ?', (transaction_id,)).fetchone()
    conn.close()
    return trans

def get_journal_entries_by_transaction_id(transaction_id):
    conn = get_db_connection()
    entries = conn.execute('SELECT * FROM journal_entries WHERE transaction_id = ?', (transaction_id,)).fetchall()
    conn.close()
    return entries

def get_journal_entries_filtered(start_date=None, end_date=None, account_id=None):
    conn = get_db_connection()

    query = """
        SELECT
            t.id as transaction_id,
            t.date,
            t.description,
            a.name as account_name,
            je.debit,
            je.credit
        FROM journal_entries je
        JOIN transactions t ON je.transaction_id = t.id
        JOIN accounts a ON je.account_id = a.id
    """
    params = []
    where_clauses = []

    if start_date:
        where_clauses.append("t.date >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("t.date <= ?")
        params.append(end_date)
    if account_id:
        where_clauses.append("je.account_id = ?")
        params.append(account_id)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY t.date DESC, t.id DESC, je.id ASC"

    entries = conn.execute(query, params).fetchall()
    conn.close()
    return entries

def get_account_balances(start_date=None, end_date=None):
    conn = get_db_connection()

    query = """
        SELECT
            a.id,
            a.name,
            a.type,
            SUM(je.debit) as total_debit,
            SUM(je.credit) as total_credit
        FROM accounts a
        LEFT JOIN journal_entries je ON a.id = je.account_id
        LEFT JOIN transactions t ON je.transaction_id = t.id
    """
    params = []
    if start_date and end_date:
        query += " WHERE t.date BETWEEN ? AND ?"
        params.extend([start_date, end_date])

    query += " GROUP BY a.id, a.name, a.type ORDER BY a.type, a.name"

    balances = conn.execute(query, params).fetchall()
    conn.close()
    return balances

def create_journal_entry(date, description, entries):
    """
    Creates a new transaction with multiple journal entries.
    'entries' should be a list of tuples: (account_id, debit, credit)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create a new transaction meta-record
    cursor.execute('INSERT INTO transactions (date, description) VALUES (?, ?)', (date, description))
    transaction_id = cursor.lastrowid

    # Add all journal entries for this transaction
    for account_id, debit, credit in entries:
        cursor.execute("""
            INSERT INTO journal_entries (transaction_id, account_id, debit, credit)
            VALUES (?, ?, ?, ?)
        """, (transaction_id, account_id, debit, credit))

    conn.commit()
    conn.close()

def add_user(username, password):
    conn = get_db_connection()
    conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                 (username, generate_password_hash(password)))
    conn.commit()
    conn.close()

def get_user(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return user
