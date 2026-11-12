---
title: "Logfire Self-Hosted: FusionFire Database Migration Guide"
description: "How to move the FusionFire (ff) PostgreSQL database of a self-hosted Pydantic Logfire deployment to a new PostgreSQL instance."
---
# FusionFire Database Migration

This guide moves the `ff` PostgreSQL database of a self-hosted **Logfire** deployment to a new PostgreSQL instance. The object storage bucket stays where it is.

!!! warning
    The `ff` database records which objects in the bucket hold live data. When Logfire starts on the new instance, the new database must be an exact copy of the old database. A copy that is older than the bucket is not supported, and Logfire cannot repair it:

    * Compaction deletes the files it replaces about 5 minutes after it writes the new files. An older copy still points at the deleted files, and queries over those files fail.
    * An older copy has no record of the files written after the copy was made. Queries do not return that data, and retention never deletes it.

    For the same reason, do not point Logfire back at the old database after the FusionFire workloads have run against the new one.

---

## Overview

The migration consists of three steps:

1. **Stop** the FusionFire workloads that use the `ff` database.
2. **Copy** the database to the new instance, with one of these methods:
    * **Dump and restore.** This method is the simplest. Queries are unavailable for as long as the dump and restore take.
    * **Promote a replica.** Queries are unavailable for a few minutes. This method needs a physical replica of the old instance, for example a read replica from your PostgreSQL provider.
3. **Deploy** the Helm chart with the new `postgresFFDsn` and start the workloads again.

`logfire-ff-ingest` keeps running through all steps. It does not connect to PostgreSQL. It accepts telemetry and buffers it on disk until the other workloads start again. By default, it keeps retrying a batch for only 10 minutes, so Step 1 raises that limit for the length of the migration.

## Prerequisites

- Admin access to your **Kubernetes** cluster.
- The [Helm](https://helm.sh) CLI installed.
- `pg_dump`, `pg_restore`, and `psql` with the same major version as the new instance.
- A new PostgreSQL instance that meets the [PostgreSQL requirements](installation.md#postgresql). For dump and restore, it must run the same or a newer PostgreSQL major version than the old instance. A physical replica must run the same major version.
- An empty `ff` database on the new instance, owned by the user in the new `postgresFFDsn`. That user must be able to create the `intarray` and `btree_gist` extensions.
- Enough disk on the `logfire-ff-ingest` volumes to buffer incoming data for the length of the migration.
- An estimate of how long the migration takes. Use a value that is longer than that estimate for `FF_INGEST_REMOTE_RETRY_MAX_DURATION` in Step 1.

Use the same chart version and the same values before and after the migration, except for `postgresFFDsn`. Do not upgrade the chart in the same window. Record the installed chart version, and pass it to every `helm upgrade` in this guide:

```bash
CHART_VERSION=$(helm list -n logfire -f '^logfire$' -o json | jq -r '.[0].chart | sub("^logfire-"; "")')
```

The examples below assume the Helm release is named `logfire` and installed in the `logfire` namespace. Adjust the commands if your deployment uses different names.

---

## Step 1: Stop the FusionFire Workloads

Pause the autoscalers of these workloads first. Every `sizingPreset` turns on HPA for them, and your values can also turn on HPA or KEDA. Otherwise, Kubernetes scales the workloads back up during the migration.

Also raise how long `logfire-ff-ingest` retries a batch. After `FF_INGEST_REMOTE_RETRY_MAX_DURATION` (10 minutes by default), ingest writes the batch to the `_ingest_failover` prefix of the bucket, and queries do not return that data. If your values already set `logfire-ff-ingest.env`, copy the other entries into this file too, because Helm replaces the whole list. Leave out any existing `FF_INGEST_REMOTE_RETRY_MAX_DURATION` entry.

Create a temporary `migration-pause-ff.yaml` file:

```yaml
logfire-ff-ingest:
  env:
    - name: FF_INGEST_REMOTE_RETRY_MAX_DURATION
      value: "6h"

logfire-ff-ingest-processor:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false

logfire-ff-compaction-worker:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false

logfire-ff-maintenance-worker:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false

logfire-ff-maintenance-scheduler:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false

logfire-ff-crud-api:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false

logfire-ff-query-api:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false

logfire-ff-query-worker:
  autoscaling:
    hpa:
      enabled: false
    keda:
      enabled: false
```

Apply it with your current production values:

```bash
helm upgrade logfire pydantic/logfire \
  --version "$CHART_VERSION" \
  -f values.yaml \
  -f migration-pause-ff.yaml \
  --namespace logfire
```

Wait until every `logfire-ff-ingest` pod runs with the new retry limit. A pod that still has the 10-minute limit loses data once the workloads stop:

```bash
kubectl -n logfire rollout status statefulset/logfire-ff-ingest
```

Then scale the workloads down:

```bash
kubectl -n logfire scale deployment --replicas=0 \
  -l 'app.kubernetes.io/component in (logfire-ff-ingest-processor,logfire-ff-compaction-worker,logfire-ff-maintenance-worker,logfire-ff-maintenance-scheduler,logfire-ff-crud-api,logfire-ff-query-api,logfire-ff-query-worker)'
```

Make sure that no client is still connected to the old `ff` database:

```sql
SELECT application_name, usename, client_addr, state
FROM pg_stat_activity
WHERE datname = 'ff' AND pid <> pg_backend_pid();
```

The query must return no rows before you continue. If it returns rows, find and stop the clients that it shows.

!!! note
    Queries in the Logfire UI and the API fail until Step 3 is complete. `logfire-ff-ingest` buffers incoming data on disk for as long as `FF_INGEST_REMOTE_RETRY_MAX_DURATION` allows. Finish Step 3 before that time ends, and monitor the ingest disk usage. If the ingest disk fills, ingest writes new data to the `_ingest_failover` prefix, and queries do not return that data. If the ingest autoscaler removes a pod during the window, that pod's buffered data stays on its volume until the pod starts again.

---

## Step 2: Copy the Database

Use one of the two methods below.

### Option A: Dump and Restore

Dump the old database. The directory format lets `pg_dump` and `pg_restore` use parallel jobs:

```bash
pg_dump \
  --dbname="$OLD_FF_DSN" \
  --format=directory \
  --jobs=4 \
  --no-owner \
  --no-privileges \
  --file=ff-dump
```

Restore it into the empty `ff` database on the new instance. Connect as the user in the new `postgresFFDsn`, so that this user owns the restored tables:

```bash
pg_restore \
  --dbname="$NEW_FF_DSN" \
  --jobs=4 \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  ff-dump
```

The restore does not copy planner statistics. Collect them before Logfire uses the new database:

```bash
psql "$NEW_FF_DSN" -c 'ANALYZE;'
```

### Option B: Promote a Replica

Create a physical replica of the old instance before Step 1, while Logfire is still running. Most managed PostgreSQL services call this a read replica. A physical replica copies every change, including the schema migration history, so the promoted instance is an exact copy.

This guide does not cover logical replication. Logical replication does not copy sequence values or schema changes.

After Step 1 is complete:

1. Wait until the replica has replayed every change from the old instance. Your provider shows this as a replication lag of zero. On a self-managed replica, run `SELECT pg_current_wal_lsn();` on the old instance after Step 1. Then wait until `SELECT pg_wal_lsn_diff(pg_last_wal_replay_lsn(), '<LSN>') >= 0;` returns `true` on the replica.
2. Promote the replica to a standalone instance, with your provider's promote action or with `pg_promote()`.
3. Make sure that the user in the new `postgresFFDsn` can sign in to the promoted instance and owns the `ff` database.

---

## Step 3: Deploy Updated Configuration and Scale Up

Update `postgresFFDsn` in your values, or the `postgresFFDsn` key of the Secret that `postgresSecret.name` references:

```yaml
postgresFFDsn: postgresql://logfire_ff:PASSWORD@new-postgres.example.com:5432/ff
```

Deploy the updated Helm chart without `migration-pause-ff.yaml`, so Helm restores the autoscaling, replica, and ingest retry settings from your production values:

```bash
helm upgrade logfire pydantic/logfire \
  --version "$CHART_VERSION" \
  -f values.yaml \
  --namespace logfire
```

The FusionFire migration job runs against the new database first. The chart version did not change, so the job has no migration to apply.

The chart restarts every pod that receives `postgresFFDsn`. That includes `logfire-ff-ingest`, which receives the value but does not use it. Its buffer is on a persistent volume, so the restart does not lose buffered data. If an external tool manages the Secret and the pods did not restart, restart the FusionFire deployments and the `logfire-ff-ingest` StatefulSet with `kubectl rollout restart`.

If the Helm upgrade does not restore the workloads, scale them back up manually to your previous replica counts.

---

## Verification

1. **Check pod status.** All pods must be running without restarts:

    ```bash
    kubectl -n logfire get pods
    ```

2. **Check the database connections.** Run the `pg_stat_activity` query from Step 1 against both instances. The new instance shows FusionFire connections. The old instance shows none.

3. **Check the writer logs** for database errors:

    ```bash
    kubectl -n logfire logs -l app.kubernetes.io/component=logfire-ff-ingest-processor --tail=50
    ```

4. **Query data in the Logfire UI.** Query recent data, data from before the migration, and data sent during the migration window.

Keep the old database until you have finished the checks. Do not point Logfire at it again.
