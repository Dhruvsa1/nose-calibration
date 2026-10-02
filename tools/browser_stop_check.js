// Playwright function. Serve web/ at 127.0.0.1:48474; all native messages are mocked.
async (page) => {
  const p = await page.context().newPage();
  try {
    await p.addInitScript(() => {
      const listeners = [];
      window.__messages = [];
      window.chrome = window.chrome || {};
      window.chrome.webview = {
        addEventListener: (_, listener) => listeners.push(listener),
        postMessage: message => {
          window.__messages.push({ ...message, observedAt: performance.now() });
          if (message.command === 'start') setTimeout(() => listeners.forEach(listener => listener({ data: { kind: 'started', mode: 'verification', sessionId: 'a'.repeat(32) } })), 0);
        }
      };
    });
    await p.goto('http://127.0.0.1:48474/index.html');
    await p.click('label[for=consent]');
    await p.click('#start-session');
    await p.locator('#task-list-coding .solve-button').first().click();
    await p.fill('#code-editor', 'function summarize(numbers){while(true){}}');
    await p.click('#next');
    await p.fill('#code-editor', 'function makeReceipt(items){while(true){}}');
    await p.click('#back-overview');
    const immediate = await p.evaluate(() => {
      const begin = performance.now();
      document.getElementById('finish-session').click();
      document.getElementById('stop-recording').click();
      const finishes = window.__messages.filter(m => m.command === 'finish');
      const finalizes = window.__messages.filter(m => m.command === 'finalized');
      return { finishCount: finishes.length, delayMs: finishes[0]?.observedAt - begin, finalizedCount: finalizes.length, resultsVisible: !document.getElementById('results').hidden };
    });
    if (immediate.finishCount !== 1 || immediate.delayMs > 100 || immediate.finalizedCount !== 0 || !immediate.resultsVisible) throw new Error(JSON.stringify(immediate));
    const count = await p.evaluate(() => window.__messages.filter(m => m.command === 'events').flatMap(m => m.events).length);
    await p.mouse.move(200, 200);
    await p.keyboard.press('a');
    await p.waitForFunction(() => window.__messages.some(m => m.command === 'finalized'), { timeout: 6000 });
    const after = await p.evaluate(() => ({
      events: window.__messages.filter(m => m.command === 'events').flatMap(m => m.events).length,
      finishes: window.__messages.filter(m => m.command === 'finish').length,
      finalized: window.__messages.filter(m => m.command === 'finalized').map(m => ({ sessionId: m.sessionId, total: m.answers.total, score: m.answers.score }))
    }));
    if (after.events !== count || after.finishes !== 1 || after.finalized.length !== 1 || after.finalized[0].sessionId !== 'a'.repeat(32)) throw new Error(JSON.stringify(after));
    return { immediate, after, captureAfterFinish: false };
  } finally { await p.close(); }
}
