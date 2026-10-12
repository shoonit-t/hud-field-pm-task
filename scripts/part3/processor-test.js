// Part 3 check: can one span processor, registered once in the SDK core, record
// the event loop's busy time on every "client" span? Uses the real SDK packages.
const { createRequire } = require('node:module');
const req = createRequire(process.argv[2] + '/');
const { SpanKind } = req('@opentelemetry/api');
const { BasicTracerProvider, SimpleSpanProcessor, InMemorySpanExporter } = req('@opentelemetry/sdk-trace-base');
const { performance } = require('node:perf_hooks');

const startReadings = new WeakMap();
const eventLoopProcessor = {
  onStart(span) {
    if (span.kind === SpanKind.CLIENT) startReadings.set(span, performance.eventLoopUtilization());
  },
  onEnding(span) {
    const start = startReadings.get(span);
    if (start) span.setAttribute('nodejs.eventloop.busy_ms', Math.round(performance.eventLoopUtilization(start).active));
  },
  onEnd() {}, forceFlush: async () => {}, shutdown: async () => {},
};

const exporter = new InMemorySpanExporter();
const provider = new BasicTracerProvider({ spanProcessors: [eventLoopProcessor, new SimpleSpanProcessor(exporter)] });
const tracer = provider.getTracer('part3-test');

const fakeCall = () => new Promise((resolve) => setTimeout(resolve, 10));     // the outside system answers in 10 ms
const block = (ms) => { const end = Date.now() + ms; while (Date.now() < end); };

async function run(name, kind, alsoRunning) {
  const span = tracer.startSpan(name, { kind });
  const pending = fakeCall();
  if (alsoRunning) setImmediate(alsoRunning);
  await pending;
  span.end();
}
(async () => {
  await run('warm-up', SpanKind.CLIENT);
  await run('pg.query:SELECT (normal)', SpanKind.CLIENT);
  await run('pg.query:SELECT (thread blocked 290 ms)', SpanKind.CLIENT, () => block(290));
  await run('POST fraud-service (thread blocked 150 ms)', SpanKind.CLIENT, () => block(150));
  await run('request handler (not a client span)', SpanKind.INTERNAL, () => block(100));
  for (const s of exporter.getFinishedSpans().slice(1)) {
    const ms = (s.duration[0] * 1e3 + s.duration[1] / 1e6).toFixed(0);
    console.log(`${s.name.padEnd(46)} duration ${ms.padStart(4)} ms   tags ${JSON.stringify(s.attributes)}`);
  }
})();
