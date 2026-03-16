const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const repoRoot = path.resolve(__dirname, '..');
const reports = [
  'testing/reports/backend/report.html',
  'testing/reports/backend/junit.xml',
  'testing/reports/backend/report.json',
  'testing/reports/backend/coverage.xml',
  'testing/reports/frontend/playwright/index.html',
  'testing/reports/frontend/junit.xml',
  'testing/reports/frontend/report.json',
];

const existing = reports.filter((p) => fs.existsSync(path.join(repoRoot, p)));

if (!existing.length) {
  console.log('No reports found. Run tests first.');
  process.exit(0);
}

console.log('Available reports:');
for (const report of existing) {
  console.log(`- ${report}`);
}

if (process.env.OPEN_REPORTS === '1') {
  const htmlReports = existing.filter((p) => p.endsWith('.html'));
  for (const report of htmlReports) {
    const full = path.join(repoRoot, report);
    try {
      if (process.platform === 'darwin') execSync(`open "${full}"`);
      else if (process.platform === 'win32') execSync(`start "" "${full}"`);
      else execSync(`xdg-open "${full}"`);
    } catch (err) {
      console.log(`Unable to open ${report}.`);
    }
  }
}
