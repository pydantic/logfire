---
title: "Pydantic Logfire: Browser Source Maps"
description: "Upload source maps from CI so Logfire shows browser exceptions with your original file, function and line instead of minified code."
---

# Browser source maps

!!! warning "Experimental"
    Browser source maps are experimental. The behavior on this page can change before the feature reaches Beta.

Production JavaScript is usually *minified*: the bundler (the build tool that combines your code into a few files, such as Vite, webpack or Turbopack) renames functions and puts the code on a few long lines. A stack trace from a minified bundle points at `index-a1b2.js:1:48213`, which tells you little.

A *source map* is a JSON file that the bundler writes next to each bundle. It maps every position in the minified file back to the original file, line and function. When you upload your source maps to Logfire, Logfire shows browser exceptions with your original code.

## Before you begin

You need these two things:

- An app that sends browser exceptions to Logfire with `@pydantic/logfire-browser` version 0.34.0 or later. See the [browser SDK setup](https://pydantic.dev/docs/logfire/instrument/typescript/packages/browser/).
- The ID of your *frontend application*. A frontend application is the entry in a Logfire project that gives the browser data of one web app a stable name and a restricted token. Find it under **Project settings → Frontend applications** (see [Frontend](../guides/web-ui/frontend.md)).

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

1. A snippet at the top of each bundle registers the bundle's debug ID when the bundle loads. `logfire sourcemap inject` writes the ID to `globalThis._logfireDebugIds`. Turbopack and other tools write it to `globalThis._debugIds`, which is a shared convention. The SDK reads both registries.
2. When the Logfire browser SDK records an exception, it looks up the files in the stack trace in that registry. It adds the matches to the exception span as the `logfire.debug_ids` attribute: a JSON map from file URL to debug ID. The SDK removes the query string, the fragment and any credentials from each URL.
3. When the span reaches Logfire, Logfire finds the uploaded source map for each debug ID and rewrites the stack trace to the original source. This happens once, at ingest (when Logfire receives and stores the data). The stored record holds the resolved stack trace.

Logfire keeps the stack trace as the browser sent it in `logfire.source_map.original_stacktrace`.

The SDK sends `logfire.debug_ids` from `@pydantic/logfire-browser` version 0.34.0. An earlier version sends no debug IDs, so its exceptions stay minified.

## Give your bundles debug IDs

The commands on this page come from the Logfire CLI for JavaScript projects, the `logfire-cli` npm package. Run them with `npx logfire-cli`. The `logfire` command that the Python package installs has no `sourcemap` command.

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

`turbopack.debugIds` needs Next.js 16.0.0 or later. On an earlier version, or when you build with webpack (`next build --webpack`), keep `productionBrowserSourceMaps` and run `inject` after `next build`:

```bash
npx logfire-cli --beta sourcemap inject .next
```

!!! note "Browser exceptions only"
    This page covers exceptions that `@pydantic/logfire-browser` records in the browser. Next.js middleware and edge runtime code run on the server, so the browser SDK does not send their exceptions.

### Other bundlers

For Vite, webpack, esbuild, Rollup and other bundlers, build with source maps on:

- Vite: set `build.sourcemap: true` in `vite.config.js`.
- webpack: set `devtool: 'source-map'` in `webpack.config.js`.
- esbuild: pass `--sourcemap`.
- Rollup: set `output.sourcemap: true` in `rollup.config.js`.

Then run `logfire sourcemap inject` on the build output directory:

```bash
npx logfire-cli --beta sourcemap inject dist
```

The command processes every `.js`, `.mjs` and `.cjs` file that has a source map. For each file, it:

- derives a debug ID from the file's bytes, so a rebuild of the same code gets the same ID. It keeps a `//# debugId=` comment that the file already has.
- adds one line at the top that registers the ID in `globalThis._logfireDebugIds`. The SDK reads this registry and `globalThis._debugIds`.
- appends a `//# debugId=<id>` comment, and writes the same ID into the map's `debugId` field.

Run `inject` before any step that hashes or compresses the bundle, such as precompression (`.br`, `.gz`), subresource integrity hashes or content-addressed CDN uploads. `inject` changes the bundle bytes, so a hash computed before it no longer matches.

Running `inject` again on the same directory is safe. It reports each file as `unchanged`.

The files you upload must be exactly the files you deploy. If a later step changes a bundle, its stack traces no longer match the uploaded source map.

## Upload source maps in CI

Upload the maps in CI, after the build and **before you deploy**. Logfire resolves an exception only if its source map is already stored when the exception arrives (see [Late uploads](#late-uploads)).

```bash
npx logfire-cli --beta --region us sourcemap upload dist --frontend-application-id <frontend-application-id> --delete
```

`--delete` removes the `.map` files after the upload, so the deploy does not serve your source maps to browsers. Leave it out only if you want the maps to be public.

Each source map and each bundle can be at most 60 MiB, measured before compression. The CLI reports a larger file as failed, and the server answers `413`. Split the bundle into smaller chunks to get under the limit.

!!! note "Source text in maps"
    Most bundlers embed your original source code in each map, in the `sourcesContent` field. By default, `upload` sends it to Logfire, which uses it to show the source lines around each frame. Pass `--strip-sources` to send the maps without the source text. Resolved frames then show the original file, function and line, but no source lines.

For a Next.js app, upload the browser chunks under `.next/static`, which Next.js serves from `/_next/static`:

```bash
npx logfire-cli --beta --region us sourcemap upload .next/static \
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

These are the flags that this page uses:

| Option | Purpose |
| --- | --- |
| `<DIRECTORY>` | The build output directory to upload. |
| `--frontend-application-id <UUID>` | The browser application that owns the bundles. Its ID is on the project's Frontend page. |
| `--base-url-path <PATH>` | The URL path that the directory is served from. The default is `/`. |
| `--strip-sources` | Remove the embedded source text (`sourcesContent`) from the uploaded maps. Logfire then shows no source lines around a frame. |
| `--delete` | Delete each `.map` file and the bundle's `sourceMappingURL` comment after the upload succeeds, so the maps do not ship to browsers. |
| `--region <REGION>`, `--base-url <URL>` | The Logfire instance that the API key belongs to. |

<!-- TODO: link to the public `logfire-cli` reference page for `sourcemap` when it is published. -->
For the other flags, run `npx logfire-cli --beta sourcemap upload --help`.

### Upload results

The CLI prints one line per bundle with its debug ID and the result, then a summary. These are the results you can see:

| Result | Meaning | What to do |
| --- | --- | --- |
| Stored (`created`) | Logfire stored the file. | Nothing. |
| Already uploaded (`exists`) | Logfire already has identical content for this debug ID. | Nothing. A retry of the same upload is safe. |
| Conflict | Logfire already has *different* content for this debug ID. | Rebuild so the files get a new debug ID, or upload with the same flags (such as `--strip-sources`) that produced the stored map. |
| Invalid | Logfire rejected the map. For example, it is not valid JSON, or its `debugId` does not match the debug ID of its bundle. | Check the build output, then run `inject` and `upload` again. |
| Too large | The map or the bundle is larger than 60 MiB. | Split the bundle into smaller chunks, then build and upload again. |
| Rate limited or quota full | The project sends uploads too fast, or its source map quota is full. The CLI waits for the time that the server names, then tries again. It tries each file at most 4 times, and it stops if the wait is longer than 60 seconds. | Nothing if the retry succeeds. If the file still fails, run `upload` again later. |

A result other than stored or already uploaded shows as `failed`, with the reason from the server. If a file fails, the command exits with a non-zero code, so the CI job fails before the deploy.

## Late uploads

Logfire resolves stack traces when it receives the data, not when you view it. An exception that arrives before its source map is uploaded stays minified, and a later upload does not change it. Logfire does not process a stored exception again. Exceptions that arrive after the upload resolve normally. So upload in CI before the deploy starts serving the new bundles.

## Retention

Logfire deletes an uploaded source map 90 days after it was last used to resolve an exception. A map that no exception uses is deleted 90 days after its upload. This retention is separate from your data retention. Exceptions that were already resolved keep their resolved stack trace.

## Check the result

A resolved exception shows the original file, function, line and column in its stack trace, in the `exception.stacktrace` attribute:

```text
Error: checkout failed
    at submitOrder (src/checkout.ts:42:5)
    at HTMLButtonElement.<anonymous> (src/checkout.ts:88:3)
```

The `logfire.source_map.original_stacktrace` attribute on the same exception holds the minified stack trace as the browser sent it:

```text
Error: checkout failed
    at o (https://app.example.com/assets/index-a1b2.js:1:48213)
    at HTMLButtonElement.<anonymous> (https://app.example.com/assets/index-a1b2.js:1:48392)
```

Logfire writes the `logfire.source_map.status` attribute on each exception that carries debug IDs:

| Status | Meaning |
| --- | --- |
| `ok` | Every frame with a debug ID resolved to original source. |
| `partial` | At least one frame resolved, and at least one frame did not. The unresolved frames stay minified. |
| `missing` | No frame resolved. Logfire has no source map for the debug IDs. |
| `error` | No frame resolved. Logfire could not load or use the source map. |
| `pending` | No frame resolved. Logfire did not finish loading the source map in time. |

For `missing`, `error` and `pending`, the stack trace stays as the browser sent it.

To find exceptions with at least one frame that did not resolve, query for every status other than `ok`:

```sql
SELECT start_timestamp, exception_type, attributes->>'logfire.source_map.status' AS status
FROM records
WHERE attributes->>'logfire.source_map.status' != 'ok'
ORDER BY start_timestamp DESC
```

## Troubleshooting

Start from what you see on the exception.

### The exception has no `logfire.source_map.status`

The exception carries no debug IDs, so Logfire did not try to resolve it. Do these two checks in order.

**1. The built bundle contains the debug ID snippet.** Run this command on the build output directory. Use `dist`, or `.next/static` for a Next.js app:

```bash
grep -rlE '_debugIds|_logfireDebugIds' dist --include='*.js' --include='*.mjs' --include='*.cjs'
grep -rlE '_debugIds|_logfireDebugIds' .next/static --include='*.js'
```

The command lists each bundle that registers a debug ID. Turbopack writes `_debugIds`, and `logfire sourcemap inject` writes `_logfireDebugIds`. If a bundle is not in the list, turn on `turbopack.debugIds` or run `inject` (see [Give your bundles debug IDs](#give-your-bundles-debug-ids)). Then do the same check on the file that the browser downloads, to make sure that the deploy serves the new build.

**2. The exception span has `logfire.debug_ids`.** Query for the attribute:

```sql
SELECT start_timestamp, exception_type, attributes->>'logfire.debug_ids' AS debug_ids
FROM records
WHERE is_exception
ORDER BY start_timestamp DESC
```

If the bundle has the snippet but the attribute is empty, check these causes:

- The app uses `@pydantic/logfire-browser` earlier than 0.34.0. Upgrade the SDK.
- No frame in the stack trace comes from a bundle with a debug ID. For example, the error comes from a third-party script.

### The status is not `ok`

| Status | Likely cause | Fix |
| --- | --- | --- |
| `missing` | The upload did not run for this build, or it ran after the exception arrived. A second cause is that the deployed files are not the uploaded files. | Do the two checks below. |
| `partial` | Some frames resolved. The other frames have one of the causes in this table. For example, the upload covered only a part of the build output, or one file failed. | Read the upload log for skipped and failed files. Upload the full build output directory. |
| `error` | Logfire could not read or use the stored source map. For example, the bundler wrote a map that does not follow the source map format. | Check that the `.map` file from the build is valid. Fix the build, then build, `inject` and upload again. If the map is valid, contact support. |
| `pending` | Logfire did not load the source map in time. This can occur for the first exceptions of a new build, or when many new builds arrive together. | The exceptions that already have `pending` stay minified for good. Logfire tries again on the next exception for the same build. If new exceptions keep the status `pending`, contact support. |

**The upload ran before the deploy.** Compare the time of the upload step in the CI log with the time of the deploy. The upload must finish first, and it must exit with code 0. An exception that arrives before the upload stays minified (see [Late uploads](#late-uploads)).

**The deployed files are exactly the uploaded files.** A debug ID identifies one exact build output. Compare the `//# debugId=` comment at the end of the deployed bundle with the comment in the bundle that CI uploaded:

```bash
curl -s https://app.example.com/assets/index-a1b2.js | tail -c 200
tail -c 200 dist/assets/index-a1b2.js
```

If the IDs differ, the deploy built the code again. Deploy the output of the build that you uploaded. If the IDs are the same but frames resolve to the wrong lines, a step after the upload changed the bundle. Do not minify the files again or compress them again with a tool that rewrites the JavaScript after `inject`. Transport compression by the web server or the CDN (`gzip`, Brotli) is safe, because the browser gets the same bytes back.
