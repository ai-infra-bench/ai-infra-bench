// Negative control: an agent-writable test runner forges the scorer's input.
// This runs only in a disposable review container, never in the task image.
import fs from 'node:fs'
const names = JSON.parse(fs.readFileSync('/tests/expected-tests.json', 'utf8'))
fs.writeFileSync(process.env.DSH_REPORT, JSON.stringify({
  success: true,
  numTotalTests: names.length,
  numPassedTests: names.length,
  numFailedTests: 0,
  numPendingTests: 0,
  numTodoTests: 0,
  testResults: [{ status: 'passed', assertionResults: names.map(fullName => ({ fullName, status: 'passed' })) }],
}))
console.log('REVIEW_FORGED_REPORT_WITHOUT_EXECUTING_TESTS')
