from flask import Blueprint, jsonify, render_template, request

from app.db import db
from app.db.models import Calculation

main = Blueprint('main', __name__)


@main.route('/')
def index():
    """Render the calculator view."""
    return render_template('index.html')


@main.route('/calculate', methods=['POST'])
def calculate():
    """Calculate the value."""
    data = request.json
    calculation_type = data['type']
    result = 0

    if calculation_type == 'compound_interest':
        principal = float(data['principal'])
        rate = float(data['rate'])
        time = float(data['time'])
        compounds_per_year = int(data['compounds_per_year'])
        result = principal * (1 + rate / compounds_per_year) ** (compounds_per_year * time)
    elif calculation_type == 'loan_payment':
        principal = float(data['principal'])
        rate = float(data['rate'])
        time = float(data['time'])
        monthly_rate = rate / 12
        num_payments = time * 12
        result = (
            principal * (monthly_rate * (1 + monthly_rate) ** num_payments) / ((1 + monthly_rate) ** num_payments - 1)
        )

    new_calculation = Calculation(type=calculation_type, input_data=str(data), result=result)
    db.session.add(new_calculation)
    db.session.commit()

    return jsonify({'result': result})


@main.route('/history')
def history():
    """Render the history view."""
    calculations = Calculation.query.order_by(Calculation.timestamp.desc()).limit(10).all()
    return render_template('history.html', calculations=calculations)
