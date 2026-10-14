import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
let memory = {};
let listener;
let responder;
globalThis.chrome = {
  storage: { local: {
    get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(k => [k, memory[k]])),
    set: async values => Object.assign(memory, values),
    remove: async keys => { for (const k of Array.isArray(keys) ? keys : [keys]) delete memory[k]; },
  } },
  runtime: { id: 'test-extension', onMessage: { addListener: fn => { listener = fn; } }, getPlatformInfo: async () => ({ os: 'win' }) },
  commands: { onCommand: { addListener() {} } },
};
globalThis.fetch = async (url, options) => responder(url, options);
await import('../public/background.js');
const send = message => new Promise(resolve => listener(message, {}, resolve));
const json = (body, status = 200) => new Response(JSON.stringify(body), { status });
const trustedSender = { id: 'test-extension', tab: { id: 1 }, frameId: 0, url: 'http://localhost:5173/dashboard' };
test('dashboard connection validates and saves the account token', async () => {
  responder = (url, options) => {
    assert.ok(url.endsWith('/auth/me'));
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    return json({ id: 7 });
  };
  const result = await new Promise(resolve => listener({ type: 'CONNECT_ACCOUNT', token: 'test-token' }, trustedSender, resolve));
  assert.equal(result.ok, true);
  assert.equal(memory.verifai_auth.access_token, 'test-token');
});
test('dashboard connection rejects untrusted senders', () => {
  responder = () => { throw new Error('Unexpected request'); };
  for (const change of [{ url: 'https://example.com/' }, { frameId: 1 }, { id: 'other-extension' }]) {
    assert.equal(listener({ type: 'CONNECT_ACCOUNT', token: 'test-token' }, { ...trustedSender, ...change }, () => assert.fail()), false);
  }
  assert.equal(memory.verifai_auth, undefined);
});
test('dashboard connection refuses an invalid account token', async () => {
  responder = () => json({}, 401);
  const result = await new Promise(resolve => listener({ type: 'CONNECT_ACCOUNT', token: 'invalid' }, trustedSender, resolve));
  assert.equal(result.ok, false);
  assert.equal(memory.verifai_auth, undefined);
});
beforeEach(() => { memory = {}; responder = () => json({ classification: 'Likely human-written', confidence: .9, ai_probability: .1, human_probability: .9 }); });

test('worker returns real results and preserves simultaneous history writes', async () => {
  const results = await Promise.all([
    send({ type: 'ANALYZE_TEXT', text: 'This is a sufficiently long first text.' }),
    send({ type: 'ANALYZE_TEXT', text: 'This is a sufficiently long second text.' }),
  ]);
  assert.equal(results[0].confidence, 90);
  assert.equal(memory.verifai_scan_history.length, 2);
  assert.notEqual(memory.verifai_scan_history[0].id, memory.verifai_scan_history[1].id);
});

test('worker reports network error without saving an invented result', async () => {
  responder = () => { throw new TypeError('Network failure'); };
  const result = await send({ type: 'ANALYZE_TEXT', text: 'This is a sufficiently long sample passage.' });
  assert.match(result.error, /Cannot reach/);
  assert.equal(memory.verifai_scan_history, undefined);
});

test('image failure is an error state, never an authentic result', async () => {
  responder = () => json({ detail: 'Vision model unavailable' }, 503);
  const result = await send({ type: 'ANALYZE_IMAGE', croppedImage: 'data:image/png;base64,aGVsbG8=', mode: 'media' });
  assert.match(result.error, /Vision model unavailable/);
  assert.equal(memory.verifai_status, 'error');
  assert.equal(result.isAIGenerated, undefined);
  assert.equal(memory.verifai_scan_history, undefined);
});

test('cropper completion returns image result and saves it for popup history', async () => {
  responder = () => json({ classification: 'Inconclusive', confidence: 22, ai_probability: 48, authentic_probability: 52, summary: 'Needs review' });
  const response = await send({ type: 'CROP_COMPLETE', croppedImage: 'data:image/png;base64,aGVsbG8=', mode: 'media' });
  assert.equal(response.results.label, 'Inconclusive');
  assert.equal(memory.verifai_status, 'done');
  assert.equal(memory.verifai_scan_history[0].result.summary, 'Needs review');
});

test('text inference can exceed the old six-second cutoff', async () => {
  responder = async () => {
    await new Promise(resolve => setTimeout(resolve, 6100));
    return json({ classification: 'Review recommended', confidence: .55, ai_probability: .55, human_probability: .45 });
  };
  const result = await send({ type: 'ANALYZE_TEXT', text: 'This is a sufficiently long sample passage.' });
  assert.equal(result.classification, 'Review recommended');
  assert.equal(result.confidence, 55);
});
