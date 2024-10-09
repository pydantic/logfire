package main

import (
	"context"
	"errors"
	"log"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	shutdown := initTracer()

	defer shutdown()

	tracer := otel.Tracer("go-example")
	ctx := context.Background()

	// work begins
	parentFunction(ctx, tracer)

	// bonus work
	exceptionFunction(ctx, tracer)
}

func initTracer() func() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)

	// Set up a trace exporter
	traceExporter, err := otlptracehttp.New(ctx,
		otlptracehttp.WithEndpoint("logfire-api.pydantic.dev"),
	)
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

func parentFunction(ctx context.Context, tracer trace.Tracer) {
	ctx, parentSpan := tracer.Start(
		ctx,
		"hello world",
		trace.WithAttributes(attribute.String("string-attribute", "potato"), attribute.Int("int-attribute", 42)),
	)

	defer parentSpan.End()

	childFunction(ctx, tracer)
}

func childFunction(ctx context.Context, tracer trace.Tracer) {
	ctx, childSpan := tracer.Start(ctx, "child span")

	time.Sleep(200 * time.Millisecond)

	childSpan.AddEvent("child span has event")
	defer childSpan.End()
}

func exceptionFunction(ctx context.Context, tracer trace.Tracer) {
	ctx, exceptionSpan := tracer.Start(
		ctx,
		"exception span")
	defer exceptionSpan.End()

	err := errors.New("division by zero")

	if err != nil {
		exceptionSpan.RecordError(err)
		exceptionSpan.SetStatus(codes.Error, err.Error())
	}
}
