from app.main import main

import logfire

logfire.configure()
logfire.install_auto_tracing(modules=['app'])

main()
