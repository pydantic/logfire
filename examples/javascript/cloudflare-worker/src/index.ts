/**
 * Welcome to Cloudflare Workers! This is your first worker.
 *
 * - Run `npm run dev` in your terminal to start a development server
 * - Open a browser tab at http://localhost:8787/ to see your worker in action
 * - Run `npm run deploy` to publish your worker
 *
 * Bind resources to your worker in `wrangler.toml`. After adding bindings, a type definition for the
 * `Env` object can be regenerated with `npm run cf-typegen`.
 *
 * Learn more at https://developers.cloudflare.com/workers/
 */
import { trace } from '@opentelemetry/api';
import { instrument, ResolveConfigFn } from '@microlabs/otel-cf-workers';

export interface Env {
	LOGFIRE_WRITE_TOKEN: string;
	LOGFIRE_BASE_URL: string;
	OTEL_TEST: KVNamespace;
}

const handler = {
	async fetch(request, env, ctx): Promise<Response> {
		const tracer = trace.getTracer('cloudflare-worker');
		trace.getActiveSpan()?.setAttribute('greeting', 'Hello World!');
		const span = tracer.startSpan('my span');
		span.setAttribute('my-attribute', 'my-attribute-value');
		span.end();
		return new Response('Hello World!');
	},
} satisfies ExportedHandler<Env>;

const config: ResolveConfigFn = (env: Env, _trigger) => {
	return {
		exporter: {
			url: `${env.LOGFIRE_BASE_URL ?? 'https://logfire-api.pydantic.dev/'}v1/traces`,
			headers: { Authorization: env.LOGFIRE_WRITE_TOKEN },
		},
		service: { name: 'cloudflare-worker' },
	};
};

export default instrument(handler, config);
