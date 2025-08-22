from flask import Flask, render_template, request, redirect, url_for
import os
import click
import database
from datetime import date, timedelta
import functools
import io
import csv
from werkzeug.security import check_password_hash
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, Response
)

app = Flask(__name__)
# It's crucial to set a secret key for session management
app.config['SECRET_KEY'] = 'a_truly_random_secret_key_for_production'

# Ensure the instance folder exists
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

# Add a command to initialize the database
@app.cli.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    database.init_db()
    click.echo('Initialized the database.')

@app.cli.command('create-user')
@click.argument('username')
@click.argument('password')
def create_user_command(username, password):
    """Create a new user."""
    database.add_user(username, password)
    click.echo(f'User {username} created.')

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        # In a real app, you'd fetch the full user object from the DB
        # For this simple app, just knowing the user_id is enough to be "logged in"
        g.user = {'id': user_id}

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        user = database.get_user(username)

        if user is None:
            error = 'نام کاربری اشتباه است.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'رمز عبور اشتباه است.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            flash('شما با موفقیت وارد شدید.', 'success')
            return redirect(url_for('index'))

        flash(error, 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/settings')
@login_required
def settings():
    services = database.get_all_services()
    staff = database.get_all_staff()
    accounts = database.get_accounts()

    services_with_payouts = []
    for service in services:
        payouts = database.get_payouts_for_service(service['id'])
        total_percentage = sum(p['percentage'] for p in payouts)
        services_with_payouts.append({
            'id': service['id'],
            'name': service['name'],
            'price': service['price'],
            'payouts': payouts,
            'total_percentage': total_percentage
        })

    return render_template('settings.html',
                           services=services,
                           staff=staff,
                           accounts=accounts,
                           services_with_payouts=services_with_payouts)

@app.route('/add_payout', methods=['POST'])
@login_required
def add_payout():
    service_id = request.form.get('service_id')
    staff_id = request.form.get('staff_id')
    percentage = request.form.get('percentage')

    if staff_id == 'clinic':
        staff_id = None

    if service_id and percentage:
        database.add_payout(service_id, staff_id, percentage)
        flash('سهم با موفقیت اضافه شد.', 'success')

    return redirect(url_for('settings'))

@app.route('/add_staff', methods=['POST'])
@login_required
def add_staff():
    name = request.form['name']
    payment_type = request.form['payment_type']
    payment_rate = request.form['payment_rate'] or 0
    if name and payment_type:
        database.add_staff(name, payment_type, float(payment_rate))
        flash('عضو جدید با موفقیت اضافه شد.', 'success')
    return redirect(url_for('settings'))

@app.route('/add_service', methods=['POST'])
@login_required
def add_service():
    name = request.form.get('name')
    price = request.form.get('price')
    revenue_account_id = request.form.get('revenue_account_id')
    if name and price and revenue_account_id:
        database.add_service(name, float(price), revenue_account_id)
        flash('خدمت جدید با موفقیت اضافه شد.', 'success')
    return redirect(url_for('settings'))

@app.route('/edit_service/<int:id>', methods=('GET', 'POST'))
@login_required
def edit_service(id):
    service = database.get_service_by_id(id)
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        revenue_account_id = request.form['revenue_account_id']
        database.update_service(id, name, float(price), revenue_account_id)
        flash('خدمت با موفقیت ویرایش شد.', 'success')
        return redirect(url_for('settings'))

    accounts = database.get_accounts()
    return render_template('edit_service.html', service=service, accounts=accounts)

@app.route('/delete_service/<int:id>', methods=('POST',))
@login_required
def delete_service(id):
    database.delete_service(id)
    flash('خدمت با موفقیت حذف شد.', 'success')
    return redirect(url_for('settings'))

@app.route('/edit_staff/<int:id>', methods=('GET', 'POST'))
@login_required
def edit_staff(id):
    staff = database.get_staff_by_id(id)
    if request.method == 'POST':
        name = request.form['name']
        payment_type = request.form['payment_type']
        payment_rate = request.form['payment_rate'] or 0
        database.update_staff(id, name, payment_type, float(payment_rate))
        flash('عضو با موفقیت ویرایش شد.', 'success')
        return redirect(url_for('settings'))
    return render_template('edit_staff.html', staff=staff)

@app.route('/delete_staff/<int:id>', methods=('POST',))
@login_required
def delete_staff(id):
    database.delete_staff(id)
    flash('عضو با موفقیت حذف شد.', 'success')
    return redirect(url_for('settings'))

@app.route('/transaction/reverse/<int:transaction_id>', methods=('POST',))
@login_required
def reverse_transaction(transaction_id):
    original_entries = database.get_journal_entries_by_transaction_id(transaction_id)

    if original_entries:
        # Get description from the first entry's transaction meta
        trans_meta = database.get_transaction_by_id(transaction_id) # Need to create this function
        new_description = f"Reversal of Transaction #{transaction_id}: {trans_meta['description']}"

        reversed_entries = []
        for entry in original_entries:
            # Swap debit and credit
            reversed_entries.append((entry['account_id'], entry['credit'], entry['debit']))

        database.create_journal_entry(date.today().strftime('%Y-%m-%d'), new_description, reversed_entries)
        flash(f'تراکنش شماره {transaction_id} با موفقیت معکوس شد.', 'success')
    else:
        flash('خطا: تراکنش مورد نظر یافت نشد.', 'error')

    return redirect(url_for('ledger'))

@app.route('/ledger')
@login_required
def ledger():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    account_id = request.args.get('account_id')

    entries = database.get_journal_entries_filtered(start_date, end_date, account_id)
    accounts = database.get_accounts()

    return render_template('ledger.html',
                           entries=entries,
                           accounts=accounts,
                           selected_account_id=int(account_id) if account_id else None,
                           start_date=start_date,
                           end_date=end_date)

@app.route('/export/ledger')
@login_required
def export_ledger():
    entries = database.get_all_journal_entries()

    # Use an in-memory text stream
    si = io.StringIO()
    cw = csv.writer(si)

    # Write header
    cw.writerow(['Date', 'Transaction ID', 'Description', 'Account', 'Debit', 'Credit'])

    # Write data rows
    for entry in entries:
        cw.writerow([
            entry['date'],
            entry['transaction_id'],
            entry['description'],
            entry['account_name'],
            entry['debit'],
            entry['credit']
        ])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition":
                 "attachment; filename=ledger_export.csv"})

@app.route('/reports/balance-sheet')
@login_required
def balance_sheet():
    balances = database.get_account_balances()

    assets = []
    liabilities = []
    equity = []
    total_assets = 0
    total_liabilities = 0
    total_equity = 0

    for acc in balances:
        balance = (acc['total_debit'] or 0) - (acc['total_credit'] or 0)
        # For Liability, Equity, we flip the sign because credits are positive
        if acc['type'] in ('Liability', 'Equity'):
            balance = -balance

        if acc['type'] == 'Asset':
            assets.append({'name': acc['name'], 'balance': balance})
            total_assets += balance
        elif acc['type'] == 'Liability':
            liabilities.append({'name': acc['name'], 'balance': balance})
            total_liabilities += balance
        elif acc['type'] == 'Equity':
            equity.append({'name': acc['name'], 'balance': balance})
            total_equity += balance

    return render_template('reports/balance_sheet.html',
                           assets=assets,
                           liabilities=liabilities,
                           equity=equity,
                           total_assets=total_assets,
                           total_liabilities=total_liabilities,
                           total_equity=total_equity,
                           today_date=date.today().strftime('%Y-%m-%d'))


@app.route('/reports/trial-balance')
@login_required
def trial_balance():
    balances = database.get_account_balances()

    debit_total = 0
    credit_total = 0

    accounts_with_balance = []
    for acc in balances:
        balance = (acc['total_debit'] or 0) - (acc['total_credit'] or 0)
        debit_balance = 0
        credit_balance = 0

        if acc['type'] in ('Asset', 'Expense'):
            if balance > 0:
                debit_balance = balance
            else:
                credit_balance = -balance
        else: # Liability, Equity, Revenue
            if balance < 0:
                credit_balance = -balance
            else:
                debit_balance = balance

        if debit_balance > 0 or credit_balance > 0:
            accounts_with_balance.append({
                'name': acc['name'],
                'debit': debit_balance,
                'credit': credit_balance
            })
            debit_total += debit_balance
            credit_total += credit_balance

    return render_template('reports/trial_balance.html',
                           accounts=accounts_with_balance,
                           debit_total=debit_total,
                           credit_total=credit_total,
                           today_date=date.today().strftime('%Y-%m-%d'))


@app.route('/reports')
@login_required
def reports():
    end_date_str = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    # Default start_date to the beginning of the current month
    start_date_str = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))

    balances = database.get_account_balances(start_date_str, end_date_str)

    revenue_accounts = []
    expense_accounts = []
    total_revenue = 0
    total_expense = 0

    for acc in balances:
        # For Revenue accounts, credit is positive
        if acc['type'] == 'Revenue':
            balance = (acc['total_credit'] or 0) - (acc['total_debit'] or 0)
            if balance > 0:
                revenue_accounts.append({'name': acc['name'], 'balance': balance})
                total_revenue += balance
        # For Expense accounts, debit is positive
        elif acc['type'] == 'Expense':
            balance = (acc['total_debit'] or 0) - (acc['total_credit'] or 0)
            if balance > 0:
                expense_accounts.append({'name': acc['name'], 'balance': balance})
                total_expense += balance

    net_profit = total_revenue - total_expense

    return render_template('reports/profit_and_loss.html',
                           revenue_accounts=revenue_accounts,
                           expense_accounts=expense_accounts,
                           total_revenue=total_revenue,
                           total_expense=total_expense,
                           net_profit=net_profit,
                           start_date=start_date_str,
                           end_date=end_date_str)

@app.route('/data-entry')
@login_required
def data_entry():
    services = database.get_all_services()
    accounts = database.get_accounts()
    today = date.today().strftime('%Y-%m-%d')
    return render_template('data_entry.html', services=services, accounts=accounts, today=today)

@app.route('/add_income', methods=['POST'])
@login_required
def add_income():
    trans_date = request.form.get('date')
    service_id = int(request.form.get('service_id'))
    quantity = int(request.form.get('quantity', 1))
    customer_name = request.form.get('customer_name')

    service = database.get_service_by_id(service_id)
    if service and quantity > 0:
        total_revenue = service['price'] * quantity
        description = f"درآمد از {quantity} عدد {service['name']} برای {customer_name}"

        accounts = database.get_accounts()
        ar_account = next((acc for acc in accounts if acc['name'] == 'حساب دریافتنی'), None)

        if ar_account:
            entries = [
                (ar_account['id'], total_revenue, 0),
                (service['revenue_account_id'], 0, total_revenue)
            ]
            database.create_journal_entry(trans_date, description, entries)
            flash('تراکنش درآمد با موفقیت ثبت شد.', 'success')
        else:
            flash('خطا: حساب دریافتنی پیش‌فرض یافت نشد. لطفاً یک حساب با نام "حساب دریافتنی" از نوع دارایی بسازید.', 'error')

    return redirect(url_for('data_entry'))

@app.route('/receive_payment', methods=['POST'])
@login_required
def receive_payment():
    trans_date = request.form.get('date')
    customer_name = request.form.get('customer_name')
    amount = float(request.form.get('amount', 0))
    asset_account_id = request.form.get('asset_account_id')

    if amount > 0 and customer_name and asset_account_id:
        accounts = database.get_accounts()
        ar_account = next((acc for acc in accounts if acc['name'] == 'حساب دریافتنی'), None)

        if ar_account:
            description = f"دریافت وجه از {customer_name}"
            entries = [
                (asset_account_id, amount, 0),
                (ar_account['id'], 0, amount)
            ]
            database.create_journal_entry(trans_date, description, entries)
            flash('دریافت وجه با موفقیت ثبت شد.', 'success')
        else:
            flash('خطا: حساب دریافتنی پیش‌فرض یافت نشد. لطفاً یک حساب با نام "حساب دریافتنی" از نوع دارایی بسازید.', 'error')

    return redirect(url_for('data_entry'))

@app.route('/pay_bill', methods=['POST'])
@login_required
def pay_bill():
    trans_date = request.form.get('date')
    vendor_name = request.form.get('vendor_name')
    amount = float(request.form.get('amount', 0))
    asset_account_id = request.form.get('asset_account_id')

    if amount > 0 and vendor_name and asset_account_id:
        accounts = database.get_accounts()
        ap_account = next((acc for acc in accounts if acc['name'] == 'حساب پرداختنی'), None)

        if ap_account:
            description = f"پرداخت وجه به {vendor_name}"
            entries = [
                (ap_account['id'], amount, 0),
                (asset_account_id, 0, amount)
            ]
            database.create_journal_entry(trans_date, description, entries)
            flash('پرداخت وجه با موفقیت ثبت شد.', 'success')
        else:
            flash('خطا: حساب پرداختنی پیش‌فرض یافت نشد. لطفاً یک حساب با نام "حساب پرداختنی" از نوع بدهی بسازید.', 'error')

    return redirect(url_for('data_entry'))

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    trans_date = request.form.get('date')
    description = request.form.get('description')
    amount = float(request.form.get('amount', 0))
    expense_account_id = request.form.get('expense_account_id')
    asset_account_id = request.form.get('asset_account_id')

    if amount > 0 and description and expense_account_id and asset_account_id:
        entries = [
            (expense_account_id, amount, 0),
            (asset_account_id, 0, amount)
        ]
        database.create_journal_entry(trans_date, description, entries)
        flash('هزینه با موفقیت ثبت شد.', 'success')

    return redirect(url_for('data_entry'))

@app.route('/add_ledger_entry', methods=['POST'])
@login_required
def add_ledger_entry():
    transaction_date = request.form.get('transaction_date') or date.today().strftime('%Y-%m-%d')
    trans_type = request.form.get('type')
    entity_name = request.form.get('entity_name')
    description = request.form.get('description')
    amount = request.form.get('amount')

    if trans_type in ['Payable', 'Receivable'] and entity_name and description and amount:
        database.add_transaction(trans_type, description, float(amount), transaction_date, entity=entity_name)

    return redirect(url_for('data_entry'))

@app.route('/chart-of-accounts')
@login_required
def chart_of_accounts():
    accounts = database.get_accounts()
    # Group accounts by type for display
    grouped_accounts = {}
    for acc in accounts:
        if acc['type'] not in grouped_accounts:
            grouped_accounts[acc['type']] = []
        grouped_accounts[acc['type']].append(acc)
    return render_template('chart_of_accounts.html', grouped_accounts=grouped_accounts)

@app.route('/add-account', methods=['POST'])
@login_required
def add_account():
    name = request.form.get('name')
    type = request.form.get('type')
    if name and type:
        database.add_account(name, type)
        flash('حساب جدید با موفقیت اضافه شد.', 'success')
    return redirect(url_for('chart_of_accounts'))

@app.route('/edit_account/<int:id>', methods=('GET', 'POST'))
@login_required
def edit_account(id):
    account = database.get_account_by_id(id)
    if request.method == 'POST':
        name = request.form['name']
        type = request.form['type']
        database.update_account(id, name, type)
        flash('حساب با موفقیت ویرایش شد.', 'success')
        return redirect(url_for('chart_of_accounts'))
    return render_template('edit_account.html', account=account)

@app.route('/delete_account/<int:id>', methods=('POST',))
@login_required
def delete_account(id):
    database.delete_account(id)
    flash('حساب با موفقیت حذف شد.', 'success')
    return redirect(url_for('chart_of_accounts'))

@app.route('/')
@login_required
def index():
    end_date_str = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    start_date_str = request.args.get('start_date', (date.today() - timedelta(days=29)).strftime('%Y-%m-%d'))

    # Use the new, correct function
    period_balances = database.get_account_balances(start_date_str, end_date_str)
    all_time_balances = database.get_account_balances() # For A/R and A/P which are point-in-time

    total_revenue = 0
    total_expense = 0
    total_receivables = 0
    total_payables = 0

    for acc in period_balances:
        balance = (acc['total_debit'] or 0) - (acc['total_credit'] or 0)
        if acc['type'] == 'Revenue':
            total_revenue += -balance # Credits are positive for revenue
        elif acc['type'] == 'Expense':
            total_expense += balance # Debits are positive for expense

    for acc in all_time_balances:
        balance = (acc['total_debit'] or 0) - (acc['total_credit'] or 0)
        if acc['name'] == 'حساب دریافتنی': # Look up by name
            total_receivables = balance
        elif acc['name'] == 'حساب پرداختنی': # Look up by name
            total_payables = -balance

    net_profit = total_revenue - total_expense

    # --- Charts are temporarily disabled as their logic needs to be rewritten ---

    return render_template('index.html',
                           total_revenue=total_revenue,
                           total_expense=total_expense,
                           net_profit=net_profit,
                           total_receivables=total_receivables,
                           total_payables=total_payables,
                           start_date=start_date_str,
                           end_date=end_date_str)

if __name__ == '__main__':
    app.run(debug=True)
