# Hello world Logfire in Go

This is a very simple example of sending traces to Logfire from a Go application.

**WARNING:** I am not a Go developer! This examples runs and the results are visible in Logfire, but I can't guarantee it's good Go code. (if you are a Go developer and hate what I've done, feel free to create a PR to improve it).

## Run the project

Install Go if you haven't already

To install GO dependencies, from within this directory run:

```bash
go get .
```

Set the relevant environment variables for OTel:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
```

Run the project with

```bash
go run main.go
```

You should see a trace in the Logfire app.
