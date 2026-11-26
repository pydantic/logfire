"""Publish an immutable template to an existing public S3 bucket with the AWS CLI.

The caller chooses the account, bucket, profile, and region explicitly. The script
validates the template and verifies public bytes before it writes a release manifest.
It does not change bucket permissions or put project credentials in an object.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

TEMPLATE = Path(__file__).resolve().parents[1] / 'docs/assets/cloudformation/logfire-firehose-v1.json'


def main() -> None:
    """Validate the account, publish content-addressed bytes, and verify the public URL."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--expected-account', required=True)
    parser.add_argument('--output-manifest', type=Path, required=True)
    parser.add_argument('--output-template', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', args.bucket):
        parser.error('Invalid S3 bucket name')
    if not re.fullmatch(r'[a-z]{2}(-[a-z]+)+-\d', args.region):
        parser.error('Invalid AWS region')
    if args.region.startswith(('cn-', 'us-gov-', 'us-iso')):
        parser.error('This publisher supports AWS commercial regions only')
    aws = ['aws', '--profile', args.profile, '--region', args.region]

    def run(*command: str) -> str:
        return subprocess.check_output([*aws, *command], text=True)

    account = run('sts', 'get-caller-identity', '--query', 'Account', '--output', 'text').strip()
    if account != args.expected_account:
        parser.error(f'The profile uses account {account}, not the expected account')
    source = TEMPLATE.read_bytes()
    template = json.loads(source)
    if 'Default' in template['Parameters']['LogfireWriteToken']:
        parser.error('The public template must not contain a default write token')
    run('cloudformation', 'validate-template', '--template-body', f'file://{TEMPLATE}')
    digest = hashlib.sha256(source).hexdigest()
    key = f'firehose/v1/{digest}.json'
    url = f'https://s3.{args.region}.amazonaws.com/{args.bucket}/{key}'
    try:
        with urlopen(url, timeout=30) as response:
            existing = response.read(len(source) + 1)
    except HTTPError as error:
        error.close()
        if error.code not in {403, 404}:
            raise
        existing = None
    if existing is not None and existing != source:
        raise RuntimeError('The existing public object does not match its content hash')
    # The content hash names the object. A conditional write prevents replacement.
    if existing is None:
        run(
            's3api',
            'put-object',
            '--bucket',
            args.bucket,
            '--key',
            key,
            '--body',
            str(TEMPLATE),
            '--content-type',
            'application/json',
            '--cache-control',
            'public,max-age=31536000,immutable',
            '--if-none-match',
            '*',
        )
    with urlopen(url, timeout=30) as response:
        published = response.read(len(source) + 1)
    if published != source:
        raise RuntimeError('The public template bytes do not match the source')
    if args.output_template is not None:
        args.output_template.write_bytes(source)
    args.output_manifest.write_text(
        json.dumps({'version': 'v1', 'sha256': digest, 'templateUrl': url}, indent=2) + '\n'
    )
    print(f'Published and verified {url}')


if __name__ == '__main__':
    main()
