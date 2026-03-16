import { test, expect, Page } from '@playwright/test';

const DEBUG_E2E = process.env.DEBUG_E2E === '1';

test.beforeEach(async ({ page }) => {
  if (!DEBUG_E2E) return;
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.error('PAGEERROR', err.message);
  });
  page.on('console', (msg) => {
    // eslint-disable-next-line no-console
    console.log(`BROWSER ${msg.type()}:`, msg.text());
  });
  page.on('requestfailed', (req) => {
    // eslint-disable-next-line no-console
    console.log('REQUEST FAILED', req.url(), req.failure()?.errorText);
  });
});

const OWNER = { username: 'owner', password: 'Pass@1234' };
const LIMITED = { username: 'limited', password: 'Pass@1234' };

const DATA = {
  category: 'E2E Category',
  product: 'E2E Product',
  productCode: 'E2E-001',
  customer: 'E2E Customer',
  supplier: 'E2E Supplier',
};

async function closeWalkthroughIfPresent(page: Page) {
  const skip = page.getByText('Skip');
  try {
    await skip.waitFor({ state: 'visible', timeout: 5000 });
    await skip.click();
    return;
  } catch {}

  const next = page.getByRole('button', { name: 'Next' });
  if (await next.isVisible().catch(() => false)) {
    for (let i = 0; i < 3; i += 1) {
      await next.click();
      await page.waitForTimeout(250);
    }
    const getStarted = page.getByText('Get started');
    if (await getStarted.isVisible().catch(() => false)) {
      await getStarted.click();
    }
  }
}

async function login(page: Page, username: string, password: string) {
  await page.goto('/');
  await closeWalkthroughIfPresent(page);
  await page.getByTestId('login-username').waitFor({ state: 'visible', timeout: 15000 });
  await page.getByTestId('login-username').fill(username);
  await page.getByTestId('login-password').fill(password);
  await page.getByTestId('login-submit').click();
  await page.getByText('Workspace').waitFor({ timeout: 20000 });
  await closeWalkthroughIfPresent(page);
}

async function logout(page: Page) {
  await page.getByTestId('tab-more').click();
  await page.getByText('Log out').click();
}

async function gotoMore(page: Page) {
  await page.getByTestId('tab-more').click();
}

async function clickHeaderBack(page: Page) {
  const back = page.getByRole('button', { name: 'Back' });
  if (await back.isVisible().catch(() => false)) {
    await back.click();
    return;
  }
  await page.locator('[data-testid="header-back"]:visible').first().click();
}

async function clickNext(page: Page) {
  await page.getByRole('button', { name: 'Next' }).first().click();
}

async function selectOrCreateCustomer(page: Page, name: string, opts?: { gstin?: string }) {
  await page.getByTestId('sales-customer-search').click();
  await page.getByTestId('sales-customer-search').fill(name);
  const option = page.getByText(name).first();
  if (await option.isVisible().catch(() => false)) {
    await option.click();
    return;
  }
  await page.getByTestId('sales-new-customer-name').fill(name);
  await page.getByTestId('sales-new-customer-phone').fill('9000000000');
  if (opts?.gstin) {
    await page.getByTestId('sales-new-customer-gstin').fill(opts.gstin);
  }
  await page.getByTestId('sales-new-customer-address').fill('Main Street');
  await page.getByTestId('sales-new-customer-create').click();
}

test('@smoke login and permissions', async ({ page }) => {
  await login(page, LIMITED.username, LIMITED.password);

  await expect(page.locator('[data-testid="tab-inventory"]')).toBeVisible();
  await expect(page.locator('[data-testid="tab-sales"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="tab-purchase"]')).toHaveCount(0);

  await logout(page);

  await login(page, OWNER.username, OWNER.password);
  await expect(page.locator('[data-testid="tab-sales"]')).toBeVisible();
  await expect(page.locator('[data-testid="tab-purchase"]')).toBeVisible();
  await expect(page.locator('[data-testid="tab-inventory"]')).toBeVisible();
});

test('create masters, product, purchase, and inventory flow', async ({ page }) => {
  await login(page, OWNER.username, OWNER.password);

  // Create category
  await gotoMore(page);
  await page.getByText('Product Categories').click();
  await page.getByTestId('category-name').fill(DATA.category);
  await page.getByTestId('category-add').click();

  // Create product
  await clickHeaderBack(page);
  await page.getByText('Products').click();
  await page.getByText('Add Product').click();
  await page.getByTestId('product-name').fill(DATA.product);
  await page.getByTestId('product-code').fill(DATA.productCode);
  await page.getByTestId('product-category-search').fill(DATA.category);
  await page.getByText(DATA.category).first().click();
  await page.getByTestId('product-hsn').fill('1234');
  await page.getByTestId('product-selling-rate').fill('100');
  await page.getByTestId('product-purchase-rate').fill('80');
  await page.getByTestId('product-unit').fill('pcs');
  await page.getByTestId('product-tax-rate').fill('18');
  await page.getByTestId('product-save').click();
  await page.getByText('Products catalog').waitFor();

  // Create customer
  await clickHeaderBack(page);
  await page.getByText('Customers').click();
  await page.getByTestId('customer-name').fill(DATA.customer);
  await page.getByTestId('customer-phone').fill('9000000000');
  await page.getByTestId('customer-gstin').fill('22AAAAA0000A1Z5');
  await page.getByTestId('customer-add').click();

  // Create supplier
  await clickHeaderBack(page);
  await page.getByText('Suppliers').click();
  await page.getByTestId('supplier-name').fill(DATA.supplier);
  await page.getByTestId('supplier-phone').fill('9111111111');
  await page.getByTestId('supplier-gstin').fill('22AAAAA0000A1Z5');
  await page.getByTestId('supplier-address1').fill('Market Road');
  await page.getByTestId('supplier-add').click();

  // Purchase flow
  await page.getByTestId('tab-purchase').click();
  await page.getByRole('button', { name: 'New Purchase' }).click();

  await clickNext(page);
  await page.getByTestId('purchase-supplier-search').fill(DATA.supplier);
  await page.getByText(DATA.supplier).first().click();
  await clickNext(page);

  const qtyInput = page.getByPlaceholder('Qty').first();
  const priceInput = page.getByPlaceholder('Rate').first();
  await expect(qtyInput).toHaveValue('');
  await expect(priceInput).toHaveValue('');

  await page.getByPlaceholder('Product / Service').first().fill(DATA.product);
  await page.getByText(DATA.product).first().click();
  await qtyInput.fill('10');
  await priceInput.fill('80');

  await clickNext(page);
  await clickNext(page);

  await page.getByText('Credit / Unpaid').click();
  await page.getByText('Save bill').click();
  await page.getByText('Purchase workspace').waitFor();

  // Inventory category-first and back state
  await page.getByTestId('tab-inventory').click();
  await page.getByText(DATA.category).first().click();
  const search = page.getByPlaceholder('Search products');
  await search.fill('E2E');
  await page.getByText(DATA.product).first().click();
  await page.getByText('Stock moves').waitFor();
  await clickHeaderBack(page);
  await expect(search).toHaveValue('E2E');
});

test('sales GST/non-GST, custom GST, and quotation conversion', async ({ page }) => {
  await login(page, OWNER.username, OWNER.password);
  const seedCustomer = 'Sample Customer';
  const seedProduct = 'Sample Product';

  await page.getByTestId('tab-sales').click();
  await page.getByRole('button', { name: 'New Sale' }).click();

  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const dd = String(today.getDate()).padStart(2, '0');
  const todayStr = `${yyyy}-${mm}-${dd}`;
  await expect(page.getByTestId('sales-invoice-date')).toHaveValue(todayStr);

  // switch to Non-GST within the tax mode section
  const taxModeSection = page.getByText('Tax mode').locator('..');
  await taxModeSection.getByText('Non-GST', { exact: true }).click();

  await clickNext(page);
  await selectOrCreateCustomer(page, seedCustomer, { gstin: '22AAAAA0000A1Z5' });
  await clickNext(page);

  // HSN should be hidden for non-GST
  await expect(page.locator('[data-testid^="sales-line-0-hsn"]')).toHaveCount(0);

  // switch back to GST by clicking label (so we can test HSN + custom GST)
  await page.getByText('Back').click();
  await page.getByText('Back').click();
  await taxModeSection.getByText('GST', { exact: true }).click();

  await clickNext(page);
  await selectOrCreateCustomer(page, seedCustomer, { gstin: '22AAAAA0000A1Z5' });
  await clickNext(page);

  await expect(page.locator('[data-testid="sales-line-0-hsn"]')).toBeVisible();

  await page.getByPlaceholder('Product / Service').first().fill(seedProduct);
  await page.getByText(seedProduct).first().click();
  await page.getByPlaceholder('Qty').first().fill('2');
  await page.getByPlaceholder('Rate').first().fill('100');

  await clickNext(page);
  await page.getByTestId('sales-gst-custom').click();
  await page.getByTestId('sales-custom-sgst').fill('7');
  await page.getByTestId('sales-custom-cgst').fill('7');
  await page.getByText('Total GST: 14%').waitFor();

  await clickNext(page);
  await page.getByText('Cash').click();
  await page.getByTestId('sales-payment-note').fill('Paid in cash');
  await page.getByText('Save invoice').click();
  await page.getByText('Sales workspace').waitFor();

  // Quotation flow
  await page.getByText('Create quotation').click();
  await page.getByPlaceholder('Select customer').fill(seedCustomer);
  await page.getByText(seedCustomer).first().click();

  await page.getByPlaceholder('Product / Service').first().fill(seedProduct);
  await page.getByText(seedProduct).first().click();
  await page.getByPlaceholder('Qty').first().fill('1');
  await page.getByPlaceholder('Rate').first().fill('100');

  await page.getByText('Add Description Line').click();
  await page.getByPlaceholder('Description').first().fill('Delivery within 3 days');

  await page.getByTestId('quotation-save').click();
  await page.getByText('Sales workspace').waitFor();

  await page.getByText('Quotations').click();
  await page.getByText(/Q-/).first().click();

  const convert = page.getByText('Convert to Sale');
  await convert.click();

  // Alert handling for web: attempt to click dialog buttons if rendered, else accept dialog
  const gstButton = page.getByText('GST Sale');
  if (await gstButton.isVisible().catch(() => false)) {
    await gstButton.click();
  }

  await page.getByText('Sales detail').waitFor();
  await expect(page.getByText('Quotation:')).toBeVisible();
});
