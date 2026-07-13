---
title: "Back up Logfire data to S3 with the OTel Collector | Logfire"
description: "Configure the OpenTelemetry Collector to fan out telemetry to both Logfire and an S3 bucket for long-term archive, plus how to read it back."
---

# Back up data in AWS S3

Unless you are under the [Growth or Enterprise plan](https://pydantic.dev/pricing),
data older than **30 days** is pruned from our backend.
If you want to keep your data stored long-term, you can configure the **Logfire** SDK to also send data to the
OpenTelemetry Collector, which will then forward the data to AWS S3.

!!! tip
    This uses the [OpenTelemetry Collector AWS S3 Exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/awss3exporter),
    see their docs for more details.

    There are many other exporters available, such as for [Azure Blob Storage](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/azureblobexporter).

## Architecture: dual-export

The pattern this page sets up is **dual-export**: every span, metric, and log is sent to *both* Logfire and S3 from the same Collector pipeline.

- **Logfire** is your live querying surface. The UI, dashboards, alerts, and the Explore page all read from Logfire's backend.
- **S3** is the cold archive. Objects sit there cheaply for as long as your bucket policy keeps them, and you reach for them only when you need to audit, replay, or analyze data older than Logfire's retention window.

You do not query S3 live. When you need archived data, you spin up a second Collector with the [`awss3receiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/awss3receiver) and replay a time range into whatever destination you want: for example, back into Logfire under a different project, into a local file, or into another OTel-compatible tool.

## Minimal Collector config

Here's how you can try this out right now. First, copy the below OpenTelemetry Collector configuration
into a file called `config.yaml` and fill in the `region` and `s3_bucket` fields.

```yaml title="config.yaml"
receivers:
  otlp:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"
exporters:
  awss3:
    s3uploader:
      region: <REPLACE-WITH-YOUR-REGION>
      s3_bucket: <REPLACE-WITH-YOUR-BUCKET-NAME>
processors:
  batch:
    timeout: 10s
    send_batch_size: 32768
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [awss3]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [awss3]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [awss3]
```

Next, run the OpenTelemetry Collector locally with the above configuration using Docker:

```shell
docker run \
    -v ./config.yaml:/etc/otelcol-contrib/config.yaml \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -p 4318:4318 \
    otel/opentelemetry-collector-contrib
```

Now send some data to the OpenTelemetry Collector using the Logfire SDK.
See the [Alternative Backends guide](../alternative-backends.md) for more details.

```python skip-run="true" skip-reason="external-connection"
import os

import logfire

# This will make the Logfire SDK send data to the OpenTelemetry Collector
os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://localhost:4318'

# Keep the default send_to_logfire=True, so it will also send data to Logfire.
logfire.configure()

logfire.info('Hello, {name}!', name='world')
```

After running the script, you should see the data in both the **Logfire** UI and your S3 bucket.
The files in S3 will have keys like `year=2025/month=06/day=25/hour=14/minute=09/traces_312302042.json`.

## Object format and partitioning

The two knobs that matter most for retrieval cost are the **marshaler** (how each object is serialized) and the **partition format** (how objects are laid out under the bucket prefix).

### Marshaler

The `awss3exporter` supports several marshalers via the `marshaler` field. The two you'll pick between in practice:

| Marshaler    | Format                  | Size               | When to use                                                   |
|--------------|-------------------------|--------------------|---------------------------------------------------------------|
| `otlp_json`  | OTLP, JSON-encoded       | Larger (~2–3x)     | First-time setups; you want to grep, jq, or eyeball the data  |
| `otlp_proto` | OTLP, Protocol Buffers   | Smallest            | Cost-sensitive long-term archive at any meaningful volume     |

`otlp_json` is the default and produces files with a `.json` suffix; `otlp_proto` produces files with a `.binpb` suffix. Pick a single marshaler per bucket prefix: mixing formats under the same prefix makes the receiver-side configuration annoying.

```yaml title="config.yaml"
exporters:
  awss3:
    marshaler: otlp_proto  # or otlp_json (default)
    s3uploader:
      region: <REPLACE-WITH-YOUR-REGION>
      s3_bucket: <REPLACE-WITH-YOUR-BUCKET-NAME>
```

!!! tip
    Start with `otlp_json` while you're verifying the pipeline end-to-end: being able to `aws s3 cp ... -` and pipe into `jq` is invaluable during setup. Switch to `otlp_proto` once everything is working and you're optimizing storage cost.

You can also turn on per-object compression independently of the marshaler with `compression: gzip` or `compression: zstd` under `s3uploader`. This stacks with the marshaler choice and is usually worth turning on for long-term archives.

### Partitioning

By default, the exporter writes keys under a time-partitioned path:

```
year=%Y/month=%m/day=%d/hour=%H/minute=%M
```

Those placeholders are [strftime](https://man7.org/linux/man-pages/man3/strftime.3.html) directives and expand to the time the object was written.

!!! warning
    **Without partitioning, every read scans the entire bucket.** The `awss3receiver` uses the partition format to construct the list of object prefixes it needs to download for a given `starttime`/`endtime`. If your write-side partition format and your read-side partition format don't match, the receiver will silently find nothing.

You can override the layout via `s3uploader.s3_partition_format`:

```yaml title="config.yaml"
exporters:
  awss3:
    s3uploader:
      region: <REPLACE-WITH-YOUR-REGION>
      s3_bucket: <REPLACE-WITH-YOUR-BUCKET-NAME>
      s3_prefix: logfire-archive  # everything lands under s3://<bucket>/logfire-archive/...
      s3_partition_format: "year=%Y/month=%m/day=%d/hour=%H"  # hour-level granularity
```

Hour-level partitioning is a reasonable default for most workloads: minute-level (the default) produces a lot of tiny objects and inflates LIST costs, while day-level forces the receiver to download more than it needs for narrow time windows.

## IAM permissions

The exporter follows the standard [AWS SDK default credential chain](https://docs.aws.amazon.com/sdkref/latest/guide/standardized-credentials.html), so the same code works whether you're authenticating via environment variables locally or an attached IAM role in production. **Do not hardcode access keys in the Collector config.**

| Environment                  | Credential mechanism                                                                                       |
|------------------------------|------------------------------------------------------------------------------------------------------------|
| Local development            | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables                                        |
| EC2                          | [EC2 instance profile](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2.html) |
| ECS / Fargate                | [IAM role for tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)      |
| EKS                          | [IRSA (IAM Roles for Service Accounts)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) or EKS Pod Identity |

If you need the Collector to assume a role at runtime (for example, to write to a bucket in another account), set `s3uploader.role_arn` and the exporter will perform the AssumeRole call for you.

### Least-privilege policy

The exporter only needs `s3:PutObject` on the bucket prefix it writes to:

```json title="iam-policy.json"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCollectorToWriteArchive",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::my-logfire-archive/logfire-archive/*"
    }
  ]
}
```

Scope the `Resource` to the prefix you configured in `s3_prefix` rather than the whole bucket: that way the same bucket can hold other archives without the Collector being able to touch them.

The retrieval-side Collector (covered below) needs separate read permissions; don't grant them to the writer.

## Encryption

S3 encrypts every object at rest. The simplest setup is to configure encryption at the **bucket** level rather than per-object: the Collector then doesn't need to know or care, and the same policy applies to anything else that ever writes to the bucket.

- **SSE-S3** (AES-256, AWS-managed keys) is on by default for all new buckets and requires no extra IAM. This is what you get for free.
- **SSE-KMS** (customer-managed KMS key) gives you per-key audit trail, key rotation policies, and the ability to revoke access by disabling the key. To use it, enable [SSE-KMS as the default bucket encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/default-bucket-encryption.html) and grant the Collector's IAM principal `kms:GenerateDataKey` on the key:

```json title="iam-policy-with-kms.json"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCollectorToWriteArchive",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::my-logfire-archive/logfire-archive/*"
    },
    {
      "Sid": "AllowCollectorToUseKmsKey",
      "Effect": "Allow",
      "Action": "kms:GenerateDataKey",
      "Resource": "arn:aws:kms:us-east-1:111122223333:key/abcd1234-..."
    }
  ]
}
```

The retrieval-side Collector additionally needs `kms:Decrypt` on the same key: again, granted to the reader principal, not the writer.

## Lifecycle policies for cost

S3 storage is cheap but not free, and OpenTelemetry data accumulates fast. Configure a [bucket lifecycle policy](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html) so old objects transition to colder storage classes and eventually expire.

A reasonable starting point: keep hot for 30 days, then move to Glacier Instant Retrieval, then expire after a year.

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket my-logfire-archive \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "logfire-archive-tiering",
        "Status": "Enabled",
        "Filter": { "Prefix": "logfire-archive/" },
        "Transitions": [
          { "Days": 30,  "StorageClass": "GLACIER_IR" },
          { "Days": 180, "StorageClass": "DEEP_ARCHIVE" }
        ],
        "Expiration": { "Days": 365 }
      }
    ]
  }'
```

!!! note
    Tiered storage classes have **minimum storage durations** and **retrieval costs**. Glacier Instant Retrieval has a 90-day minimum; Glacier Deep Archive has a 180-day minimum and retrieval can take hours. Pick transition ages that match how often you actually expect to read the data, not the cheapest possible per-GB rate.

## Retrieving archived data

When you need to look at archived data, run a second Collector with the [`awss3receiver`](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/awss3receiver) and point it at a time range. The receiver downloads matching objects, decodes them, and pushes them through whatever pipeline you configure: exactly like a live receiver, but bounded by `starttime`/`endtime`.

Here's a minimal config that replays a one-hour window into a local file, which you can then open in any OTel-compatible tool:

```yaml title="retrieve.yaml"
receivers:
  awss3:
    starttime: "2026-05-01 14:00"
    endtime: "2026-05-01 15:00"
    s3downloader:
      region: <REPLACE-WITH-YOUR-REGION>
      s3_bucket: <REPLACE-WITH-YOUR-BUCKET-NAME>
      s3_prefix: logfire-archive
      s3_partition_format: "year=%Y/month=%m/day=%d/hour=%H"
exporters:
  file:
    path: ./replay.json
service:
  pipelines:
    traces:
      receivers: [awss3]
      exporters: [file]
    metrics:
      receivers: [awss3]
      exporters: [file]
    logs:
      receivers: [awss3]
      exporters: [file]
```

Times accept RFC3339, `YYYY-MM-DD HH:MM`, or `YYYY-MM-DD` (interpreted as `00:00`).

A few things to keep in mind:

- **`s3_partition_format` and `s3_prefix` must match the writer.** If you changed them on the exporter side, change them here too: otherwise the receiver constructs the wrong key list and finds nothing.
- **The marshaler must match the writer.** If you wrote `otlp_proto`, configure the receiver to decode `.binpb`; if you wrote `otlp_json`, the default works.
- **Retrieval is for cold-data analysis, not live querying.** A receiver run processes one bounded time range and then stops. For live data, query Logfire.
- **You can replay back into Logfire.** Swap the `file` exporter for an `otlphttp` exporter pointing at Logfire to re-ingest archived data into a project: useful for forensic investigations on data that's already aged out of your live project's retention window.

## Using S3-compatible storage

The `awss3exporter` talks to any S3-compatible API (including [MinIO](https://min.io/), Cloudflare R2, and similar) via three knobs on `s3uploader`:

- `endpoint`: the API endpoint URL (overrides the AWS-region-derived default).
- `s3_force_path_style: true`: use `endpoint/bucket/key` addressing instead of virtual-hosted-style `bucket.endpoint/key`. Most non-AWS S3 implementations require this.
- `disable_ssl: true`: only for local development against an unencrypted endpoint. **Don't set this in production.**

```yaml title="config.yaml"
exporters:
  awss3:
    s3uploader:
      region: us-east-1                # ignored by MinIO but required by the SDK
      s3_bucket: my-bucket
      endpoint: http://minio:9000
      s3_force_path_style: true
      disable_ssl: true
```

Credentials still come from the standard AWS SDK chain: for MinIO, set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to the MinIO access key and secret.

## Reading the data with other tools

Logfire doesn't support importing this data, but you can use other OpenTelemetry-compatible tools. For example,
run this command to start a [Jaeger](https://www.jaegertracing.io/) container:

```
docker run --rm \
  -p 16686:16686 \
  -p 4318:4318 \
  jaegertracing/all-in-one:latest
```

then open [http://localhost:16686/](http://localhost:16686/) and click on 'Upload'.

Alternatively, install [`otel-tui`](https://github.com/ymtdzzz/otel-tui) and run `otel-tui --from-json-file <path-to-file>` to view the data in your terminal.

However, these simple options don't work well for searching through many files. For that, use the `awss3receiver` pattern from the [Retrieving archived data](#retrieving-archived-data) section, or the [OTLP JSON File Receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/otlpjsonfilereceiver) to read from locally downloaded files.
