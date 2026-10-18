// Run with PLAYWRIGHT_MODULE and MANAGEMENT_TEST_PYTHON pointing at local tools.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn, spawnSync} = require('node:child_process');
const {mkdtempSync, mkdirSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const {randomBytes} = require('node:crypto');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const temporary = mkdtempSync(path.join(tmpdir(), 'sasthotech-console-'));
  const python = process.env.MANAGEMENT_TEST_PYTHON || 'python3';
  const password = randomBytes(24).toString('base64url');
  const env = {...process.env, PYTHONPATH: root, MANAGEMENT_DATABASE: path.join(temporary, 'test.db'), SMOKE_PASSWORD: password};
  const seeded = spawnSync(python, ['-c', "import os; from app.database import migrate,connect_database; from app.security import create_user; p=os.environ['MANAGEMENT_DATABASE']; migrate(p); c=connect_database(p); d=c.__enter__(); create_user(d,'smoke-admin',os.environ['SMOKE_PASSWORD'],'admin'); c.__exit__(None,None,None)"], {env, encoding: 'utf8'});
  assert.equal(seeded.status, 0, seeded.stderr);
  delete env.SMOKE_PASSWORD;
  const server = spawn(python, ['-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '21124', '--no-access-log'], {env, stdio: 'pipe'});
  let browser;
  try {
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try { if ((await fetch('http://127.0.0.1:21124/readyz')).ok) { ready = true; break; } } catch (_) {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(ready, 'API did not become ready');
    browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE});
    const page = await browser.newPage({viewport: {width: 1280, height: 800}});
    const errors = []; page.on('pageerror', err => errors.push(err.message));
    page.on('dialog', dialog => dialog.accept());
    await page.goto('http://127.0.0.1:21124/console');
    await page.locator('#login-form').getByLabel('Username', {exact: true}).fill('smoke-admin');
    await page.locator('#login-form').getByLabel('Password', {exact: true}).fill(password);
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    await page.getByRole('button', {name: 'Add client', exact: true}).waitFor();
    await page.getByRole('button', {name: 'Add client', exact: true}).click();
    const editor = page.getByRole('dialog');
    await editor.getByLabel('RustDesk ID', {exact: true}).fill('123456789');
    await editor.getByLabel('Customer', {exact: true}).fill('Hospital East');
    await editor.getByLabel('Device', {exact: true}).fill('Reception');
    await editor.getByRole('button', {name: 'Save', exact: true}).click();
    await page.getByRole('cell', {name: 'Hospital East', exact: true}).waitFor();
    await page.getByRole('button', {name: 'Employees', exact: true}).click();
    await page.getByRole('button', {name: 'Add employee', exact: true}).click();
    await editor.getByLabel('Username', {exact: true}).fill('smoke-employee');
    await editor.getByLabel('Initial password', {exact: true}).fill(password);
    await editor.getByRole('button', {name: 'Save', exact: true}).click();
    await page.getByRole('cell', {name: 'smoke-employee', exact: true}).waitFor();
    await page.getByRole('button', {name: 'Policies', exact: true}).click();
    const company = page.locator('form').filter({has: page.getByRole('heading', {name: 'Company defaults'})});
    await company.getByLabel('File transfer', {exact: true}).uncheck();
    await company.getByRole('button', {name: 'Save policy'}).click();
    await page.getByText('Policy saved for new managed connections.', {exact: true}).waitFor();
    await page.getByLabel('Employee override', {exact: true}).selectOption({label: 'smoke-employee'});
    const employeePolicy = page.locator('form').filter({has: page.getByRole('heading', {name: 'Employee policy'})});
    await employeePolicy.getByLabel('Clipboard', {exact: true}).selectOption('false');
    await Promise.all([
      page.waitForResponse(response => response.url().includes('/policies/employees/') && response.request().method() === 'PUT'),
      employeePolicy.getByRole('button', {name: 'Save policy'}).click(),
    ]);
    await page.getByLabel('Employee override', {exact: true}).selectOption({label: 'smoke-admin'});
    await page.getByLabel('Employee override', {exact: true}).selectOption({label: 'smoke-employee'});
    assert.equal(await employeePolicy.getByLabel('Clipboard', {exact: true}).inputValue(), 'false');
    await page.getByRole('button', {name: 'Sign out'}).click();
    await page.locator('#login-form').getByLabel('Username', {exact: true}).fill('smoke-employee');
    await page.locator('#login-form').getByLabel('Password', {exact: true}).fill(password);
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    await page.getByRole('cell', {name: 'Hospital East', exact: true}).waitFor();
    assert.equal(await page.getByRole('button', {name: 'Employees', exact: true}).count(), 0);
    assert.equal(await page.getByRole('button', {name: 'Add client', exact: true}).count(), 0);
    const output = path.join(temporary, 'screenshots'); mkdirSync(output);
    await page.screenshot({path: path.join(output, 'desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    await page.screenshot({path: path.join(output, 'mobile.png'), fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.getByRole('button', {name: 'Sessions', exact: true}).click();
    await page.getByText('No records found.', {exact: true}).waitFor();
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({status: 'passed', scenarios: ['admin login', 'client creation', 'employee creation', 'policy change', 'employee directory', 'role isolation', 'desktop/mobile layout', 'empty reports'], screenshots: output}));
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => server.once('exit', resolve));
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
