import sqlite3
import os

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
    cursor.execute("DROP TABLE IF EXISTS service_payouts;")
    cursor.execute("DROP TABLE IF EXISTS transactions;")
    cursor.execute("DROP TABLE IF EXISTS services;")
    cursor.execute("DROP TABLE IF EXISTS staff;")

    # Create services table
    cursor.execute("""
    CREATE TABLE services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        price REAL NOT NULL
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

    # Create a unified transactions ledger
    cursor.execute("""
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_type TEXT NOT NULL CHECK(transaction_type IN ('Income', 'Expense', 'Payable', 'Receivable')),
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        transaction_date TEXT NOT NULL,
        entity_name TEXT,
        related_service_id INTEGER,
        is_settled BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (related_service_id) REFERENCES services (id)
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
    print(f"---- FETCHED services: {[s['name'] for s in services]} ----")
    conn.close()
    return services

def add_service(name, price):
    conn = get_db_connection()
    conn.execute('INSERT INTO services (name, price) VALUES (?, ?)', (name, price))
    conn.commit()
    print(f"---- COMMITTED service: {name} ----")
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

def add_transaction(trans_type, desc, amount, date, entity=None, service_id=None, settled=0):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO transactions
        (transaction_type, description, amount, transaction_date, entity_name, related_service_id, is_settled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (trans_type, desc, amount, date, entity, service_id, settled))
    conn.commit()
    conn.close()

def get_transactions_summary(start_date, end_date):
    conn = get_db_connection()
    summary = conn.execute("""
        SELECT
            SUM(CASE WHEN transaction_type = 'Income' THEN amount ELSE 0 END) as total_income,
            SUM(CASE WHEN transaction_type = 'Expense' THEN amount ELSE 0 END) as total_expenses
        FROM transactions
        WHERE transaction_date BETWEEN ? AND ?
    """, (start_date, end_date)).fetchone()
    conn.close()
    return summary

def get_unsettled_ledger_totals():
    conn = get_db_connection()
    totals = conn.execute("""
        SELECT
            SUM(CASE WHEN transaction_type = 'Receivable' THEN amount ELSE 0 END) as total_receivables,
            SUM(CASE WHEN transaction_type = 'Payable' THEN amount ELSE 0 END) as total_payables
        FROM transactions
        WHERE is_settled = 0 AND transaction_type IN ('Receivable', 'Payable')
    """).fetchone()
    conn.close()
    return totals

def get_daily_income_expense_series(start_date, end_date):
    conn = get_db_connection()
    series = conn.execute("""
        SELECT
            transaction_date,
            SUM(CASE WHEN transaction_type = 'Income' THEN amount ELSE 0 END) as daily_income,
            SUM(CASE WHEN transaction_type = 'Expense' THEN amount ELSE 0 END) as daily_expense
        FROM transactions
        WHERE transaction_date BETWEEN ? AND ?
        GROUP BY transaction_date
        ORDER BY transaction_date
    """, (start_date, end_date)).fetchall()
    conn.close()
    return series

def get_income_by_service(start_date, end_date):
    conn = get_db_connection()
    income_dist = conn.execute("""
        SELECT
            s.name,
            SUM(t.amount) as total_amount
        FROM transactions t
        JOIN services s ON t.related_service_id = s.id
        WHERE t.transaction_type = 'Income' AND t.transaction_date BETWEEN ? AND ?
        GROUP BY s.name
        ORDER BY total_amount DESC
    """, (start_date, end_date)).fetchall()
    conn.close()
    return income_dist
