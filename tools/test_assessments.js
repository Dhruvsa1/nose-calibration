'use strict';
// Synthetic checks for test selection: the assessment registry, deterministic grading of every coding
// question through the real grader worker source, per-session state isolation, the frozen test tuple and
// rejection of unknown or mismatched tuples. Runs the real web files in Node vm contexts with a stub DOM,
// a fake WebView2 bridge and an in-process grader. No window, host, network, files or recordings.
// Usage: node tools/test_assessments.js
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert'), crypto = require('crypto');
const web = process.env.NOSE_WEB_DIR || path.join(__dirname, '..', 'web');
const read = f => fs.readFileSync(path.join(web, f), 'utf8');
let checks = 0;
const ok = (c, m) => { assert.ok(c, m); checks++; };
const tick = () => new Promise(r => setImmediate(r));

// The real grader worker source in its own context; returns its posted result.
function grade(data) {
  let result;
  const ctx = vm.createContext({ postMessage: r => { result = r; }, structuredClone });
  vm.runInContext(read('grader.js'), ctx, { filename: 'grader.js' });
  ctx.onmessage({ data: JSON.parse(JSON.stringify(data)) });
  return result;
}

function registry() {
  const ctx = vm.createContext({});
  vm.runInContext('globalThis.window = globalThis;', ctx);
  vm.runInContext(read('questions.js'), ctx, { filename: 'questions.js' });
  return ctx.window;
}

// 1. Registry: exactly the two known tuples; the original five questions are unchanged.
const win = registry(), [original, extended] = win.assessments;
ok(win.assessments.length === 2, 'two assessments');
ok(original.testId === 'practice-js-5' && original.testVersion === 1 && original.questionCount === 5 && original.questions.length === 5, 'original tuple');
ok(extended.testId === 'practice-js-13' && extended.testVersion === 1 && extended.questionCount === 13 && extended.questions.length === 13, 'extended tuple');
ok(crypto.createHash('sha256').update(JSON.stringify(original.questions)).digest('hex') === '8287aacfa3afb8793e1dda4587b828bf614caabac126612e46ce2774f391c1de', 'original questions byte-identical to the pre-selection list');
ok(win.questions === original.questions, 'legacy alias is the original list');
ok(Object.isFrozen(win.assessments) && Object.isFrozen(extended.questions[0]) && Object.isFrozen(extended.questions[10].tests), 'registry is immutable');
const ids = [...original.questions, ...extended.questions].map(q => q.id);
ok(new Set(ids).size === ids.length, 'question IDs distinct across both tests');
for (const a of win.assessments) ok(new Set(a.questions.map(q => q.title)).size === a.questions.length, a.testId + ' titles unique');
const mc = extended.questions.filter(q => q.type === 'Multiple choice'), coding = extended.questions.filter(q => q.type === 'Coding');
ok(mc.length === 10 && coding.length === 3 && extended.questions.slice(0, 10).every(q => q.type === 'Multiple choice'), '10 multiple choice then 3 coding');
for (const q of mc) ok(q.options.length === 4 && new Set(q.options).size === 4 && q.options.filter(o => o === q.answer).length === 1, q.id + ' has one correct option');
const promptsOld = new Set(original.questions.map(q => q.prompt));
ok(extended.questions.every(q => !promptsOld.has(q.prompt)), 'new questions are distinct from the original');
const allowed = /\[('[^\]]+')\]\.includes\(fn\)/.exec(read('grader.js'))[1].split(',').map(s => s.slice(1, -1));
for (const q of [...original.questions, ...extended.questions].filter(q => q.type === 'Coding')) {
  ok(allowed.includes(q.fn) && q.tests.length >= 4 && q.tests.length <= 10, q.fn + ' allowlisted with bounded tests');
}

// 2. Deterministic grading. Reference solutions pass every case; plausible mistakes fail at least one.
const cases = {
  summarize: { pass: 'function summarize(numbers) {\n    let count = 0, sum = 0, evenCount = 0, max = null;\n    for (const n of numbers) { count++; sum += n; if (n % 2 === 0) evenCount++; if (max === null || n > max) max = n; }\n    return { count, sum, evenCount, max };\n}', fail: ['function summarize(numbers) { return { count: numbers.length, sum: 0, evenCount: 0, max: null }; }'] },
  makeReceipt: { pass: 'function makeReceipt(items) {\n    const lines = items.map(i => i.name + ": " + i.price);\n    lines.push("TOTAL: " + items.reduce((s, i) => s + i.price, 0));\n    return lines.join("\\n");\n}', fail: ['function makeReceipt(items) { return items.map(i => i.name + ": " + i.price).join("\\n") + "\\nTOTAL: 0"; }'] },
  countVowels: {
    pass: 'function countVowels(text) {\n    let count = 0;\n    for (const c of text.toLowerCase()) {\n        if ("aeiou".includes(c)) count++;\n    }\n    return count;\n}',
    fail: [
      'function countVowels(text) { let n = 0; for (const c of text) if ("aeiou".includes(c)) n++; return n; }', // ignores upper case
      'function countVowels(text) { let n = 0; for (const c of text.toLowerCase()) if ("aeiouy".includes(c)) n++; return n; }', // counts y
      'function countVowels(text) { let n = 0; for (const c of text.toLowerCase()) if ("aeiou".includes(c)) n++; return String(n); }', // string result
    ],
  },
  reverseWords: {
    pass: 'function reverseWords(sentence) {\n    return sentence.split(" ").reverse().join(" ");\n}',
    fail: [
      'function reverseWords(sentence) { return sentence.split("").reverse().join(""); }', // reverses letters
      'function reverseWords(sentence) { return sentence.split(" ").reverse().join(""); }', // drops spaces
      'function reverseWords(sentence) { return sentence.toLowerCase().split(" ").reverse().join(" "); }', // changes case
    ],
  },
  countAbove: {
    pass: 'function countAbove(numbers, limit) {\n    let count = 0;\n    for (const n of numbers) {\n        if (n > limit) count++;\n    }\n    return count;\n}',
    fail: [
      'function countAbove(numbers, limit) { return numbers.filter(n => n >= limit).length; }', // counts equal values
      'function countAbove(numbers, limit) { return numbers.filter(n => n < limit).length; }', // wrong direction
      'function countAbove(numbers, limit) { return numbers.length; }',
    ],
  },
};
for (const q of [...original.questions, ...extended.questions].filter(q => q.type === 'Coding')) {
  const c = cases[q.fn], request = source => ({ source, fn: q.fn, tests: q.tests });
  const first = grade(request(c.pass)), second = grade(request(c.pass));
  ok(first.passed === true && first.message.split('\n').length === q.tests.length, q.fn + ' reference passes every case');
  ok(JSON.stringify(first) === JSON.stringify(second), q.fn + ' grading is deterministic');
  for (const wrong of c.fail) ok(grade(request(wrong)).passed === false, q.fn + ' rejects a wrong solution');
  ok(grade(request(q.starter)).passed === false, q.fn + ' starter does not pass');
  ok(grade(request('function ' + q.fn + '( {')).passed === false, q.fn + ' syntax error fails');
}
ok(grade({ source: 'function hack(){}', fn: 'hack', tests: [] }).message === 'Invalid test request', 'unknown function name refused');

// 3. Page state. The real questions.js + app.js with a stub DOM and fake bridge/worker.
function page() {
  const elements = new Map(), listeners = [], posted = [], toasts = [];
  const el = id => {
    if (!elements.has(id)) elements.set(id, {
      id, textContent: '', disabled: false, hidden: false, checked: false, value: '', title: '', dataset: {}, style: {},
      children: [], classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
      addEventListener() {}, removeEventListener() {}, setAttribute() {}, removeAttribute() {}, focus() {}, scrollIntoView() {},
      querySelectorAll: () => [], querySelector: () => null, closest: () => null,
      replaceChildren(...c) { this.children = c; }, append(...c) { this.children.push(...c); },
    });
    return elements.get(id);
  };
  el('test-practice-js-5').checked = true; // markup default
  el('admin-prompt').value = 'Complete all five practice questions correctly. Use the personalized input tools and inspect results. Get 5/5.';
  const document = {
    getElementById: el, querySelector: () => null, querySelectorAll: () => [],
    createElement: tag => Object.assign(el('created-' + Math.random()), { tag }), createTextNode: text => ({ text }),
    addEventListener() {}, activeElement: null, hidden: false, visibilityState: 'visible', hasFocus: () => true,
  };
  function Worker() {}
  Worker.prototype.postMessage = function (data) { const r = grade(data); queueMicrotask(() => this.onmessage({ data: r })); };
  Worker.prototype.terminate = () => {};
  const ctx = vm.createContext({
    document, console, performance: { now: () => 0 }, setTimeout: () => 0, clearTimeout() {},
    setInterval: () => 0, clearInterval() {}, requestAnimationFrame: () => 0, addEventListener() {}, Worker,
    innerWidth: 1000, innerHeight: 800, devicePixelRatio: 1,
    chrome: { webview: { postMessage: m => posted.push(m), addEventListener: (t, f) => listeners.push(f) } },
  });
  vm.runInContext('globalThis.window = globalThis.self = globalThis;', ctx);
  for (const f of ['questions.js', 'app.js']) vm.runInContext(read(f), ctx, { filename: f });
  const send = m => listeners.forEach(f => f({ data: m }));
  el('toast').textContent = '';
  const choose = id => { for (const a of ['practice-js-5', 'practice-js-13']) el('test-' + a).checked = a === id; el('test-' + id).onchange?.(); };
  const start = () => { el('consent').checked = true; el('start-session').onclick(); return posted.filter(p => p.command === 'start').at(-1); };
  const echo = (s, extra = {}) => send({ kind: 'started', mode: 'human', sessionId: 'a'.repeat(32), testId: s.testId, testVersion: s.testVersion, questionCount: s.questionCount, ...extra });
  // Answer the current question through the editor stub, then move on (save() stores it).
  const answerAll = values => values.forEach((v, i) => { el('code-editor').value = v; if (i < values.length - 1) el('next').onclick(); });
  const last = command => posted.filter(p => p.command === command).at(-1);
  return { el, posted, send, choose, start, echo, answerAll, last, ctx };
}
const solutions = qs => qs.map(q => q.type === 'Coding' ? cases[q.fn].pass : q.answer);

(async () => {
  // 3a. Selector freezes the 13-question tuple; full correct answers grade 13/13.
  {
    const t = page();
    t.choose('practice-js-13');
    ok(t.el('admin-prompt').value.includes('13/13'), 'unedited Admin prompt follows the selected test');
    const s = t.start();
    ok(s.testId === 'practice-js-13' && s.testVersion === 1 && s.questionCount === 13 && s.consent === true, 'start names the selected tuple');
    t.echo(s);
    t.el('task-list').children[0].children[3].children[0].onclick();
    ok(t.el('question-nav').children.length === 13 && t.el('question-nav').children[10].dataset.section === 'S2' && !t.el('question-nav').children[3].dataset.section, '13-question rail labels coding at question 11');
    ok(t.el('test-practice-js-13').disabled && t.el('test-practice-js-5').disabled, 'selector locked while recording');
    t.choose('practice-js-5'); // a late change must not affect the running session
    ok(t.ctx.window.assessmentSession.testId === 'practice-js-13' && t.ctx.window.assessmentSession.questions.length === 13, 'bound session stays practice-js-13');
    ok(t.el('basics-count').textContent === '10 questions' && t.el('coding-count').textContent === '3 questions', 'overview section counts follow the test');
    t.answerAll(solutions(extended.questions));
    t.el('finish-session').onclick();
    const finish = t.last('finish').answers;
    ok(finish.testId === 'practice-js-13' && finish.questionCount === 13 && finish.total === 13 && finish.values.length === 13, 'finish snapshot carries the frozen tuple');
    for (let i = 0; i < 40 && !t.last('finalized'); i++) await tick();
    const final = t.last('finalized').answers;
    ok(final.score === 13 && Object.keys(final.grades).length === 13 && Object.values(final.grades).every(g => g.passed), 'all 13 graded and passed');
    ok(t.el('score-summary').textContent === '13 / 13 questions passed' && t.el('results-test').textContent === 'Extended practice · 13 questions', 'results show the session test');

    // 3b. New session with the original test: fresh state, nothing carried over.
    t.el('new-session').onclick();
    ok(!t.el('test-practice-js-5').disabled, 'selector unlocked after the session');
    t.choose('practice-js-5');
    const s5 = t.start();
    ok(s5.testId === 'practice-js-5' && s5.questionCount === 5, 'second start names the original tuple');
    t.echo(s5, { sessionId: 'b'.repeat(32) });
    t.el('task-list').children[0].children[3].children[0].onclick();
    const rail=t.el('question-nav').children;
    ok(rail[0].dataset.section==='S1'&&!rail[1].dataset.section&&!rail[2].dataset.section&&rail[3].dataset.section==='S2','legacy rail retains only question 1 and 4 section markers');
    t.el('code-editor').value = original.questions[0].starter || '';
    t.el('finish-session').onclick();
    const fresh = t.last('finish').answers;
    ok(fresh.testId === 'practice-js-5' && fresh.total === 5 && fresh.values.length === 5 && Object.keys(fresh.grades).length === 0, 'fresh 5-question state');
    ok(!fresh.values.some(v => Object.values(cases).some(c => c.pass === v)), 'no answers carried from the 13-question session');
    for (let i = 0; i < 40 && t.posted.filter(p => p.command === 'finalized').length < 2; i++) await tick();
    ok(t.last('finalized').answers.score === 0 && t.last('finalized').sessionId === 'b'.repeat(32), 'original test graded within its own session');
  }

  // 3c. Original test, full marks: unchanged 5/5 behaviour.
  {
    const t = page();
    const s = t.start();
    ok(s.testId === 'practice-js-5' && s.testVersion === 1 && s.questionCount === 5, 'default selection is the original test');
    t.echo(s);
    t.answerAll(solutions(original.questions));
    t.el('finish-session').onclick();
    for (let i = 0; i < 40 && !t.last('finalized'); i++) await tick();
    const a = t.last('finalized').answers;
    ok(a.score === 5 && a.total === 5 && a.values.length === 5 && t.el('score-summary').textContent === '5 / 5 questions passed', 'original 5/5');
  }

  // 3d. One wrong multiple-choice answer costs exactly one point.
  {
    const t = page();
    t.choose('practice-js-13'); t.echo(t.start());
    const values = solutions(extended.questions); values[3] = '9';
    t.answerAll(values); t.el('finish-session').onclick();
    for (let i = 0; i < 40 && !t.last('finalized'); i++) await tick();
    const a = t.last('finalized').answers;
    ok(a.score === 12 && a.grades[3].passed === false, '12/13 with one wrong choice');
  }

  // 3e. Host stop finalizes under the frozen tuple.
  {
    const t = page();
    t.choose('practice-js-13'); t.echo(t.start());
    t.send({ kind: 'stopped' });
    const a = t.last('finalized').answers;
    ok(a.testId === 'practice-js-13' && a.values.length === 13 && a.total === 13, 'host stop keeps the session tuple');
  }

  // 3f. Unknown or mismatched tuples are refused and the host recording is stopped.
  for (const [label, change] of [['different test', { testId: 'practice-js-5', questionCount: 5 }], ['unknown version', { testVersion: 2 }],
    ['wrong count', { questionCount: 5 }], ['missing tuple', { testId: undefined }], ['string version', { testVersion: '1' }]]) {
    const t = page();
    t.choose('practice-js-13');
    t.echo(t.start(), change);
    ok(t.last('stop') && !t.el('test-practice-js-13').disabled && t.el('welcome').hidden === false, 'refused started: ' + label);
    t.send({ kind: 'stopped' });
    ok(!t.posted.some(p => p.command === 'finalized' || p.command === 'finish'), 'nothing finalized for refused start: ' + label);
  }

  // 3g. Loading binds the recording's own tuple; legacy recordings arrive mapped to the original test.
  {
    const t = page();
    t.choose('practice-js-5');
    t.send({ kind: 'loaded', sessionId: 'c'.repeat(32), mode: 'human', testId: 'practice-js-13', testVersion: 1, questionCount: 13, events: 3, answers: { grades: { 0: { passed: true } } } });
    ok(t.el('score-summary').textContent === '1 / 13 questions passed' && t.ctx.window.assessmentSession.testId === 'practice-js-13', 'loaded 13-question recording');
    ok(t.el('admin-prompt').value.includes('13/13'),'default Admin prompt follows loaded assessment');
    t.send({ kind: 'loaded', sessionId: 'd'.repeat(32), mode: 'human', testId: 'practice-js-5', testVersion: 1, questionCount: 5, events: 3, answers: { grades: {} } });
    ok(t.el('score-summary').textContent === '0 / 5 questions passed' && t.el('results-test').textContent === 'Original practice · 5 questions', 'loaded legacy-mapped recording');
    t.send({ kind: 'loaded', sessionId: 'e'.repeat(32), mode: 'human', testId: 'practice-js-13', testVersion: 1, questionCount: 5, events: 3 });
    ok(t.ctx.window.assessmentSession.sessionId === 'd'.repeat(32) && t.el('toast').textContent.includes('unknown test'), 'mismatched loaded tuple ignored');
  }

  // 3h. Admin edition starts Codex with the selected tuple.
  {
    const t = page();
    t.send({ kind: 'edition', mode: 'admin' });
    t.choose('practice-js-13');
    t.el('admin-run').onclick();
    const a = t.last('admin-start');
    ok(a.testId === 'practice-js-13' && a.testVersion === 1 && a.questionCount === 13 && a.prompt.includes('13/13'), 'admin-start names the selected tuple');
  }

  // 4. Markup: one named radio per registry test; the original is the default.
  {
    const html = read('index.html');
    for (const a of win.assessments) ok(new RegExp(`<input id="test-${a.testId}" type="radio" name="assessment-choice" value="${a.testId}"`).test(html), a.testId + ' radio present');
    ok((html.match(/name="assessment-choice"[^>]*checked/g) || []).length === 1 && /id="test-practice-js-5"[^>]*checked/.test(html), 'original test checked by default');
  }
  console.log('PASS: ' + checks + ' synthetic assessment checks. No host, window, network or recordings.');
})().catch(e => { console.error(e); process.exit(1); });
