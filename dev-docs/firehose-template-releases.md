# Firehose template releases

`logfire-firehose-v1.json` is the source template for CloudWatch logs and metrics.
Keep deployment endpoints and project credentials out of this file.
The console launch fetches the template over HTTPS from Amazon S3.
CloudFormation does not accept a generic HTTPS server or Google Cloud Storage URL.
See the [supported quick-create URL formats](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-console-create-stacks-quick-create-links.html).
Downloadable copies can use another host.

Publish to an existing public template bucket with the AWS CLI:

```bash
make publish-firehose-template FIREHOSE_PUBLISH_ARGS='--profile PROFILE --expected-account ACCOUNT_ID --region REGION --bucket BUCKET --output-manifest /path/to/release.json --output-template /path/to/bundled-template.json'
```

The script validates the account and template before upload.
It writes an object under `firehose/v1/<sha256>.json` without replacing existing objects.
It verifies the public object bytes before it writes the manifest and optional bundle.
The consumer must check the bundled bytes against the manifest fingerprint.
Update the source, public object, manifest, and consumer bundle as one release.
Use a new version when parameter or output compatibility changes.

The bucket must serve only public templates.
Keep public access blocked on the customer backup bucket that the template creates.
Do not put credentials or customer telemetry in the template publication bucket.
