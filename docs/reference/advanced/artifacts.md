# Artifacts

Artifacts let you attach a **binary blob** — an image, audio clip, PDF, or a large JSON
payload — to a span. The blob is stored separately from your telemetry, so it is not
subject to span attribute size limits and does not bloat your traces. The span itself
carries only a small reference; Logfire uploads the blob out of band.

## Logging an artifact

Wrap your data in `logfire.Artifact` and pass it as a span or log attribute:

```python skip="true"
import logfire

logfire.configure()

with open('chart.png', 'rb') as f:
    image_bytes = f.read()

logfire.info('chart generated', chart=logfire.Artifact(image_bytes, content_type='image/png'))
```

The `chart` argument renders as an image preview on the trace in the Logfire UI, with a
download link — not as a wall of base64.

### From a file or a file handle

`Artifact.from_file` reads a path lazily (no need to load the bytes yourself), and
`Artifact.from_file_handle` accepts any open binary handle, including temporary files:

```python skip="true"
import logfire

logfire.configure()

# From a path — the content type is guessed from the extension.
logfire.info('report ready', report=logfire.Artifact.from_file('report.pdf'))

# From an open binary handle.
with open('clip.mp3', 'rb') as handle:
    logfire.info('audio processed', clip=logfire.Artifact.from_file_handle(handle))
```

## When the upload happens

Each artifact chooses when its bytes are uploaded, via the `upload` argument:

- **`background`** (the default) — the upload is handed to a background thread and the
  logging call never blocks. If uploads cannot keep up, queued artifacts are dropped
  with a warning rather than stalling your program.
- **`sync`** — the upload runs inline; the logging call returns only once the blob is
  stored. Use this when you need delivery guaranteed, or when you want to free the
  source bytes/file immediately afterwards.

```python skip="true"
import logfire

logfire.configure()

# Block until this artifact is uploaded.
logfire.info('critical input', data=logfire.Artifact(payload, upload='sync'))
```

## How it works

Artifacts are **content-addressed**: an artifact's identity is the sha256 of its bytes.
The same blob logged repeatedly — within a project — is uploaded and stored only once.
The reference embedded in the span looks like:

```json
{
  "type": "logfire.artifact",
  "sha256": "9f86d0818...",
  "filename": "chart.png",
  "content_type": "image/png",
  "size_bytes": 28421
}
```

The blob never travels through the telemetry pipeline. On SaaS the SDK uploads it
directly to object storage via a signed URL; self-hosted deployments route it through
the Logfire backend.

## Viewing artifacts

Open a span in the Logfire UI: any artifact-valued argument renders inline — images,
audio, video, and PDFs as previews, everything else as a download link — alongside its
filename, content type, and size.
