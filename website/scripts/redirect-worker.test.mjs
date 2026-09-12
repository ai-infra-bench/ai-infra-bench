import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../../cloudflare/redirect-worker.js';

const originalFetch = globalThis.fetch;

test.afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('redirects supported legacy HTML routes with a permanent redirect', async () => {
  globalThis.fetch = async () => new Response('origin');

  for (const [legacy, clean] of [
    ['/index.html', '/'],
    ['/leaderboard.html', '/leaderboard'],
    ['/tasks.html', '/tasks'],
    ['/tasks/vllm-asr-chunk-spacing.html', '/tasks/vllm-asr-chunk-spacing'],
  ]) {
    const response = await worker.fetch(new Request(`https://infrabench.ai${legacy}?source=legacy`));
    assert.equal(response.status, 301);
    assert.equal(response.headers.get('location'), `https://infrabench.ai${clean}?source=legacy`);
  }
});

test('passes clean routes and unsupported HTML files through to GitHub Pages', async () => {
  let fetchedRequest;
  globalThis.fetch = async (request) => {
    fetchedRequest = request;
    return new Response('origin', { status: 200 });
  };

  const response = await worker.fetch(new Request('https://infrabench.ai/tasks'));
  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'origin');
  assert.equal(fetchedRequest.url, 'https://infrabench.ai/tasks');

  const unsupported = await worker.fetch(new Request('https://infrabench.ai/assets/app.html'));
  assert.equal(unsupported.status, 200);
});
