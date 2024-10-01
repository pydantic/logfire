import logfire

logfire.configure()
logfire.install_auto_tracing(modules=['app'], min_duration=0)

from app import app, db  # noqa  # needs to be imported after auto-tracing

logfire.instrument_sqlalchemy()
logfire.instrument_flask(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'  # in-memory database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

app.run(debug=True)
