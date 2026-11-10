// Renders docs/tutorial-src/mockups.html -> docs/images/<id>.png
// usage: node scripts/make_tutorial_images.js   (needs playwright + chromium)
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 860, height: 900 } });
  await page.goto('file://' + path.resolve(__dirname, '..', 'docs', 'tutorial-src', 'mockups.html'));
  await page.waitForLoadState('networkidle');
  for (const el of await page.$$('.fig')) {
    const id = await el.getAttribute('id');
    await el.screenshot({ path: path.resolve(__dirname, '..', 'docs', 'images', id + '.png') });
    console.log('wrote', id);
  }
  await browser.close();
})();
