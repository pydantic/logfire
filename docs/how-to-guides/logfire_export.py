# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx",
#     "logfire",
#     "polars",
#     "pyarrow",
#     "rich",
# ]
# ///
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Callable, Literal, ParamSpec, TypeVar, cast

import polars
from rich.progress import MofNCompleteColumn, Progress, TimeElapsedColumn, track

from logfire.experimental.query_client import AsyncLogfireQueryClient

read_token = os.environ['LOGFIRE_READ_TOKEN']
# we should use `/read-token-info` as a project identifier, not this
token_hash = hashlib.sha1(read_token[10:].encode()).hexdigest()[:5]
QUERY_LIMIT = 10_000
# this can be tweaked to improve performance:
# to get as many rows as possible per request while minimizing the number
# of intervals that need to be split
TARGET_QUERY_SIZE = 5_000

RECORDS_COLUMNS = [
    'project_id',
    'day',
    'start_timestamp',
    'end_timestamp',
    'duration',
    'trace_id',
    'span_id',
    'kind',
    'level',
    'parent_span_id',
    'span_name',
    'message',
    'log_body',
    'otel_status_code',
    'otel_status_message',
    'otel_links',
    'otel_events',
    'is_exception',
    'tags',
    'url_path',
    'url_query',
    'url_full',
    'http_route',
    'http_method',
    'attributes',
    'otel_scope_name',
    'otel_scope_version',
    'otel_scope_attributes',
    'service_namespace',
    'service_name',
    'service_version',
    'otel_resource_attributes',
    'service_instance_id',
    'process_pid',
    'telemetry_sdk_name',
    'telemetry_sdk_language',
    'telemetry_sdk_version',
    'deployment_environment',
]

METRICS_COLUMNS = [
    'project_id',
    'day',
    'recorded_timestamp',
    'metric_name',
    'metric_type',
    'unit',
    'start_timestamp',
    'aggregation_temporality',
    'is_monotonic',
    'metric_description',
    'scalar_value',
    'histogram_min',
    'histogram_max',
    'histogram_count',
    'histogram_sum',
    'histogram_bucket_counts',
    'histogram_explicit_bounds',
    'exp_histogram_scale',
    'exp_histogram_zero_count',
    'exp_histogram_zero_threshold',
    'exp_histogram_positive_bucket_counts',
    'exp_histogram_positive_bucket_counts_offset',
    'exp_histogram_negative_bucket_counts',
    'exp_histogram_negative_bucket_counts_offset',
    'exemplars',
    'attributes',
    'otel_scope_name',
    'otel_scope_version',
    'otel_scope_attributes',
    'service_namespace',
    'service_name',
    'service_version',
    'service_instance_id',
    'process_pid',
    'otel_resource_attributes',
    'telemetry_sdk_name',
    'telemetry_sdk_language',
    'telemetry_sdk_version',
    'deployment_environment',
]


async def main(export_date: date, table: Literal['records', 'metrics'] = 'records'):
    """Main entry point for exporting all records in a given interval from Pydantic Logfire."""
    print(f'Exporting data from {export_date}...')
    start_of_day = datetime(export_date.year, export_date.month, export_date.day)

    async with AsyncLogfireQueryClient(read_token=read_token) as client:
        data_frames = await export_day(client, start_of_day, table)

    day_parquet = Path(f'logfire_export_{table}_{token_hash}_{export_date}.parquet')
    first, *rest = data_frames
    df = polars.read_parquet(first)
    for path in track(rest, description='Merging dataframes...'):
        df.vstack(polars.read_parquet(path), in_place=True)
    print(f'Saving combined data with {df.height} rows to {day_parquet}...')
    df.write_parquet(day_parquet)
    print('done')


async def export_day(
    client: AsyncLogfireQueryClient, start: datetime, table: Literal['records', 'metrics']
) -> list[Path]:
    """Query for records or metrics for a given day, returning a list of Paths pointing to parquet files."""
    data_frames: list[Path] = []
    tic = time.perf_counter()
    filter_groups = await get_groups(client, start, table)
    diff = time.perf_counter() - tic
    print(f'  Counts complete in {diff:.2f}s')
    queries = build_queries(filter_groups, start)
    exceeded_limit = 0
    progress_total = len(queries)
    errors = 0

    with Progress(*Progress.get_default_columns(), TimeElapsedColumn(), MofNCompleteColumn()) as progress:
        progress_task = progress.add_task('  Downloading...', total=progress_total)
        queue: list[Query] = queries.copy()

        columns = ', '.join(RECORDS_COLUMNS if table == 'records' else METRICS_COLUMNS)

        async def worker() -> None:
            nonlocal exceeded_limit, progress_total, errors
            while True:
                try:
                    query = queue.pop()
                except IndexError:
                    break
                try:
                    df_path, df = await run_query(client, f'SELECT {columns} FROM {table} WHERE {query.where()}')
                    if df.height < QUERY_LIMIT:
                        del df
                        data_frames.append(df_path)
                        progress.update(progress_task, advance=1)
                    else:
                        # interval has more thank 10k rows we need to split the interval in half
                        lower, upper = query.split()
                        queue.extend([lower, upper])
                        progress_total += 1
                        progress.update(progress_task, total=progress_total)
                        exceeded_limit += 1
                except Exception as e:
                    errors += 1
                    if errors <= 20:
                        print(f'  RETRYING error running {query.where()!r} ({errors=}):\n    {e!r}')
                        await asyncio.sleep(5)
                        queue.append(query)
                    else:
                        print(f'  FATAL error running {query.where()!r} ({errors=}):\n    {e!r}')
                        raise

        await asyncio.gather(*[worker() for _ in range(15)])

        print(f'  done, {len(queries)} initial queries, {exceeded_limit} exceeded 10k limit and where split')
        return data_frames


async def get_groups(
    client: AsyncLogfireQueryClient, start: datetime, table: Literal['records', 'metrics']
) -> list[tuple[str, int]]:
    """Group records by partitions (service_name and deployment_environment) and collect counts for each group."""
    _, df = await run_query(
        client,
        f"""
        select
            service_name,
            deployment_environment,
            count(*) as count
            from {table}
            where date_trunc('day', created_at) = '{start:%Y-%m-%dT%H:%M:%S}'
            group by service_name, deployment_environment
        """,
    )
    filter_groups: list[tuple[str, int]] = []
    for row in df.iter_rows():
        service_name, deployment_environment, count = row
        if service_name is None:
            sql_filter = ['service_name IS NULL']
        else:
            sql_filter = [f"service_name='{service_name}'"]

        if deployment_environment is None:
            sql_filter.append('deployment_environment IS NULL')
        else:
            sql_filter.append(f"deployment_environment='{deployment_environment}'")

        filter_groups.append((' AND '.join(sql_filter), count))

    return filter_groups


@dataclass
class Query:
    filter_group: str
    lower_bound_inc: datetime
    upper_bound: datetime

    def where(self) -> str:
        return (
            self.filter_group
            + f" AND created_at >= '{self.lower_bound_inc:%Y-%m-%dT%H:%M:%S.%f}'"
            + f" AND created_at < '{self.upper_bound:%Y-%m-%dT%H:%M:%S.%f}'"
        )

    def split(self) -> tuple[Query, Query]:
        """split the query in two by splitting the time range"""
        mid = self.lower_bound_inc + (self.upper_bound - self.lower_bound_inc) / 2
        return (
            Query(self.filter_group, self.lower_bound_inc, mid),
            Query(self.filter_group, mid, self.upper_bound),
        )


def build_queries(filter_groups: list[tuple[str, int]], start: datetime) -> list[Query]:
    """Build a full list of queries for an hour."""
    queries: list[Query] = []
    interval = timedelta(days=1)

    for filter_group, count in filter_groups:
        query_count = count // TARGET_QUERY_SIZE
        query_interval = timedelta(seconds=interval.total_seconds() / query_count)
        lower_bound = start
        for _ in range(query_count):
            upper_bound = lower_bound + query_interval
            queries.append(Query(filter_group, lower_bound, upper_bound))
            lower_bound = upper_bound

        end = start + interval
        if lower_bound < end:
            queries.append(Query(filter_group, lower_bound, end))

    return queries


cache_dir = Path('.cache')
cache_dir.mkdir(exist_ok=True)


async def run_query(client: AsyncLogfireQueryClient, sql: str) -> tuple[Path, polars.DataFrame]:
    cache_path = cache_dir / f'{token_hash}_{slugify(sql)}.parquet'
    if await asyncify(cache_path.exists):
        return cache_path, await asyncify(polars.read_parquet, cache_path)
    else:
        data = await client.query_arrow(sql, limit=QUERY_LIMIT)  # type: ignore
        df: polars.DataFrame = polars.from_arrow(data)  # type: ignore
        await asyncify(df.write_parquet, cache_path)
        return cache_path, df


P = ParamSpec('P')
R = TypeVar('R')


async def asyncify(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    return await asyncio.get_event_loop().run_in_executor(None, partial(func, *args, **kwargs))


def slugify(sql: str) -> str:
    s = re.sub(r'\s+', '_', sql.lower())
    s = re.sub(r'[^a-zA-Z0-9_]+', '_', s)
    s = re.sub(r'__+', '_', s)
    return s.strip('_')


if __name__ == '__main__':
    if len(sys.argv) == 3:
        table = cast(Literal['records', 'metrics'], sys.argv[1])
        assert table in {'records', 'metrics'}, f'Invalid table: {table}, must be either "records" or "metrics"'
        d = date.fromisoformat(sys.argv[2])
        asyncio.run(main(d, table))
    else:
        print('Usage: uv run logfire_export.py [records|metrics] [date]', file=sys.stderr)
        exit(1)
