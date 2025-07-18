We support linking to the source code on GitHub, GitLab, and any other VCS provider that uses the same URL format.

![Link to GitHub](../images/guide/link-to-github.gif)

## Usage

Here's an example:

```python
import logfire

logfire.configure(
    code_source=logfire.CodeSource(
        repository='https://github.com/pydantic/logfire',  #(1)!
        revision='<hash of commit used on release>',  #(2)!
        root_path='path/within/repo',  #(3)!
    )
)
```

1. The URL of the repository e.g. `https://github.com/pydantic/logfire`.
2. The specific branch, tag, or commit hash to link to e.g. `main`.
3. The path from the root of the repository to the current working directory of the process. If your code is in a
   subdirectory of your repo, you can specify it here. Otherwise you can probably omit this.

You can learn more in our [`logfire.CodeSource`][logfire.CodeSource] API reference.

## Alternative Configuration

For other OpenTelemetry SDKs, you can configure these settings using resource attributes, e.g. by setting the
[`OTEL_RESOURCE_ATTRIBUTES`][otel-resource-attributes] environment variable:

```
OTEL_RESOURCE_ATTRIBUTES=vcs.repository.url.full=https://github.com/pydantic/platform
OTEL_RESOURCE_ATTRIBUTES=${OTEL_RESOURCE_ATTRIBUTES},vcs.repository.ref.revision=main
OTEL_RESOURCE_ATTRIBUTES=${OTEL_RESOURCE_ATTRIBUTES},vcs.root.path=path/within/repo
```

[otel-resource-attributes]: https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/#general-sdk-configuration
