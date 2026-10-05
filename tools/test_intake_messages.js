'use strict';
// Synthetic regression for the Admin intake status messages in web/app.js.
// Runs the real questions.js + app.js in a Node vm with a stub DOM and a recording fake
// WebView2 bridge. No network, files, keys, accounts or native host are touched.
// Usage: node tools/test_intake_messages.js
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const web = process.env.NOSE_WEB_DIR || path.join(__dirname, '..', 'web');

function run() {
  const elements = new Map(), listeners = [], posted = [];
  const el = id => {
    if (!elements.has(id)) elements.set(id, {
      id, textContent: '', disabled: false, hidden: false, checked: false, value: '', title: '', dataset: {}, style: {},
      children: [], classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
      addEventListener() {}, removeEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {}, scrollIntoView() {},
      querySelectorAll: () => [], querySelector: () => null, closest: () => null,
      replaceChildren(...c) { this.children = c; }, append(...c) { this.children.push(...c); },
      set innerHTML(v) { throw new Error('innerHTML must not be used: ' + id); },
    });
    return elements.get(id);
  };
  const document = {
    getElementById: el, querySelector: () => null, querySelectorAll: () => [],
    createElement: tag => Object.assign(el('created-' + Math.random()), { tag }),
    addEventListener() {}, activeElement: null, hidden: false, visibilityState: 'visible',
  };
  const ctx = vm.createContext({
    document, console, performance: { now: () => 0 }, setTimeout: () => 0, clearTimeout() {},
    setInterval: () => 0, clearInterval() {}, requestAnimationFrame: () => 0, addEventListener() {},
    Worker: function () { throw new Error('no workers in synthetic test'); }, URL, Blob: function () {},
    chrome: { webview: { postMessage: m => posted.push(m), addEventListener: (t, f) => listeners.push(f) } },
  });
  // The vm global is the page's window, as in a browser.
  vm.runInContext('globalThis.window = globalThis.self = globalThis;', ctx);
  for (const f of ['questions.js', 'app.js']) vm.runInContext(fs.readFileSync(path.join(web, f), 'utf8'), ctx, { filename: f });
  const send = m => listeners.forEach(f => f({ data: m }));
  return { el, posted, send };
}

const GENERIC = 'Collection could not complete. Check the organizer GitHub sign-in and try again.';
const NEW = {
  intake_migration_required: [/intake_worker\.py migrate/, /once/, /never migrates it automatically/, /left unchanged/],
  migration_backup_conflict: [/preserved unchanged/, /repair the conflicting backup/],
  recipient_key_setup_invalid: [/^Collection stopped/, /recipient key/, /could not be verified/],
};
let checks = 0;
const ok = (c, m) => { assert.ok(c, m); checks++; };

// 1. Each new code renders its fixed message for a correlated (pending) request.
for (const [code, patterns] of Object.entries(NEW)) {
  const t = run();
  t.send({ kind: 'edition', mode: 'admin' });
  t.el('intake-refresh').onclick();
  ok(t.posted.some(p => p.command === 'intake-queue'), 'queue posted');
  t.send({ kind: 'intake-result', data: { schemaVersion: 1, command: 'queue', ok: false, error: code } });
  const text = t.el('intake-status').textContent;
  ok(typeof text === 'string' && text !== GENERIC, code + ' has a specific message');
  for (const p of patterns) ok(p.test(text), code + ' matches ' + p);
  ok(!/resend|re-send|upload again|share again/i.test(text) || /do not need to resend/.test(text), code + ' never asks participants to resend');
  ok(!/reset|change|replace|update/i.test(text.replace(/left unchanged|preserved unchanged/g, '')) , code + ' never asks to reset or change pins/keys');
  ok(!t.el('intake-refresh').disabled, code + ' re-enables controls after the error');
}

// 2. Same codes also render on the worker stream path (start -> run failure).
{
  const t = run();
  t.send({ kind: 'edition', mode: 'admin' });
  t.el('intake-start').onclick();
  t.send({ kind: 'intake-result', stream: true, data: { schemaVersion: 1, command: 'run', ok: false, error: 'recipient_key_setup_invalid' } });
  ok(/^Collection stopped: the local recipient key/.test(t.el('intake-status').textContent), 'stream path renders key message');
}

// 3. Unknown and inherited/prototype names fall back to the generic message as plain text.
for (const code of ['intake_command_failed', 'not_a_code', 'constructor', 'toString', '__proto__', 'hasOwnProperty', '<b>x</b>', 7, null, undefined]) {
  const t = run();
  t.send({ kind: 'edition', mode: 'admin' });
  t.el('intake-catchup').onclick();
  t.send({ kind: 'intake-result', data: { schemaVersion: 1, command: 'catchup', ok: false, error: code } });
  ok(t.el('intake-status').textContent === GENERIC, 'generic fallback for ' + String(code));
}

// 4. Existing code still maps to its existing message (no regressions in the map).
{
  const t = run();
  t.send({ kind: 'edition', mode: 'admin' });
  t.el('intake-refresh').onclick();
  t.send({ kind: 'intake-result', data: { schemaVersion: 1, command: 'queue', ok: false, error: 'organizer_account_mismatch' } });
  ok(/different account/.test(t.el('intake-status').textContent), 'existing mapping intact');
}

// 5. Correlation: an uncorrelated non-stream result (no pending request / wrong command) is ignored.
{
  const t = run();
  t.send({ kind: 'edition', mode: 'admin' });
  t.el('intake-status').textContent = 'sentinel';
  t.send({ kind: 'intake-result', data: { schemaVersion: 1, command: 'queue', ok: false, error: 'recipient_key_setup_invalid' } });
  ok(t.el('intake-status').textContent === 'sentinel', 'uncorrelated result ignored');
  t.el('intake-refresh').onclick();
  t.send({ kind: 'intake-result', data: { schemaVersion: 1, command: 'catchup', ok: false, error: 'recipient_key_setup_invalid' } });
  ok(t.el('intake-status').textContent === 'Working…', 'wrong-command result ignored while queue pending');
}

// 6. Gates: non-admin edition and an active recording both refuse intake requests.
{
  const t = run();
  t.el('intake-refresh').onclick();
  ok(!t.posted.some(p => String(p.command).startsWith('intake-')), 'collector edition never posts intake commands');
  t.send({ kind: 'edition', mode: 'admin' });
  try { t.send({ kind: 'started', sessionId: 'c'.repeat(32), mode: 'human', testId: 'practice-js-5', testVersion: 1, questionCount: 5 }); } catch { /* page rendering stubs are partial */ }
  t.el('intake-refresh').onclick();
  ok(!t.posted.some(p => p.command === 'intake-queue'), 'recording blocks intake requests');
}

console.log('PASS: ' + checks + ' synthetic intake message checks');
