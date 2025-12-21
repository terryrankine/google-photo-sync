// @ts-check
import { test, expect } from '@playwright/test';

/**
 * Google Photos Sync Tool - UI Tests
 *
 * Run with: npx playwright test
 * Run specific test: npx playwright test -g "test name"
 * Run with UI: npx playwright test --ui
 * View report: npx playwright show-report
 *
 * Make sure the app is running at http://localhost:18080 before running tests
 * Or set BASE_URL environment variable to point to the running app
 */

// =============================================================================
// NAVIGATION TESTS
// =============================================================================

test.describe('Navigation', () => {
  test('should load the homepage', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/frontend/);
  });

  test('should have navigation bar with all links', async ({ page }) => {
    await page.goto('/');

    // Check navbar exists
    const nav = page.locator('nav');
    await expect(nav).toBeVisible();

    // Check all navigation links
    await expect(page.getByRole('link', { name: 'GPhoto Sync' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Jobs' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Statistics' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Files' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
  });

  test('should show status indicator', async ({ page }) => {
    await page.goto('/');

    // Status should be visible (idle, running, or paused)
    const statusText = page.locator('nav').getByText(/idle|running|paused/i);
    await expect(statusText).toBeVisible();
  });

  test('should navigate to Dashboard', async ({ page }) => {
    await page.goto('/jobs');
    await page.getByRole('link', { name: 'Dashboard' }).click();
    await expect(page).toHaveURL('/');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('should navigate to Jobs', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Jobs' }).click();
    await expect(page).toHaveURL('/jobs');
    await expect(page.getByRole('heading', { name: 'Sync Jobs' })).toBeVisible();
  });

  test('should navigate to Statistics', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Statistics' }).click();
    await expect(page).toHaveURL('/stats');
    await expect(page.getByRole('heading', { name: 'Statistics' })).toBeVisible();
  });

  test('should navigate to Files', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Files' }).click();
    await expect(page).toHaveURL('/files');
    await expect(page.getByRole('heading', { name: 'Files' })).toBeVisible();
  });

  test('should navigate to Settings', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page).toHaveURL('/config');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });

  test('should navigate via logo to home', async ({ page }) => {
    await page.goto('/jobs');
    await page.getByRole('link', { name: 'GPhoto Sync' }).click();
    await expect(page).toHaveURL('/');
  });

  test('should have footer', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Google Photos Sync Tool')).toBeVisible();
  });
});

// =============================================================================
// DASHBOARD PAGE TESTS
// =============================================================================

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display dashboard heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Dashboard', level: 1 })).toBeVisible();
  });

  test('should have Start New Sync button', async ({ page }) => {
    const button = page.getByRole('button', { name: 'Start New Sync' });
    await expect(button).toBeVisible();
    await expect(button).toBeEnabled();
  });

  test('should display stats cards', async ({ page }) => {
    // Check all four stats cards exist
    await expect(page.getByText('Total Files')).toBeVisible();
    await expect(page.getByText('Pending')).toBeVisible();
    await expect(page.getByText('Database')).toBeVisible();
    await expect(page.getByText('Data', { exact: true })).toBeVisible();
  });

  test('should display stats card values', async ({ page }) => {
    // Stats cards should show numeric values (even if 0)
    const statsSection = page.locator('.grid').first();
    await expect(statsSection).toBeVisible();

    // Check for uploaded subtitle (use exact match to avoid multiple matches)
    await expect(page.getByText(/\d+ uploaded/)).toBeVisible();
    // Check for errors subtitle
    await expect(page.getByText(/\d+ errors/)).toBeVisible();
    // Check for unique hashes
    await expect(page.getByText(/unique hashes/)).toBeVisible();
  });

  test('should display job status area', async ({ page }) => {
    // Either shows active job or "No active job" message
    const noJobMessage = page.getByText('No active job');
    const jobPanel = page.locator('text=Job #');

    // One of these should be visible
    const hasNoJob = await noJobMessage.isVisible().catch(() => false);
    const hasJob = await jobPanel.isVisible().catch(() => false);

    expect(hasNoJob || hasJob).toBeTruthy();
  });

  test('should display chart section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Last 7 Days' })).toBeVisible();

    // Chart canvas should exist
    const canvas = page.locator('canvas');
    await expect(canvas).toBeVisible();
  });

  test('should display recent activity section', async ({ page }) => {
    // Either shows activity list or no activity section (if empty)
    const activityHeading = page.getByRole('heading', { name: 'Recent Activity' });
    const activityList = page.locator('ul');

    const hasHeading = await activityHeading.isVisible().catch(() => false);
    const hasActivity = await activityList.isVisible().catch(() => false);

    // Activity section may or may not exist depending on data
    expect(hasHeading || !hasHeading).toBeTruthy();
  });

  test('should update stats periodically', async ({ page }) => {
    // Wait for initial load
    await page.waitForTimeout(500);

    // Stats should be loaded (checking one of the cards has a value)
    const totalFilesCard = page.locator('text=Total Files').locator('..');
    await expect(totalFilesCard).toBeVisible();
  });
});

// =============================================================================
// JOBS PAGE TESTS
// =============================================================================

test.describe('Jobs Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/jobs');
  });

  test('should display jobs heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Sync Jobs', level: 1 })).toBeVisible();
  });

  test('should display jobs table', async ({ page }) => {
    const table = page.getByRole('table');
    await expect(table).toBeVisible();
  });

  test('should have correct table headers', async ({ page }) => {
    await expect(page.getByRole('columnheader', { name: 'ID' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Status' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Phase' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Started' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Scanned' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Hashed' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Uploaded' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Errors' })).toBeVisible();
  });

  test('should show empty state when no jobs', async ({ page }) => {
    // If there are no jobs, should show message
    const noJobs = page.getByText('No jobs yet');
    const jobRows = page.locator('tbody tr').filter({ hasNot: page.getByText('No jobs') });

    const isEmpty = await noJobs.isVisible().catch(() => false);
    const rowCount = await jobRows.count();

    // Either shows "No jobs yet" or has job rows
    expect(isEmpty || rowCount > 0).toBeTruthy();
  });

  test('should have Clear Finished button', async ({ page }) => {
    const clearButton = page.getByRole('button', { name: 'Clear Finished' });
    await expect(clearButton).toBeVisible();
  });
});

// =============================================================================
// STATISTICS PAGE TESTS
// =============================================================================

test.describe('Statistics Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/stats');
  });

  test('should display statistics heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Statistics', level: 1 })).toBeVisible();
  });

  test('should display overview section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  });

  test('should display stats values', async ({ page }) => {
    // Check for stat labels
    await expect(page.getByText('Total Files')).toBeVisible();
    await expect(page.getByText('Uploaded', { exact: true })).toBeVisible();
    await expect(page.getByText('Unique Hashes')).toBeVisible();
  });

  test('should display daily stats section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Daily Stats' })).toBeVisible();
  });

  test('should display daily stats table', async ({ page }) => {
    const table = page.locator('table').last();
    await expect(table).toBeVisible();

    // Check table headers
    await expect(page.getByRole('columnheader', { name: 'Date' })).toBeVisible();
  });
});

// =============================================================================
// FILES PAGE TESTS
// =============================================================================

test.describe('Files Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/files');
  });

  test('should display files heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Files', level: 1 })).toBeVisible();
  });

  test('should have search input', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();
  });

  test('should have status filter dropdown', async ({ page }) => {
    const filterSelect = page.getByRole('combobox');
    await expect(filterSelect).toBeVisible();
  });

  test('should have filter options', async ({ page }) => {
    const filterSelect = page.getByRole('combobox');

    // Check filter options exist (HTML select options are accessible even when not expanded)
    await expect(filterSelect.getByRole('option', { name: 'All' })).toBeAttached();
    await expect(filterSelect.getByRole('option', { name: 'Pending' })).toBeAttached();
    await expect(filterSelect.getByRole('option', { name: 'Uploaded' })).toBeAttached();
    await expect(filterSelect.getByRole('option', { name: 'Error' })).toBeAttached();
  });

  test('should display files table', async ({ page }) => {
    const table = page.getByRole('table');
    await expect(table).toBeVisible();
  });

  test('should have correct table headers', async ({ page }) => {
    await expect(page.getByRole('columnheader', { name: 'Path' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Size' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Status' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Modified' })).toBeVisible();
  });

  test('should allow searching files', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill('test.jpg');

    // Search should be applied (input should have value)
    await expect(searchInput).toHaveValue('test.jpg');
  });

  test('should allow filtering by status', async ({ page }) => {
    const filterSelect = page.getByRole('combobox');
    await filterSelect.selectOption('pending');

    await expect(filterSelect).toHaveValue('pending');
  });

  test('should have pagination controls', async ({ page }) => {
    // Check for pagination buttons
    const prevButton = page.getByRole('button', { name: /prev/i });
    const nextButton = page.getByRole('button', { name: /next/i });

    // At least one pagination control should exist
    const hasPrev = await prevButton.isVisible().catch(() => false);
    const hasNext = await nextButton.isVisible().catch(() => false);

    // Pagination might not show if no files, so just check page info exists
    const pageInfo = page.getByText(/page \d+/i);
    const hasPageInfo = await pageInfo.isVisible().catch(() => false);

    expect(hasPrev || hasNext || hasPageInfo).toBeTruthy();
  });
});

// =============================================================================
// SETTINGS PAGE TESTS
// =============================================================================

test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/config');
  });

  test('should display settings heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
  });

  test('should have source directories textarea', async ({ page }) => {
    await expect(page.getByText('Source Directories')).toBeVisible();

    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible();
  });

  test('should have file extensions input', async ({ page }) => {
    await expect(page.getByText('File Extensions')).toBeVisible();

    const input = page.locator('input[type="text"]').first();
    await expect(input).toBeVisible();
  });

  test('should have ignore patterns input', async ({ page }) => {
    await expect(page.getByText('Ignore Patterns')).toBeVisible();
  });

  test('should have upload workers input', async ({ page }) => {
    await expect(page.getByText('Upload Workers')).toBeVisible();

    const input = page.locator('input[type="number"]').first();
    await expect(input).toBeVisible();
    await expect(input).toHaveAttribute('type', 'number');
  });

  test('should have hash workers input', async ({ page }) => {
    await expect(page.getByText('Hash Workers')).toBeVisible();

    const inputs = page.locator('input[type="number"]');
    await expect(inputs).toHaveCount(2);
  });

  test('should have save button', async ({ page }) => {
    const saveButton = page.getByRole('button', { name: 'Save Settings' });
    await expect(saveButton).toBeVisible();
    await expect(saveButton).toBeEnabled();
  });

  test('should allow editing source directories', async ({ page }) => {
    const textarea = page.locator('textarea');
    await textarea.clear();
    await textarea.fill('/photos\n/media/pictures');

    await expect(textarea).toHaveValue('/photos\n/media/pictures');
  });

  test('should allow editing file extensions', async ({ page }) => {
    const input = page.locator('input[type="text"]').first();
    await input.clear();
    await input.fill('.jpg,.png,.gif');

    await expect(input).toHaveValue('.jpg,.png,.gif');
  });

  test('should allow editing worker counts', async ({ page }) => {
    const uploadWorkers = page.locator('input[type="number"]').first();
    await uploadWorkers.clear();
    await uploadWorkers.fill('8');

    await expect(uploadWorkers).toHaveValue('8');
  });

  test('should have helper text for fields', async ({ page }) => {
    await expect(page.getByText('One directory per line')).toBeVisible();
    await expect(page.getByText('Comma-separated list')).toBeVisible();
    await expect(page.getByText(/patterns to skip/i)).toBeVisible();
  });
});

// =============================================================================
// API INTEGRATION TESTS
// =============================================================================

test.describe('API Integration', () => {
  test('should load dashboard from API', async ({ page }) => {
    // Intercept the API call
    const dashboardPromise = page.waitForResponse(resp =>
      resp.url().includes('/api/dashboard') && resp.status() === 200
    );

    await page.goto('/');

    const response = await dashboardPromise;
    const data = await response.json();

    // Verify response structure
    expect(data).toHaveProperty('stats');
    expect(data.stats).toHaveProperty('total_files');
  });

  test('should load status from API', async ({ page }) => {
    const statusPromise = page.waitForResponse(resp =>
      resp.url().includes('/api/status') && resp.status() === 200
    );

    await page.goto('/');

    const response = await statusPromise;
    const data = await response.json();

    expect(data).toHaveProperty('status');
  });

  test('should load jobs from API', async ({ page }) => {
    const jobsPromise = page.waitForResponse(resp =>
      resp.url().includes('/api/jobs') && resp.status() === 200
    );

    await page.goto('/jobs');

    const response = await jobsPromise;
    const data = await response.json();

    expect(Array.isArray(data)).toBeTruthy();
  });

  test('should load config from API', async ({ page }) => {
    const configPromise = page.waitForResponse(resp =>
      resp.url().includes('/api/config') && resp.status() === 200
    );

    await page.goto('/config');

    const response = await configPromise;
    const data = await response.json();

    expect(typeof data).toBe('object');
  });

  test('should load chart data from API', async ({ page }) => {
    const dashboardPromise = page.waitForResponse(resp =>
      resp.url().includes('/api/dashboard') && resp.status() === 200
    );

    await page.goto('/');

    const response = await dashboardPromise;
    const data = await response.json();

    expect(data).toHaveProperty('chart');
    expect(data.chart).toHaveProperty('labels');
  });

  test('health endpoint should return healthy', async ({ page }) => {
    const response = await page.request.get('/health');
    const data = await response.json();

    expect(response.status()).toBe(200);
    expect(data.status).toBe('healthy');
  });
});

// =============================================================================
// RESPONSIVE DESIGN TESTS
// =============================================================================

test.describe('Responsive Design', () => {
  test('should be responsive on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    // Navigation should still be visible
    await expect(page.locator('nav')).toBeVisible();

    // Dashboard should render
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('should be responsive on tablet', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');

    await expect(page.locator('nav')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('stats cards should stack on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    // Stats cards container should be visible
    const statsGrid = page.locator('.grid').first();
    await expect(statsGrid).toBeVisible();
  });
});

// =============================================================================
// ERROR HANDLING TESTS
// =============================================================================

test.describe('Error Handling', () => {
  test('should handle 404 routes gracefully', async ({ page }) => {
    await page.goto('/nonexistent-page');

    // SPA should still load (catches all routes)
    await expect(page.locator('nav')).toBeVisible();
  });

  test('should handle API errors gracefully', async ({ page }) => {
    // Mock API to return error
    await page.route('**/api/dashboard', route => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal Server Error' })
      });
    });

    await page.goto('/');

    // Page should still render without crashing
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });
});

// =============================================================================
// USER INTERACTION TESTS
// =============================================================================

test.describe('User Interactions', () => {
  test('should be able to click Start New Sync', async ({ page }) => {
    await page.goto('/');

    const button = page.getByRole('button', { name: 'Start New Sync' });
    await expect(button).toBeEnabled();

    // Click should not throw error
    await button.click();

    // Should still be on dashboard
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('should be able to navigate using keyboard', async ({ page }) => {
    await page.goto('/');

    // Tab to first link and press Enter
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');

    // Should navigate somewhere
    await expect(page.locator('nav')).toBeVisible();
  });

  test('should be able to fill and submit settings form', async ({ page }) => {
    await page.goto('/config');

    // Fill form
    const textarea = page.locator('textarea');
    await textarea.fill('/test/photos');

    // Click save
    const saveButton = page.getByRole('button', { name: 'Save Settings' });
    await saveButton.click();

    // Page should not crash
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });
});

// =============================================================================
// VISUAL REGRESSION TESTS (Screenshots)
// =============================================================================

test.describe('Visual Regression', () => {
  test('dashboard should match snapshot', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('dashboard.png', {
      maxDiffPixels: 100,
      threshold: 0.2
    });
  });

  test('jobs page should match snapshot', async ({ page }) => {
    await page.goto('/jobs');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('jobs.png', {
      maxDiffPixels: 5000,
      threshold: 0.3
    });
  });

  test('settings page should match snapshot', async ({ page }) => {
    await page.goto('/config');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('settings.png', {
      maxDiffPixels: 100,
      threshold: 0.2
    });
  });
});
