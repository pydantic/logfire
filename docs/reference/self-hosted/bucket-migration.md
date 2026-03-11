---
title: "Logfire Self-Hosted: Object Storage Bucket Migration Guide"
description: "How to migrate your Pydantic Logfire self-hosted deployment to a new S3-compatible object storage bucket without data loss."
---
# Object Storage Bucket Migration

This guide walks you through migrating your **Logfire** self-hosted deployment from one object storage bucket to another. This applies whether you're moving between providers (e.g., Amazon S3 to Google Cloud Storage), between regions, or simply to a different bucket within the same provider.

!!! note
    **This process does not involve data loss.** The ingest system buffers incoming data on local disk and will flush it to the new object store once the migration is completed and writer workloads are scaled back up.

---

## Overview

The migration consists of three steps:

1. **Replicate & sync** data from the source bucket to the destination bucket.
2. **Scale down** writer workloads to stop writes to the source bucket.
3. **Deploy** the Helm chart with updated object storage configuration and scale writer workloads back up.

## Prerequisites

- Admin access to your **Kubernetes** cluster.
- The [Helm](https://helm.sh) CLI installed.
- Read access to the source bucket and write access to the destination bucket.
- Familiarity with your current `values.yaml` object storage configuration.

---

## Step 1: Replicate & Sync Bucket Data

Before switching **Logfire** to the new bucket, you need to copy all existing data from the source bucket to the destination. The exact tool depends on your cloud provider or storage solution.

### Google Cloud Storage

Use [Storage Transfer Service](https://cloud.google.com/storage-transfer-service) for managed transfers, or `gsutil`/`gcloud storage` for a manual copy:

```bash
gcloud storage rsync gs://source-bucket gs://destination-bucket --recursive
```

### Amazon S3

Use [S3 Cross-Region Replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html) for ongoing replication, or the AWS CLI for a one-time sync:

```bash
aws s3 sync s3://source-bucket s3://destination-bucket
```

### S3-Compatible / Other Providers

For MinIO, Ceph, or other S3-compatible storage, you can use [rclone](https://rclone.org/) or `rsync`-style tools:

```bash
rclone sync source:source-bucket destination:destination-bucket
```

!!! warning
    Ensure the sync is fully completed before proceeding to Step 2. Depending on the volume of data, this may take a significant amount of time. You can monitor progress with your provider's tooling or by comparing object counts between the two buckets.

---

## Step 2: Scale Down Writer Workloads

Once the bucket data is fully synced, scale the writer workloads to zero. This prevents any further writes to the source bucket while you update the configuration.

```bash
kubectl scale deployment logfire-ff-maintenance-worker --replicas=0
kubectl scale deployment logfire-ff-compaction-worker --replicas=0
kubectl scale deployment logfire-ff-ingest-processor --replicas=0
```

Verify that all writer pods have terminated:

```bash
kubectl get pods -l 'app.kubernetes.io/component in (logfire-ff-maintenance-worker,logfire-ff-compaction-worker,logfire-ff-ingest-processor)'
```

You should see no running pods for these workloads.

!!! note
    Incoming data will continue to be received by `logfire-ff-ingest` and buffered to local disk. No data will be lost during this window.

### Final Sync

After the writers are stopped, run a final incremental sync to capture any data written between the initial sync and the scale-down:

```bash
# Example using AWS CLI
aws s3 sync s3://source-bucket s3://destination-bucket
```

Use the equivalent command for your provider as shown in Step 1.

---

## Step 3: Deploy Updated Configuration & Scale Up

Update your `values.yaml` with the new object storage configuration. Refer to the [Object Storage section of the installation guide](installation.md#object-storage) for full details on configuring credentials for each provider.

For example, if migrating to a new S3 bucket:

```yaml
objectStore:
  uri: s3://new-destination-bucket
  env:
    AWS_DEFAULT_REGION: "<new-region>"
    AWS_ACCESS_KEY_ID:
      valueFrom:
        secretKeyRef:
          name: my-aws-secret
          key: access-key
    AWS_SECRET_ACCESS_KEY:
      valueFrom:
        secretKeyRef:
          name: my-aws-secret
          key: secret-key
```

Or, if migrating to Google Cloud Storage:

```yaml
objectStore:
  uri: gs://new-destination-bucket
```

Deploy the updated Helm chart:

```bash
helm upgrade logfire pydantic/logfire -f values.yaml
```

Once the deployment is complete, scale the writer workloads back up:

```bash
kubectl scale deployment logfire-ff-maintenance-worker --replicas=1
kubectl scale deployment logfire-ff-compaction-worker --replicas=1
kubectl scale deployment logfire-ff-ingest-processor --replicas=1
```

!!! note
    Adjust `--replicas` to match your previous replica count if you were running more than one replica per workload. You can check your Helm values or previous deployment configuration for the correct counts.

---

## Verification

After scaling the workloads back up, verify that the system is healthy:

1. **Check pod status** — all pods should be running without restarts:

    ```bash
    kubectl get pods
    ```

2. **Check logs** for writer workloads to ensure they are writing to the new bucket:

    ```bash
    kubectl logs -l app.kubernetes.io/component=logfire-ff-ingest-processor --tail=50
    ```

3. **Send test data** to confirm end-to-end ingestion is working:

    ```python
    import logfire

    logfire.configure(
        advanced=logfire.AdvancedOptions(base_url='https://<your_logfire_hostname>'),
        token='<YOUR_LOGFIRE_WRITE_TOKEN>',
    )
    logfire.info('Bucket migration verification')
    ```

4. **Query recent data** in the Logfire UI to confirm both historical and new data are accessible.
