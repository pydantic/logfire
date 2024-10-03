import logfire

logfire.install_auto_tracing(modules=['app'], min_duration=0)

from app import app, db  # noqa  # needs to be imported after install_auto_tracing

logfire.configure()
logfire.instrument_flask(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'  # in-memory database

db.init_app(app)

with app.app_context():
    logfire.instrument_sqlalchemy(engine=db.engine)
    db.create_all()

app.run(debug=True)
