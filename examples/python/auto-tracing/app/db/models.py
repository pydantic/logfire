from datetime import datetime

from . import db


class Calculation(db.Model):
    """Store calculation information."""

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    input_data = db.Column(db.String(200), nullable=False)
    result = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
