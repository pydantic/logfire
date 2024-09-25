# Structured Data and SQL :abacus: {#sql}

Query your data with pure, canonical PostgreSQL — all the control and (for many) nothing new to learn. We even provide direct access to the underlying Postgres database, which means that you can query Logfire using any Postgres-compatible tools you like.

This includes BI tools and dashboard-building platforms like

- Superset
- Grafana
- Google Looker Studio

As well as data science tools like

- Pandas
- SQLAlchemy
- `psql`

Using vanilla PostgreSQL as the querying language throughout the platform ensures a consistent, powerful, and flexible querying experience.

Another big advantage of using the most widely used SQL databases is that generative AI tools like ChatGPT are excellent at writing SQL for you.

Just include your Python objects in **Logfire** calls (lists, dict, dataclasses, Pydantic models, DataFrames, and more),
and it'll end up as structured data in our platform ready to be queried.

For example, using data from a `User` model, we could list users from the USA:

```sql
SELECT attributes->'result'->>'name' as name, extract(year from (attributes->'result'->>'dob')::date) as "birth year"
FROM records
WHERE attributes->'result'->>'country_code' = 'USA';
```

![Logfire explore query screenshot](../images/index/logfire-screenshot-explore-query.png)

You can also filter to show only traces related to users in the USA in the live view with

```sql
attributes->'result'->>'name' = 'Ben'
```

![Logfire search query screenshot](../images/index/logfire-screenshot-search-query.png)


Structured Data and Direct SQL Access means you can use familiar tools like Pandas, SQLAlchemy, or `psql`
for querying, can integrate seamlessly with BI tools, and can even leverage AI for SQL generation, ensuring your Python
objects and structured data are query-ready.
