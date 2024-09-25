from flask import Flask

from app.db import db


def create_app():
    """Initialize app."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financial_calculator.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    from app.server.routes import main

    app.register_blueprint(main)

    with app.app_context():
        db.create_all()

    return app
