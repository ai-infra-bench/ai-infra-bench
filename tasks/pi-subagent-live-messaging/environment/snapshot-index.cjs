// apt verifies Debian's signed snapshot metadata. Large content-addressed
// indexes can also be fetched from the official mirror using bounded ranges.
const http = require('node:http');
const { spawn } = require('node:child_process');
const { createHash } = require('node:crypto');
const fetch = require('/usr/local/lib/node_modules/npm/node_modules/make-fetch-happen');
const sizes = new Map();
const options = { proxy: process.env.HTTP_PROXY, timeout: 30000, retry: 1 };
async function ranged(url, size, hash) {
  const chunks = new Array(Math.ceil(size / 262144));
  let next = 0;
  await Promise.all(Array.from({ length: 8 }, async () => {
    while (next < chunks.length) {
      const index = next++;
      const start = index * 262144;
      const end = Math.min(size - 1, start + 262143);
      const response = await fetch(url, { ...options, headers: { Range: `bytes=${start}-${end}` } });
      if (response.status !== 206) throw new Error('Range unavailable');
      chunks[index] = await response.buffer();
      if (chunks[index].length !== end - start + 1) throw new Error('Incomplete range');
    }
  }));
  const data = Buffer.concat(chunks);
  if (createHash('sha256').update(data).digest('hex') !== hash) throw new Error('Index checksum mismatch');
  return data;
}
const server = http.createServer(async (request, response) => {
  try {
    const url = request.url;
    const hash = url.split('/').pop();
    let data;
    if (url.includes('/by-hash/SHA256/') && sizes.has(hash)) {
      const mirror = url.replace(/^http:\/\/snapshot.debian.org\/archive\/debian\/[^/]+\//, 'http://deb.debian.org/debian/');
      try { data = await ranged(mirror, sizes.get(hash), hash); } catch { /* use snapshot below */ }
    }
    if (!data) {
      const upstream = await fetch(url, options);
      if (!upstream.ok) { response.writeHead(upstream.status); response.end(); return; }
      data = await upstream.buffer();
    }
    if (url.endsWith('/InRelease')) {
      for (const match of data.toString().matchAll(/^ ([a-f0-9]{64})\s+(\d+) .+$/gm)) sizes.set(match[1], Number(match[2]));
    }
    response.writeHead(200, { 'Content-Length': data.length });
    response.end(data);
  } catch (error) { response.writeHead(502); response.end(String(error)); }
});
server.listen(0, '127.0.0.1', () => {
  const child = spawn('apt-get', ['-o', `Acquire::http::Proxy=http://127.0.0.1:${server.address().port}`, 'update'], { stdio: 'inherit' });
  child.on('close', code => { process.exitCode = code ?? 1; server.close(); server.closeAllConnections(); });
});
