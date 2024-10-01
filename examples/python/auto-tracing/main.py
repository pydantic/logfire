import logfire

logfire.configure()
logfire.install_auto_tracing(modules=['app'], min_duration=0)

from app.db import db  # noqa
from app.server import app  # noqa

db.init_app(app)

logfire.instrument_sqlalchemy()
logfire.instrument_flask(app)

with app.app_context():
    db.create_all()

app.run(debug=True)
