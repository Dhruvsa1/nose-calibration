'use strict';
// Visual-only enhancements for the assessment UI. Reads the DOM that app.js renders and
// builds display nodes with textContent only. It never posts to the native bridge, never
// records events and never changes answers. The page still works if this file is missing.
(() => {
 const $ = id => document.getElementById(id);
 const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
 // The bound session's questions (app.js sets them on start or load); before that, the original list.
 // Completion marks belong to one session and are cleared when another session is bound.
 const done = new Set();
 let doneFor = null;
 const qs = () => {
  const session = window.assessmentSession;
  if (session !== doneFor) { done.clear(); doneFor = session; }
  return session?.questions || (Array.isArray(window.questions) ? window.questions : []);
 };
 const markRail = () => { const list = qs(); document.querySelectorAll('#question-nav .question-link').forEach((b, i) => b.classList.toggle('q-done', !!list[i] && done.has(list[i].id))); };
 if ($('question-nav')) new MutationObserver(markRail).observe($('question-nav'), { childList: true });
 const currentQuestion = () => { const t = $('problem')?.querySelector('h1')?.textContent; return qs().find(q => q.title === t); };

 // Admin controls: tabs between the Codex practice run and Submissions. Only [hidden] changes,
 // so the typed Codex instructions, selections and runtime queue rows survive switching.
 const tablist = document.querySelector('#admin-controls .admin-tabs');
 const tabs = tablist ? [...tablist.querySelectorAll('[role="tab"]')] : [];
 if (tabs.length) {
  const select = (tab, focus) => {
   tabs.forEach(t => {
    const on = t === tab, panel = $(t.getAttribute('aria-controls'));
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    if (panel) panel.hidden = !on;
   });
   if (focus) tab.focus();
  };
  tablist.addEventListener('click', e => { const t = e.target.closest('[role="tab"]'); if (t) select(t); });
  tablist.addEventListener('keydown', e => {
   const i = tabs.indexOf(document.activeElement);
   const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
   if (i < 0 || to === undefined || e.altKey || e.ctrlKey || e.metaKey) return;
   e.preventDefault();
   select(tabs[(to + tabs.length) % tabs.length], true);
  });
  tablist.hidden = false;
  select(tabs.find(t => t.getAttribute('aria-selected') === 'true') || tabs[0]);
 }

 // Overview: move Coding rows from the single list app.js renders into the Coding section.
 const basics = $('task-list'), coding = $('task-list-coding');
 if (basics && coding) {
  new MutationObserver(() => {
   const rows = [...basics.children], list = qs();
   if (!list.length || rows.length !== list.length) return;
   rows.forEach((row, i) => { if (row.children[2]?.textContent === 'Passed') done.add(list[i].id); });
   coding.replaceChildren();
   rows.forEach((row, i) => { if (list[i].type === 'Coding') coding.append(row); });
  }).observe(basics, { childList: true });
 }

 // Top bar: show the timer as "27 min 58 sec" like the assessment.
 const timer = $('timer'), timerText = $('timer-text');
 if (timer && timerText) {
  const format = () => {
   const m = /^(\d+):(\d{2})$/.exec(timer.textContent.trim());
   if (!m) { timerText.textContent = ''; return; }
   const min = Number(m[1]), sec = Number(m[2]);
   timerText.textContent = min ? `${min} min ${sec} sec` : `${sec} sec`;
  };
  new MutationObserver(format).observe(timer, { childList: true, characterData: true, subtree: true });
  timer.closest('.timer-pill')?.classList.add('timer-formatted');
  format();
 }

 // Code editor: syntax colouring layer under a transparent textarea, plus the active-line band.
 const KW = new Set('async await break case catch class const continue default delete do else export extends finally for function if import in instanceof let new of return switch this throw try typeof var void while yield'.split(' '));
 const LIT = new Set(['true', 'false', 'null', 'undefined', 'NaN', 'Infinity']);
 const TOKEN = /(\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|('(?:[^'\\\n]|\\.)*'?|"(?:[^"\\\n]|\\.)*"?|`(?:[^`\\]|\\[\s\S])*`?)|(\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|([A-Za-z_$][\w$]*)|([()[\]{}])|(\s+)|([\s\S])/g;
 const paint = (pre, src) => {
  const frag = document.createDocumentFragment();
  let m, run = '', runCls = null;
  const push = (cls, text) => {
   if (cls === runCls) { run += text; return; }
   if (run) frag.append(runCls ? el('span', 'tk-' + runCls, run) : document.createTextNode(run));
   run = text; runCls = cls;
  };
  TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(src))) {
   let cls = '';
   if (m[1]) cls = 'c';
   else if (m[2]) cls = 's';
   else if (m[3]) cls = 'n';
   else if (m[4]) cls = KW.has(m[4]) ? 'k' : LIT.has(m[4]) ? 'l' : /^\s*\(/.test(src.slice(TOKEN.lastIndex, TOKEN.lastIndex + 40)) ? 'f' : 'v';
   else if (m[5]) cls = 'b';
   else if (m[7]) cls = 'p';
   push(cls, m[0]);
  }
  push(null, '\n');
  if (run) frag.append(document.createTextNode(run));
  pre.replaceChildren(frag);
 };
 const LINE = 20, PAD = 0;
 let placeBand = () => {}, resync = () => {};
 // Window resizes reflow the editor without a scroll event; realign the overlays from the
 // textarea's own scroll position. Text, selection and scroll are never written.
 const fit = typeof ResizeObserver === 'function' ? new ResizeObserver(() => resync()) : null;
 const attach = () => {
  const editor = $('code-editor'), shell = editor?.closest('.editor-shell');
  if (!editor || !shell || shell.classList.contains('hl-on')) return;
  const layer = el('pre', 'code-highlight'), band = el('div', 'line-band'), bandNum = el('span', 'line-band-num');
  layer.setAttribute('aria-hidden', 'true'); band.setAttribute('aria-hidden', 'true');
  band.append(bandNum);
  shell.insertBefore(layer, editor);
  shell.insertBefore(band, layer);
  shell.classList.add('hl-on');
  const nums = shell.querySelector('.line-numbers');
  const sync = resync = () => { layer.scrollTop = editor.scrollTop; layer.scrollLeft = editor.scrollLeft; if (nums) nums.scrollTop = editor.scrollTop; place(); };
  const place = placeBand = () => {
   const line = editor.value.slice(0, editor.selectionStart).split('\n').length;
   bandNum.textContent = String(line);
   band.style.transform = `translateY(${PAD + (line - 1) * LINE - editor.scrollTop}px)`;
  };
  editor.addEventListener('input', () => { paint(layer, editor.value); sync(); });
  editor.addEventListener('scroll', sync);
  paint(layer, editor.value);
  sync();
  if (fit) { fit.disconnect(); fit.observe(editor); }
 };

 // Editor status bar: cursor line and column.
 const pos = $('cursor-pos');
 const cursor = () => {
  const editor = $('code-editor');
  if (!editor || !pos) return;
  const lines = editor.value.slice(0, editor.selectionStart).split('\n');
  pos.textContent = `Ln ${lines.length}, Col ${lines[lines.length - 1].length + 1}`;
 };
 document.addEventListener('selectionchange', () => { if (document.activeElement?.id === 'code-editor') { cursor(); placeBand(); } });
 document.addEventListener('input', cursor, true);
 const area = $('answer-area');
 if (area) new MutationObserver(() => { attach(); cursor(); }).observe(area, { childList: true });

 // Test results: banner, test-case list and detail cards rendered from the grader's text.
 const output = $('test-output'), view = $('test-view'), panel = $('tests');
 let selected = 0, lastText = '';
 const show = (data) => {
  const body = panel?.querySelector('.tests-body');
  if (!view || !body) return;
  if (!data) { view.hidden = true; view.replaceChildren(); body.classList.remove('has-view'); return; }
  view.hidden = false; body.classList.add('has-view');
  const tabs = el('div', 'tr-tabs'); tabs.append(el('span', 'tr-tab', 'All Cases'));
  const banner = el('div', 'tr-banner'); banner.dataset.state = data.state;
  banner.append(el('span', 'tr-icon'), el('span', 'tr-banner-text', data.label));
  const parts = [tabs, banner];
  if (data.cases) {
   const wrap = el('div', 'tr-split'), list = el('div', 'tr-list'), detail = el('div', 'tr-detail');
   list.setAttribute('role', 'tablist'); list.setAttribute('aria-label', 'Test cases');
   data.cases.forEach((c, i) => {
    const b = el('button', 'tr-case'); b.type = 'button'; b.dataset.state = c.state;
    b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(i === selected));
    b.append(el('span', 'tr-icon'), el('span', 'tr-case-name', `Test Case ${i + 1}`));
    if (c.hidden) b.append(el('span', 'tr-lock', ''));
    b.addEventListener('click', () => { selected = i; show(data); });
    list.append(b);
   });
   const c = data.cases[selected] || data.cases[0];
   if (c) {
    detail.append(card('Compiler Message', c.message));
    if (c.hidden) detail.append(card('Hidden test case', 'Input and expected output are not shown for this case.'));
    else if (c.input !== undefined) { detail.append(card('Input (stdin)', c.input, true)); detail.append(card('Expected Output', c.expected, true)); }
   }
   wrap.append(list, detail); parts.push(wrap);
  } else if (data.detail) {
   const detail = el('div', 'tr-detail tr-detail-full');
   detail.append(card('Compiler Message', data.detail, true)); parts.push(detail);
  }
  view.replaceChildren(...parts);
 };
 const card = (title, text, mono) => {
  const box = el('section', 'tr-card');
  box.append(el('h4', 'tr-card-title', title));
  if (mono) {
   const pre = el('div', 'tr-card-code');
   String(text).split('\n').forEach((line, i) => { const row = el('div', 'tr-code-line'); row.append(el('span', 'tr-code-num', String(i + 1)), el('span', 'tr-code-text', line)); pre.append(row); });
   box.append(pre);
  } else box.append(el('p', 'tr-card-body', text));
  return box;
 };
 const fmt = v => typeof v === 'string' ? v : JSON.stringify(v);
 const render = () => {
  if (!output) return;
  const text = output.textContent, q = currentQuestion();
  if (q && /^(Test \d+: (passed|failed|error)\n?)+$/.test(text)) { if (/failed|error/.test(text)) done.delete(q.id); else done.add(q.id); markRail(); }
  else if (q && text === 'Answer correct.') { done.add(q.id); markRail(); }
  else if (q && text === 'Answer is not correct yet.') { done.delete(q.id); markRail(); }
  if (text === lastText && !view?.hidden) return;
  const fresh = text !== lastText; lastText = text;
  if (text.startsWith('Running')) {
   const n = q?.tests?.length || 0;
   show({ state: 'running', label: 'Running', cases: n ? Array.from({ length: n }, (_, i) => ({ state: 'running', hidden: i >= 2, message: 'Running' })) : null });
   return;
  }
  const lines = text.split('\n'), cases = lines.map(l => /^Test (\d+): (passed|failed|error)$/.exec(l)).filter(Boolean);
  if (cases.length && q?.tests) {
   const items = cases.map(([, n, r]) => {
    const i = Number(n) - 1, t = q.tests[i];
    return { state: r === 'passed' ? 'pass' : 'fail', hidden: i >= 2, message: r === 'passed' ? 'Success' : r === 'failed' ? 'Wrong Answer' : 'Runtime Error', input: t ? t.input.map(fmt).join('\n') : undefined, expected: t ? fmt(t.out) : undefined };
   });
   const passed = items.filter(c => c.state === 'pass').length;
   if (fresh) { const firstFail = items.findIndex(c => c.state === 'fail'); selected = firstFail < 0 ? 0 : firstFail; }
   show({ state: passed === items.length ? 'pass' : 'fail', label: passed === items.length ? 'All test cases passed' : passed ? `${passed}/${items.length} test cases passed` : 'All test cases failed', cases: items });
  }
  else if (text === 'Answer correct.') show({ state: 'pass', label: 'Answer correct' });
  else if (text === 'Answer is not correct yet.') show({ state: 'fail', label: 'Answer is not correct yet' });
  else if (q?.type === 'Coding' && text && !text.startsWith('Run ')) show({ state: 'fail', label: /timed out/i.test(text) ? 'Terminated due to timeout' : 'Compilation error', detail: text });
  else show(null);
 };
 if (output && view) new MutationObserver(render).observe(output, { childList: true, characterData: true, subtree: true });
 if (panel) panel.open = false;
 $('run-code')?.addEventListener('click', () => { if (panel) panel.open = true; });
})();
