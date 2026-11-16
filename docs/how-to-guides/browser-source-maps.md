---
title: "Pydantic Logfire: Browser Source Maps"
description: "Upload source maps from CI so Logfire shows browser exceptions with your original file, function and line instead of minified code."
---

# Browser source maps

!!! warning "Experimental"
    Browser source maps are experimental. The behavior on this page can change before the feature reaches Beta.

Production JavaScript is usually *minified*: the bundler (the build tool that combines your code into a few files, such as Vite, webpack or Turbopack) renames functions and puts the code on a few long lines. A stack trace from a minified bundle points at `index-a1b2.js:1:48213`, which tells you little.

A *source map* is a JSON file that the bundler writes next to each bundle. It maps every position in the minified file back to the original file, line and function. When you upload your source maps to Logfire, Logfire shows browser exceptions with your original code.

## How it works

Logfire matches a stack frame to its source map by *debug ID*. A debug ID is a unique ID (a UUID) for one built file. The build writes the same ID into the bundle and into its source map.

```
build (CI)                         browser                         Logfire
──────────                         ───────                         ───────
bundle + map share a debug ID ───► bundle registers its debug ID
logfire sourcemap upload ─────────────────────────────────────────► stores the map
                                   exception: the SDK adds the
                                   debug IDs of the frames ───────► resolves the frames at ingest
```

1. A snippet at the top of each bundle registers the bundle's debug ID in `globalThis._debugIds` when the bundle loads. This registry is a shared convention that Turbopack and other tools also write.
2. When the Logfire browser SDK records an exception, it looks up the files in the stack trace in that registry. It adds the matches to the exception span as the `logfire.debug_ids` attribute: a JSON map from file URL to debug ID. The SDK removes the query string, the fragment and any credentials from each URL.
3. When the span reaches Logfire, Logfire finds the uploaded source map for each debug ID and rewrites the stack trace to the original source. This happens once, at ingest (when Logfire receives and stores the data). The stored record holds the resolved stack trace.

Logfire keeps the stack trace as the browser sent it in `logfire.source_map.original_stacktrace`.

## Give your bundles debug IDs

### Next.js

Turbopack writes debug IDs itself. Turn them on in `next.config.js`:

```js title="next.config.js"
module.exports = {
  productionBrowserSourceMaps: true,
  turbopack: {
    debugIds: true,
  },
}
```

`productionBrowserSourceMaps` makes `next build` write source maps for browser code. `debugIds` makes Turbopack add the debug ID to each chunk and its map. You do not need `logfire sourcemap inject` for these chunks.

!!! note "Edge runtime and middleware"
    Turbopack does not add debug IDs to code for the Next.js edge runtime or to middleware. Exceptions from that code stay minified. Run `logfire sourcemap inject` on those chunks if you need them resolved.

### Other bundlers

For Vite, webpack, esbuild, Rollup and other bundlers, build with source maps on, then run `logfire sourcemap inject` on the build output directory:

```bash
logfire --beta sourcemap inject dist
```

The command processes every `.js`, `.mjs` and `.cjs` file that has a source map. For each file, it:

- derives a debug ID from the file's bytes, so a rebuild of the same code gets the same ID. It keeps a `//# debugId=` comment that the file already has.
- adds one line at the top that registers the ID in `globalThis._debugIds`.
- appends a `//# debugId=<id>` comment, and writes the same ID into the map's `debugId` field.

Run `inject` before any step that hashes or compresses the bundle, such as precompression (`.br`, `.gz`), subresource integrity hashes or content-addressed CDN uploads. `inject` changes the bundle bytes, so a hash computed before it no longer matches.

Running `inject` again on the same directory is safe. It reports each file as `unchanged`.

## Upload source maps in CI

Upload the maps in CI, after the build and **before you deploy**. Logfire resolves an exception only if its source map is already stored when the exception arrives (see [Late uploads](#late-uploads)).

```bash
logfire --beta --region us sourcemap upload dist --frontend-application-id <frontend-application-id>
```

For a Next.js app, upload the browser chunks under `.next/static`, which Next.js serves from `/_next/static`:

```bash
logfire --beta --region us sourcemap upload .next/static \
  --frontend-application-id <frontend-application-id> \
  --base-url-path /_next/static \
  --delete
```

### Authentication

`upload` reads the credential from `LOGFIRE_API_KEY`. Use a project API key with the `project:write_sourcemaps` scope. Create it on the project's API keys page in Logfire. The project comes from the key, so you do not pass it on the command line. Also pass `--region` (or `--base-url` for a self-hosted Logfire) so the CLI knows which Logfire instance to call.

In GitHub Actions, store the key as a repository secret:

```yaml
- run: npm ci && npm run build
- run: npx logfire-cli --beta sourcemap inject dist
- run: npx logfire-cli --beta --region us sourcemap upload dist --frontend-application-id <frontend-application-id> --delete
  env:
    LOGFIRE_API_KEY: ${{ secrets.LOGFIRE_API_KEY }}
```

### Options

| Option | Purpose |
| --- | --- |
| `<DIRECTORY>` | The build output directory to upload. |
| `--frontend-application-id <UUID>` | The browser application that owns the bundles. Its ID is on the project's Frontend page. |
| `--service-name <NAME>`, `--service-namespace <NAMESPACE>` | The service that owns the bundles, if it is not a frontend application. Use the `service.name` that the SDK reports. |
| `--release <ID>` | The release identifier, such as the commit SHA. The default comes from `LOGFIRE_RELEASE`, `GITHUB_SHA`, `VERCEL_GIT_COMMIT_SHA` or `CF_PAGES_COMMIT_SHA`, else `git rev-parse HEAD`. |
| `--base-url-path <PATH>` | The URL path that the directory is served from. The default is `/`. |
| `--maps-only` | Upload the maps without the bundles. Logfire then keeps the minified function names. |
| `--strip-sources` | Remove the embedded source text (`sourcesContent`) from the uploaded maps. Logfire then shows no source lines around a frame. |
| `--delete` | Delete each `.map` file and the bundle's `sourceMappingURL` comment after the upload succeeds, so the maps do not ship to browsers. |

Pass exactly one owner: `--frontend-application-id`, or `--service-name`.

The CLI sends these values as the query parameters `frontend_application_id` or `service_name`, `service_namespace`, `service_version` (the release) and `bundle_url_path`. Logfire stores them with the map to describe the build. Logfire finds the map by debug ID only.

### Upload results

Each map goes to its own debug ID. The CLI prints one line per file. These are the server answers you can see:

| Answer | Meaning | What to do |
| --- | --- | --- |
| `201 Created` | Logfire stored the map. | Nothing. |
| `200 OK` | Logfire already has identical content for this debug ID. | Nothing. A retry of the same upload is safe. |
| `409 Conflict` | Logfire already has *different* content for this debug ID. | Rebuild so the files get a new debug ID, or upload with the same flags (such as `--strip-sources`) that produced the stored map. |
| `400 Bad Request` | The map is invalid. For example, it is not valid JSON, or its `debugId` does not match the debug ID of its bundle. | Check the build output, then run `inject` and `upload` again. |

## Late uploads

Logfire resolves stack traces when it receives the data, not when you view it. An exception that arrives before its source map is uploaded stays minified, and a later upload does not change it. Exceptions that arrive after the upload resolve normally. So upload in CI before the deploy starts serving the new bundles.

## Retention

Logfire deletes an uploaded source map 90 days after it was last used to resolve an exception. A map that no exception uses is deleted 90 days after its upload. This retention is separate from your data retention. Exceptions that were already resolved keep their resolved stack trace.

## Check the result

Logfire writes the `logfire.source_map.status` attribute on each exception that carries debug IDs:

| Status | Meaning |
| --- | --- |
| `ok` | Every frame with a debug ID resolved to original source. |
| `partial` | Some frames resolved, and others did not. |
| `missing` | Logfire has no source map for the debug IDs. Check that the upload ran for this build. |
| `error` | Logfire could not use the source map. Check that the map is valid. |
| `pending` | Logfire did not finish loading the source map in time. The stack trace stays minified. |

For `missing`, `error` and `pending`, the stack trace stays as the browser sent it.

To find exceptions that did not resolve, query for the status:

```sql
SELECT start_timestamp, exception_type, attributes->>'logfire.source_map.status' AS status
FROM records
WHERE attributes->>'logfire.source_map.status' NOT IN ('ok', 'partial')
ORDER BY start_timestamp DESC
```
