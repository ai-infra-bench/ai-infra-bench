// Fetch the exact snapshot-selected package bytes from Debian's faster mirror.
// apt still chooses versions from the frozen snapshot and verifies its hashes.
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const fetch = require('/usr/local/lib/node_modules/npm/node_modules/make-fetch-happen');
const packages = process.argv.slice(2);
const listing = execFileSync('apt-get', ['--print-uris', '-y', '--no-install-recommends',
  '-o', 'Acquire::ForceHash=sha256', 'install', ...packages], { encoding: 'utf8' });
const entries = [...listing.matchAll(/^'([^']+)' (\S+) (\d+) (\S+)$/gm)];
async function download(entry) {
  const [, snapshot, name, size, digest] = entry;
  const mirror = snapshot.replace(/^http:\/\/snapshot.debian.org\/archive\/debian\/[^/]+\//,
    'http://deb.debian.org/debian/');
  const [algorithm, expected] = digest.split(':');
  for (const url of [mirror, snapshot]) {
    try {
      const response = await fetch(url, { proxy: process.env.HTTP_PROXY, timeout: 30000, retry: 1 });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.buffer();
      const hash = createHash(algorithm.toLowerCase().replace('sum', '')).update(data).digest('hex');
      if (data.length !== Number(size) || hash !== expected) throw new Error('package checksum mismatch');
      fs.writeFileSync(`/var/cache/apt/archives/${name}`, data);
      console.log(`Verified ${name}`);
      return;
    } catch (error) {
      if (url === snapshot) throw error;
    }
  }
}
let next = 0;
Promise.all(Array.from({ length: 6 }, async () => {
  while (next < entries.length) await download(entries[next++]);
})).catch(error => { console.error(error); process.exitCode = 1; });
