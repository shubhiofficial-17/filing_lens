import { expect, test } from '@playwright/test';

test('asks a question and shows a cited answer with its trace', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('status')).toContainText('API ready');
  await page.getByLabel('Ask about the 10-K filings').fill('Who was the CFO of Northwind Robotics in fiscal 2025?');
  await page.getByLabel('Strategy').selectOption('hybrid');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();

  const card = page.locator('article[data-strategy="hybrid"]');
  await expect(card.locator('.answer')).toContainText('Laura Benson');
  await card.locator('button.marker').first().click();
  await expect(card.locator('.sources li.active')).toContainText('NWRB 2025');
  await card.getByText(/^Trace/).click();
  await expect(card.locator('.trace')).toContainText('hybrid search');
});

test('compares every strategy side by side', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Summarise Solace Energy/ }).click();
  await page.getByRole('button', { name: 'Compare all strategies' }).click();

  const cards = page.locator('article[data-strategy]');
  await expect(cards).toHaveCount(7);
  await expect(page.locator('article[data-strategy="agentic"] .answer')).toContainText('2,311.4');
  // Guardrails: the agent drops the instruction planted in the filing; naive RAG repeats it.
  await expect(page.locator('article[data-strategy="agentic"] .answer')).not.toContainText(
    'most profitable company',
  );
  await expect(page.locator('article[data-strategy="naive"] .answer')).toContainText('most profitable company');
});

test('shows the evaluation report', async ({ page }) => {
  await page.goto('/evaluation');
  await expect(page.getByRole('heading', { name: 'How the strategies compare' })).toBeVisible();
  const rows = page.locator('section').first().locator('tbody tr');
  await expect(rows).toHaveCount(7);
  await expect(rows.first()).toContainText('Naive RAG');
});

test('browses a filing section', async ({ page }) => {
  await page.goto('/filings');
  await page.getByRole('button', { name: /NWRB fiscal 2024/ }).click();
  await page.getByRole('button', { name: /Item 1A/ }).click();
  await expect(page.locator('pre.text')).toContainText('EU Artificial Intelligence Act');
});
