// Playwright function. Local page only; the native bridge is mocked.
async (page) => {
  const p = await page.context().newPage();
  try {
    await p.addInitScript(() => {
      const listeners = [];
      window.sent = [];
      window.deliver = data => listeners.forEach(listener => listener({ data }));
      window.chrome = { webview: {
        addEventListener: (_, listener) => listeners.push(listener),
        postMessage: message => window.sent.push(message)
      } };
    });
    await p.goto('http://127.0.0.1:48474/index.html');
    await p.evaluate(() => window.deliver({ kind: 'started', mode: 'codex', sessionId: 'b'.repeat(32), testId: 'practice-js-5', testVersion: 1, questionCount: 5 }));
    await p.locator('#task-list-coding .solve-button').first().click();
    const source = 'function summarize(numbers) { return {}; }';
    await p.locator('#code-editor').fill(source);
    await p.evaluate(() => window.deliver({ kind: 'stopped' }));
    const finals = await p.evaluate(() => window.sent.filter(m => m.command === 'finalized'));
    if (finals.length !== 1 || finals[0].sessionId !== 'b'.repeat(32) || !finals[0].answers.values.includes(source)) {
      throw new Error('Host stop lost or misbound answers');
    }
    await p.evaluate(() => window.deliver({ kind: 'stopped' }));
    if (await p.evaluate(() => window.sent.filter(m => m.command === 'finalized').length) !== 1) {
      throw new Error('Repeated stop finalized twice');
    }
    const before = await p.evaluate(() => window.sent.filter(m => m.command === 'events').length);
    await p.mouse.move(200, 200);
    await p.keyboard.press('a');
    await p.waitForTimeout(150);
    const after = await p.evaluate(() => window.sent.filter(m => m.command === 'events').length);
    if (before !== after) throw new Error('Capture continued after host stop');
    return { preserved: true, sessionBound: true, idempotent: true, captureStopped: true };
  } finally { await p.close(); }
}
