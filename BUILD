python_requirements(
    name='reqs',
    source='pyproject.toml',
    resolve='logfire-package',
)

python_distribution(
    name='wheel',
    dependencies=['./logfire:logfire@resolve=logfire-package', ':reqs'],
    provides=setup_py(name='logfire', version='0.1.0'),
    wheel=True,
)
