import fnmatch
import hashlib
import io
import json
import re
import subprocess
import sys
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

from scripts import publish_firehose_template as publisher

Release = tuple[Callable[..., None], Path, Path, Path, list[list[str]], list[bytes | HTTPError], list[str]]


@pytest.fixture
def release(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Release:
    source = tmp_path / 'source.json'
    source.write_text('{"Parameters":{"LogfireWriteToken":{"NoEcho":true}}}')
    manifest = tmp_path / 'release.json'
    bundle = tmp_path / 'bundle.json'
    commands: list[list[str]] = []
    responses: list[bytes | HTTPError] = [source.read_bytes(), source.read_bytes()]
    requests: list[str] = []
    account = '123456789012'

    def aws(command: list[str], *, text: bool) -> str:
        commands.append(command)
        return account if 'sts' in command else '{}'

    def fetch(url: str, *, timeout: int) -> io.BytesIO:
        requests.append(url)
        value = responses.pop(0)
        if isinstance(value, HTTPError):
            raise value
        return io.BytesIO(value)

    def run(*extra: str) -> None:
        monkeypatch.setattr(
            sys,
            'argv',
            [
                'publish',
                '--bucket',
                'example-templates',
                '--region',
                'us-east-1',
                '--profile',
                'test-profile',
                '--expected-account',
                account,
                '--output-manifest',
                str(manifest),
                '--output-template',
                str(bundle),
                *extra,
            ],
        )
        publisher.main()

    monkeypatch.setattr(publisher, 'TEMPLATE', source)
    monkeypatch.setattr(publisher.subprocess, 'check_output', aws)
    monkeypatch.setattr(publisher, 'urlopen', fetch)
    return run, source, manifest, bundle, commands, responses, requests


def test_existing_release_preserves_verified_bytes(release: Release) -> None:
    run, source, manifest, bundle, commands, _, requests = release
    run()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    url = f'https://s3.us-east-1.amazonaws.com/example-templates/firehose/v1/{digest}.json'
    assert json.loads(manifest.read_text()) == {'version': 'v1', 'sha256': digest, 'templateUrl': url}
    assert bundle.read_bytes() == source.read_bytes()
    assert requests == [url, url]
    assert not any('put-object' in command for command in commands)


@pytest.mark.parametrize('status', [403, 404])
def test_new_release_requires_conditional_upload(release: Release, status: int) -> None:
    run, source, manifest, _, commands, responses, _ = release
    responses[0] = HTTPError('https://example.test', status, 'missing', Message(), None)
    run()
    uploads = [command for command in commands if 'put-object' in command]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload[upload.index('--if-none-match') + 1] == '*'
    assert upload[upload.index('--key') + 1] == f'firehose/v1/{hashlib.sha256(source.read_bytes()).hexdigest()}.json'
    assert manifest.exists()


def test_wrong_account_does_not_publish(release: Release) -> None:
    run, _, manifest, bundle, commands, _, requests = release
    with pytest.raises(SystemExit):
        run('--expected-account', '999999999999')
    assert len(commands) == 1
    assert requests == []
    assert not manifest.exists() and not bundle.exists()


def test_public_template_cannot_default_a_credential(release: Release) -> None:
    run, source, manifest, _, commands, _, requests = release
    source.write_text('{"Parameters":{"LogfireWriteToken":{"Default":"synthetic-test-value"}}}')
    with pytest.raises(SystemExit):
        run()
    assert len(commands) == 1
    assert requests == []
    assert not manifest.exists()


@pytest.mark.parametrize('index', [0, 1])
def test_wrong_public_bytes_do_not_write_release_outputs(release: Release, index: int) -> None:
    run, _, manifest, bundle, commands, responses, _ = release
    responses[index] = b'not the template'
    with pytest.raises(RuntimeError, match='(content hash|source)'):
        run()
    assert not manifest.exists() and not bundle.exists()
    assert not any('put-object' in command for command in commands)


def test_public_http_failure_does_not_trigger_upload(release: Release) -> None:
    run, _, manifest, _, commands, responses, _ = release
    responses[0] = HTTPError('https://example.test', 503, 'unavailable', Message(), None)
    with pytest.raises(HTTPError):
        run()
    assert not manifest.exists()
    assert not any('put-object' in command for command in commands)


def test_conditional_write_failure_does_not_create_release(release: Release, monkeypatch: pytest.MonkeyPatch) -> None:
    run, _, manifest, bundle, _, responses, _ = release
    responses[0] = HTTPError('https://example.test', 404, 'missing', Message(), None)

    def aws(command: list[str], *, text: bool) -> str:
        if 'put-object' in command:
            raise subprocess.CalledProcessError(1, command, stderr='PreconditionFailed')
        return '123456789012' if 'sts' in command else '{}'

    monkeypatch.setattr(publisher.subprocess, 'check_output', aws)
    with pytest.raises(subprocess.CalledProcessError):
        run()
    assert not manifest.exists() and not bundle.exists()


@pytest.mark.parametrize('region', ['cn-north-1', 'us-gov-west-1', 'us-iso-east-1'])
def test_unsupported_partition_stops_before_aws_calls(release: Release, region: str) -> None:
    run, _, manifest, _, commands, _, requests = release
    with pytest.raises(SystemExit):
        run('--region', region)
    assert commands == [] and requests == []
    assert not manifest.exists()


def test_template_endpoint_and_failure_backup_permissions() -> None:
    template = json.loads(
        (Path(__file__).parents[1] / 'docs/assets/cloudformation/logfire-firehose-v1.json').read_text()
    )
    pattern = template['Parameters']['LogfireEndpoint']['AllowedPattern']
    assert re.fullmatch(pattern, 'https://telemetry.example.test')
    for invalid in ['https://host/path', 'https://host?x=1', 'https://host#fragment', 'https://user@host']:
        assert re.fullmatch(pattern, invalid) is None
    statements = template['Resources']['FirehoseRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
    objects = next(statement for statement in statements if 's3:PutObject' in statement['Action'])
    assert 's3:AbortMultipartUpload' in objects['Action']
    assert objects['Resource'] == {'Fn::Sub': '${BackupBucket.Arn}/*'}
    # CloudFormation's LogGroup.Arn includes :*, which covers its log-stream ARNs.
    logs = next(statement for statement in statements if statement['Action'] == 'logs:PutLogEvents')
    assert logs['Resource'] == {'Fn::GetAtt': ['DeliveryLogGroup', 'Arn']}
    assert fnmatch.fnmatchcase(
        'arn:aws:logs:us-east-1:123456789012:log-group:delivery:log-stream:errors',
        'arn:aws:logs:us-east-1:123456789012:log-group:delivery:*',
    )
