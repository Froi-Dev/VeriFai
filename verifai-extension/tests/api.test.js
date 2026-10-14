import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { detectText, verifyNews, detectImage, verifyNewsImage, getCurrentUser, loginUser, logoutUser } from '../public/api.js';

let memory;
let requests;
let responder;
globalThis.chrome = {
  storage: { local: {
    get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(k => [k, memory[k]])),
    set: async values => Object.assign(memory, values),
    remove: async keys => { for (const k of Array.isArray(keys) ? keys : [keys]) delete memory[k]; },
  } },
  runtime: { getPlatformInfo: async () => ({ os: 'win' }) },
};
globalThis.fetch = async (url, options) => {
  requests.push({ url, ...options });
  return responder(url, options);
};
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const textResult = { classification: 'Review recommended', confidence: .51, ai_probability: .51, human_probability: .49, score_interpretation: 'Review the context.', model_name: 'test-model' };
beforeEach(() => { memory = {}; requests = []; responder = () => json(textResult); });

test('cookie-authenticated text uses account route and preserves uncertain classification', async () => {
  const result = await detectText('This is a sufficiently long sample passage.');
  assert.match(requests[0].url, /detector\/text$/);
  assert.equal(requests[0].credentials, 'include');
  assert.equal(result.classification, 'Review recommended');
  assert.equal(result.aiProbability, 51);
  assert.equal(result.humanProbability, 49);
});

test('rejects text outside backend bounds before sending', async () => {
  for (const input of [undefined, 'short', 'x'.repeat(10001)]) await assert.rejects(detectText(input), /20 and 10,000/);
  assert.equal(requests.length, 0);
});

test('offline scans fail instead of producing a fabricated verdict', async () => {
  responder = () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(detectText('This is a sufficiently long sample passage.'), /Cannot reach VeriFai/);
});

test('validation and rate limit details remain readable', async () => {
  responder = () => json({ detail: [{ loc: ['body', 'text'], msg: 'Text is too long' }] }, 422);
  await assert.rejects(verifyNews('A valid claim'), /Text is too long/);
  responder = () => json({ detail: 'Rate limit exceeded. Try later.' }, 429);
  await assert.rejects(detectText('This is a sufficiently long sample passage.'), /Rate limit exceeded/);
});

test('expired bearer session refreshes once and retries with fresh token', async () => {
  memory.verifai_auth = { access_token: 'old', user: { name: 'Test' } };
  responder = (url, options) => url.endsWith('/auth/refresh')
    ? json({ access_token: 'new', user: { name: 'Test' } })
    : (options.headers.Authorization || options.headers.authorization) === 'Bearer new' ? json(textResult) : json({ detail: 'Expired' }, 401);
  await detectText('This is a sufficiently long sample passage.');
  assert.equal(requests.length, 3);
  assert.match(requests[0].url, /detector\/text$/);
  assert.equal(memory.verifai_auth.access_token, 'new');
});

test('temporary session server failure does not erase stored login', async () => {
  memory.verifai_auth = { access_token: 'old', user: { name: 'Test' } };
  responder = () => json({ detail: 'Unavailable' }, 503);
  assert.deepEqual(await getCurrentUser(), { name: 'Test' });
  assert.equal(memory.verifai_auth.access_token, 'old');
});

test('image uploads use multipart image field and preserve percent units', async () => {
  responder = () => json({ classification: 'Inconclusive', confidence: 0, ai_probability: 20, authentic_probability: 80 });
  const result = await detectImage('data:image/png;base64,aGVsbG8=');
  assert.equal(requests[0].body.get('image').type, 'image/png');
  assert.equal(result.confidence, 0);
  assert.equal(result.aiProbability, 20);
  assert.equal(result.classification, 'Inconclusive');
});

test('image authentication error is actionable', async () => {
  responder = () => json({ detail: 'Not authenticated' }, 401);
  await assert.rejects(detectImage(new Blob(['test'])), /Sign in/);
});

test('news uses account route and real response', async () => {
  responder = () => json({ verdict: 'UNVERIFIED', status: 'SEARCH_UNAVAILABLE', confidence: 0, explanation: 'Search unavailable' });
  const result = await verifyNews('A valid claim');
  assert.equal(result.verdict, 'UNVERIFIED');
  assert.equal(result.confidence, 0);
  assert.equal(result.status, 'SEARCH_UNAVAILABLE');
  responder = () => json({ detail: 'Not Found' }, 404);
  await assert.rejects(verifyNews('A valid claim'), /Restart the updated/);
});

test('news image retains OCR status and verdict', async () => {
  responder = () => json({ classification: 'UNVERIFIABLE', overall_verdict: 'UNVERIFIABLE', status: 'insufficient_text', confidence: 0 });
  const result = await verifyNewsImage(new Blob(['test']));
  assert.equal(result.status, 'insufficient_text');
  assert.equal(result.overallVerdict, 'UNVERIFIABLE');
});

test('login stores the backend token and sends cookie credentials', async () => {
  responder = () => json({ access_token: 'test-token', user: { name: 'Test' } });
  await loginUser(' test@example.com ', 'test-password');
  assert.equal(memory.verifai_auth.access_token, 'test-token');
  assert.equal(JSON.parse(requests[0].body).email, 'test@example.com');
  assert.equal(requests[0].credentials, 'include');
});


test('cookie-only login discovers the account and scans without guest consent', async () => {
  const user = { id: '7', name: 'Member' };
  responder = url => url.endsWith('/auth/login') ? json({ user }) : url.endsWith('/auth/me') ? json(user) : json(textResult);
  await loginUser('member@example.com', 'a-long-test-password');
  assert.equal(memory.verifai_auth.access_token, null);
  assert.deepEqual(await getCurrentUser(), user);
  await detectText('This is a sufficiently long sample passage.');
  await verifyNews('A claim to verify');
  assert.ok(requests.every(r => !r.url.includes('/guest/')));
  assert.ok(requests.every(r => r.credentials === 'include'));
});

test('web session is discovered without extension-local auth metadata', async () => {
  responder = () => json({ id: '8', name: 'Web member' });
  assert.deepEqual(await getCurrentUser(), { id: '8', name: 'Web member' });
  assert.match(requests[0].url, /auth\/me$/);
});

test('cookie refresh retries the account route and removes a stale bearer token', async () => {
  memory.verifai_auth = { access_token: 'stale' };
  let refreshed = false;
  responder = (url, options) => {
    if (url.endsWith('/auth/refresh')) { refreshed = true; return json({ user: { name: 'Member' } }); }
    if (!refreshed) return json({ detail: 'Expired' }, 401);
    assert.equal(new Headers(options.headers).get('Authorization'), null);
    return json(textResult);
  };
  await detectText('This is a sufficiently long sample passage.');
  assert.equal(requests.length, 3);
  assert.ok(requests.every(r => !r.url.includes('/guest/')));
});

test('signed-out scans request login and never fall back to guest routes', async () => {
  responder = () => json({ detail: 'Authentication required' }, 401);
  await assert.rejects(detectText('This is a sufficiently long sample passage.'), /Sign in/);
  assert.equal(requests.length, 2);
  assert.ok(requests.every(r => !r.url.includes('/guest/')));
});

test('cookie-only logout reaches the backend', async () => {
  memory.verifai_auth = { user: { name: 'Member' }, access_token: null };
  responder = () => json({ message: 'Signed out' });
  await logoutUser();
  assert.match(requests[0].url, /auth\/logout$/);
  assert.equal(requests[0].credentials, 'include');
  assert.equal(memory.verifai_auth, undefined);
});
