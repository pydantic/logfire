# Scaling Self Hosted

**Logfire** is designed to be horizontally scalable, and can handle a lot of traffic. Depending on your usage patterns, however, you may be required to scale certain pods in order to maintain performance.

Please use the [architecture](./overview.md#service-architecture) diagram as reference.

## PostgreSQL Configuration

PostgreSQL is not managed by the logfire helm chart.  It is assumed that an existing cluster is available in your environment.  If not, a good solution to deploying PostgreSQL in Kubernetes is [CloudNativePG](https://cloudnative-pg.io/).

> **Note:** No telemetry data is stored within PostgreSQL.  We use PostgreSQL to manage organisations, projects, dashboards etc. and for tracking/compacting files within object storage.

A recommended starting size would be 4 vCPUs and 16gb RAM.

Here are some parameters you can use to start tuning:

| Parameter | Value |
|-----------|-------|
| autovacuum_analyze_scale_factor | 0.05 |
| autovacuum_analyze_threshold | 50 |
| autovacuum_max_workers | 6 |
| autovacuum_naptime | 30 |
| autovacuum_vacuum_cost_delay | 1 |
| autovacuum_vacuum_cost_limit | 2000 |
| autovacuum_vacuum_scale_factor | 0.1 |
| autovacuum_vacuum_threshold | 50 |
| idle_in_transaction_session_timeout | 60000 |
| log_autovacuum_min_duration | 600000 |
| log_lock_waits | on |
| log_min_duration_statement | 1000 |
| maintenance_work_mem | 4000000 |
| max_connections | 2048 |
| max_wal_size | 16000000 |
| max_slot_wal_keep_size | 8000000 |
| random_page_cost | 1.1 |
| work_mem | 128000 |

## Scaling Configuration

Each service can have standard kubernetes replicas, resource limits and autoscaling configured:

```yaml
<service_name>:
  # -- Number of pod replicas
  replicas: 1
  # -- Resource limits and allocations
  resources:
    cpu: "1"
    memory: "1Gi"
  # -- Autoscaler settings
  autoscaling:
    minReplicas: 2
    maxReplicas: 4
    memAverage: 65
    cpuAverage: 20
  # -- POD Disruption Budget
  pdb:
    maxUnavailable: 1
    minAvaliable: 1
```

## Recommended Starting Values

By default, the helm chart only includes a single replica for all pods, and no configured resource limits.  When bringing self hosted to production, you will need to adjust the scaling of each service.  This is depenent on the usage patterns of your instance.

I.e, if a lot of querying is going on, or there are a high number of dashboards, then you may need to scale up the query api and cache.  Conversely, if you are write heavy, but don't query as much, you may need to scale up ingest.  You can use the CPU and memory resources to gauge how busy certain aspects of Logfire are.

In the event that the system is not performing well, and there is no obvious CPU/Memory spikes, then please have a look at accessing the meta project in the [troubleshooting](./troubleshooting.md) section to understand internally what's going on.

Here are some recommended values to get you started:

```yaml
logfire-backend:
  replicas: 2
  resources:
    cpu: "2"
    memory: "2Gi"
  autoscaling:
    minReplicas: 2
    maxReplicas: 4
    memAverage: 65
    cpuAverage: 20

logfire-ff-query-api:
  replicas: 2
  resources:
    cpu: "2"
    memory: "2Gi"
  autoscaling:
    minReplicas: 2
    maxReplicas: 8
    memAverage: 65
    cpuAverage: 20

logfire-ff-cache:
  replicas: 2
  cacheStorage: "256Gi"
  resources:
    cpu: "4"
    memory: "8Gi"

logfire-ff-conhash-cache:
  replicas: 2
  resources:
    cpu: "1"
    memory: "1Gi"

logfire-ff-ingest:
  volumeClaimTemplates:
    storageClassName: my-storage-class
    storage: "16Gi"
  resources:
    cpu: "2"
    memory: "4Gi"
  autoscaling:
    minReplicas: 6
    maxReplicas: 24
    memAverage: 25
    cpuAverage: 15

logfire-ff-compaction-worker:
  replicas: 2
  resources:
    cpu: "4"
    memory: "8Gi"
  autoscaling:
    minReplicas: 2
    maxReplicas: 4
    memAverage: 50
    cpuAverage: 50

logfire-ff-maintenance-worker:
  replicas: 2
  resources:
    cpu: "4"
    memory: "8Gi"
  autoscaling:
    minReplicas: 2
    maxReplicas: 4
    memAverage: 50
    cpuAverage: 50
```
