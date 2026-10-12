// Part 2b: capture a Jaeger page, or one element of it, as a PNG.
//
//   node scripts/part2b/capture.mjs <url> <out.png> [--clip <css selector>] [--also <css selector>]
//                                   [--click <css selector>] [--eval <js>] [--width 1700] [--height 1000]
//
// --click  clicks the first matching element before capturing (e.g. to open a span's tags).
// --clip   captures only that element. --also widens the capture to include a second element.
// --eval   prints the result of a JS expression instead of capturing (for finding selectors).
//
// Drives a headless Edge over the DevTools protocol. Needs Node 22+ and Microsoft Edge.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const EDGE = process.env.EDGE ?? 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9300 + Math.floor(Math.random() * 500);

const [url, out, ...rest] = process.argv.slice(2);
const option = (name, fallback) => {
  const at = rest.indexOf(`--${name}`);
  return at === -1 ? fallback : rest[at + 1];
};
const width = Number(option('width', 1700));
const height = Number(option('height', 1000));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const edge = spawn(
  EDGE,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${mkdtempSync(join(tmpdir(), 'part2b-edge-'))}`,
    `--window-size=${width},${height}`,
    'about:blank',
  ],
  { stdio: 'ignore' },
);

async function debuggerUrl() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const pages = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = pages.find((entry) => entry.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch {
      // Edge is still starting.
    }
    await sleep(200);
  }
  throw new Error('Edge did not start');
}

try {
  const socket = new WebSocket(await debuggerUrl());
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });

  let nextId = 0;
  const pending = new Map();
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      nextId += 1;
      pending.set(nextId, (message) =>
        message.error ? reject(new Error(`${method}: ${message.error.message}`)) : resolve(message.result),
      );
      socket.send(JSON.stringify({ id: nextId, method, params }));
    });
  const evaluate = async (expression) =>
    (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.value;

  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  // Jaeger renders after its API calls return; there is no single event to wait for.
  await sleep(6000);

  const click = option('click');
  if (click) {
    const clicked = await evaluate(
      `(() => { const el = document.querySelector(${JSON.stringify(click)}); if (!el) return false; el.click(); return true; })()`,
    );
    if (!clicked) throw new Error(`nothing matches --click ${click}`);
    await sleep(800);
  }

  const probe = option('eval');
  if (probe) {
    console.log(JSON.stringify(await evaluate(probe), null, 2));
  } else {
    const selectors = [option('clip'), option('also')].filter(Boolean);
    let clip;
    if (selectors.length > 0) {
      const box = await evaluate(
        `(() => { const rects = ${JSON.stringify(selectors)}.map((s) => document.querySelector(s)).filter(Boolean)
            .map((el) => el.getBoundingClientRect());
          if (rects.length === 0) return null;
          const left = Math.min(...rects.map((r) => r.left)), top = Math.min(...rects.map((r) => r.top));
          const right = Math.max(...rects.map((r) => r.right)), bottom = Math.max(...rects.map((r) => r.bottom));
          return { x: left + scrollX, y: top + scrollY, width: right - left, height: bottom - top }; })()`,
      );
      if (!box) throw new Error(`nothing matches --clip ${selectors.join(', ')}`);
      clip = { ...box, scale: 1 };
    }
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, ...(clip ? { clip } : {}) });
    writeFileSync(out, Buffer.from(shot.data, 'base64'));
    console.log(`wrote ${out}`);
  }
  socket.close();
} finally {
  edge.kill();
}
