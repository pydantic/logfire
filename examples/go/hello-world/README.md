# Hello world Logfire in Go

This is a very simple example of sending traces to Logfire from a Go application.

**WARNING:** I am not a Go developer! This examples runs and the results are visible in Logfire, but I can't guarantee it's good Go code. (if you are a Go developer and hate what I've done, feel free to create a PR to improve it).

## Run the project

1. Install Go if you haven't already
2. Install deps, the internet suggests you should run `go get .`
3. Set a Logfire write token to use as the `Authorization` header, via the `OTEL_EXPORTER_OTLP_HEADERS` env variable, e.g. `export OTEL_EXPORTER_OTLP_HEADERS='Authorization=<write-token>'`
4. Run the project with `go run main.go`
5. You should see two traces in the Logfire app, one with a nested span
