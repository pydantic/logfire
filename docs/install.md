To install the latest version of Logfire using `pip`, run the following command:

```bash
pip install logfire --extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
```

Or if you're using `poetry`:

```bash
poetry source add logfire-source https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
poetry add logfire
```

You can also add it to your project requirements:

```txt title='requirements.txt'
--extra-index-url https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/
logfire
```

Or add to `pyproject.toml` if you're using `poetry`:

```toml title='pyproject.toml'
[[tool.poetry.source]]
name = "logfire-source"
url = "https://files.logfire.dev/NOdO2jZhxNh8ert5YFYfWkFa9IBVsT7Jher4y8sh6YlXSb9V1d/wheels/"

[tool.poetry.dependencies]
python = "^3.8"
pydantic = "^2.0"
python-dotenv = "^1.0.0"
requests = "^2.31.0"
pytest = "^7.4.2"
logfire = {version = "*", source = "logfire-source"}
```
