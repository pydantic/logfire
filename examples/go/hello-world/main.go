package main

import (
	"context"
	"log"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	// Initialize the OpenTelemetry tracing system
	shutdown := initTracer()

	// Ensure the tracer is shut down at the end of the program
	defer shutdown()

	// Create a tracer and context
	tracer := otel.Tracer("go-example")
	ctx := context.Background()

	// work begins
	helloWorld(ctx, tracer)
}

func initTracer() func() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)

	// Set up a trace exporter
	traceExporter, err := otlptracehttp.New(ctx)
	if err != nil {
		log.Fatalf("failed to create HTTP exporter: %v", err)
	}

	// Register the trace exporter with a TracerProvider, using a batch
	// span processor to aggregate spans before export.
	batchSpanProcessor := sdktrace.NewBatchSpanProcessor(traceExporter)
	tracerProvider := sdktrace.NewTracerProvider(
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithSpanProcessor(batchSpanProcessor),
	)
	otel.SetTracerProvider(tracerProvider)

	return func() {
		// Shutdown will flush any remaining spans and shut down the exporter.
		err := tracerProvider.Shutdown(ctx)
		if err != nil {
			log.Fatalf("failed to shutdown TracerProvider: %v", err)
		}
		cancel()
	}
}

func helloWorld(ctx context.Context, tracer trace.Tracer) {
	ctx, parentSpan := tracer.Start(
		ctx,
		"hello world",
		trace.WithAttributes(attribute.String("string-attribute", "potato"), attribute.Int("int-attribute", 42)),
	)

	defer parentSpan.End()

	time.Sleep(100 * time.Millisecond)
	childFunction(ctx, tracer)
	time.Sleep(100 * time.Millisecond)
}

func childFunction(ctx context.Context, tracer trace.Tracer) {
	ctx, childSpan := tracer.Start(ctx, "child span")

	time.Sleep(50 * time.Millisecond)

	defer childSpan.End()
}
