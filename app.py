from flask import Flask, render_template, request, redirect, url_for
import os
import click
import database
from datetime import date, timedelta

app = Flask(__name__)

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

@app.route('/settings')
def settings():
    services = database.get_all_services()
    staff = database.get_all_staff()

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
                           services_with_payouts=services_with_payouts)

@app.route('/add_payout', methods=['POST'])
def add_payout():
    service_id = request.form.get('service_id')
    staff_id = request.form.get('staff_id')
    percentage = request.form.get('percentage')

    if staff_id == 'clinic':
        staff_id = None

    if service_id and percentage:
        database.add_payout(service_id, staff_id, percentage)

    return redirect(url_for('settings'))

@app.route('/add_staff', methods=['POST'])
def add_staff():
    name = request.form['name']
    payment_type = request.form['payment_type']
    payment_rate = request.form['payment_rate'] or 0
    if name and payment_type:
        database.add_staff(name, payment_type, float(payment_rate))
    return redirect(url_for('settings'))

@app.route('/add_service', methods=['POST'])
def add_service():
    name = request.form.get('name')
    price = request.form.get('price')
    if name and price:
        database.add_service(name, float(price))
    return redirect(url_for('settings'))

@app.route('/data-entry')
def data_entry():
    services = database.get_all_services()
    today = date.today().strftime('%Y-%m-%d')
    return render_template('data_entry.html', services=services, today=today)

@app.route('/add_daily_income', methods=['POST'])
def add_daily_income():
    transaction_date = request.form.get('transaction_date') or date.today().strftime('%Y-%m-%d')

    service_ids = request.form.getlist('service_id[]')
    quantities = request.form.getlist('quantity[]')

    for i in range(len(service_ids)):
        if not service_ids[i] or not quantities[i]:
            continue

        service_id = int(service_ids[i])
        quantity = int(quantities[i])

        if quantity > 0:
            service = database.get_service_by_id(service_id)
            if not service:
                continue

            total_revenue = service['price'] * quantity

            income_desc = f"درآمد از {quantity} عدد {service['name']}"
            database.add_transaction('Income', income_desc, total_revenue, transaction_date, service_id=service_id)

            payouts = database.get_payouts_for_service(service_id)
            for payout in payouts:
                payout_amount = total_revenue * (payout['percentage'] / 100.0)
                if payout['staff_name']:
                    payable_desc = f"سهم قابل پرداخت برای {service['name']} به {payout['staff_name']}"
                    database.add_transaction('Payable', payable_desc, payout_amount, transaction_date, entity=payout['staff_name'])

    return redirect(url_for('data_entry'))

@app.route('/add_expense', methods=['POST'])
def add_expense():
    transaction_date = request.form.get('transaction_date') or date.today().strftime('%Y-%m-%d')
    description = request.form.get('description')
    amount = request.form.get('amount')

    if description and amount:
        database.add_transaction('Expense', description, float(amount), transaction_date)

    return redirect(url_for('data_entry'))

@app.route('/add_ledger_entry', methods=['POST'])
def add_ledger_entry():
    transaction_date = request.form.get('transaction_date') or date.today().strftime('%Y-%m-%d')
    trans_type = request.form.get('type')
    entity_name = request.form.get('entity_name')
    description = request.form.get('description')
    amount = request.form.get('amount')

    if trans_type in ['Payable', 'Receivable'] and entity_name and description and amount:
        database.add_transaction(trans_type, description, float(amount), transaction_date, entity=entity_name)

    return redirect(url_for('data_entry'))

@app.route('/')
def index():
    # Define date range (e.g., last 30 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    # Fetch data
    summary = database.get_transactions_summary(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    ledger_totals = database.get_unsettled_ledger_totals()
    daily_series = database.get_daily_income_expense_series(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    income_by_service = database.get_income_by_service(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

    # Prepare data for charts
    line_chart_labels = [d['transaction_date'] for d in daily_series]
    line_chart_income = [d['daily_income'] for d in daily_series]
    line_chart_expense = [d['daily_expense'] for d in daily_series]

    pie_chart_labels = [d['name'] for d in income_by_service]
    pie_chart_data = [d['total_amount'] for d in income_by_service]

    return render_template('index.html',
                           summary=summary,
                           ledger_totals=ledger_totals,
                           line_chart_labels=line_chart_labels,
                           line_chart_income=line_chart_income,
                           line_chart_expense=line_chart_expense,
                           pie_chart_labels=pie_chart_labels,
                           pie_chart_data=pie_chart_data,
                           date_range=30)

if __name__ == '__main__':
    app.run(debug=True)
