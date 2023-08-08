python_requirements(
    name="reqs",
    source="pyproject.toml",
)

python_distribution(
    name="wheel",
    dependencies=["./logfire:logfire", ":reqs"],
    provides=setup_py(name="logfire", version="0.1.0"),
    wheel=True,
)
