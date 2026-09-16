// Runs in each fork before candidate modules load. The root runner owns reports.
import process from 'node:process'
if (process.getuid() === 0) {
  process.setgroups([])
  process.setgid(65534)
  process.setuid(65534)
}
if (process.getuid() !== 65534 || process.getgid() !== 65534) {
  throw new Error('test worker did not enter the unprivileged verifier identity')
}
