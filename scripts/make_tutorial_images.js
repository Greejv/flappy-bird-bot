// Renders docs/tutorial-src/mockups.html -> docs/images/<id>.png (English)
// and docs/images/sk/<id>.png (Slovak: every element with data-sk gets that text).
// usage: node scripts/make_tutorial_images.js   (needs playwright + chromium)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

(async () => {
  const browser = await chromium.launch();
  for (const lang of ['en', 'sk']) {
    const outDir = lang === 'en' ? path.join(ROOT, 'docs', 'images') : path.join(ROOT, 'docs', 'images', lang);
    fs.mkdirSync(outDir, { recursive: true });
    const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 860, height: 900 } });
    await page.goto('file://' + path.join(ROOT, 'docs', 'tutorial-src', 'mockups.html'));
    await page.waitForLoadState('networkidle');
    if (lang !== 'en') {
      await page.evaluate((attr) => {
        document.documentElement.lang = attr.slice(5);
        for (const el of document.querySelectorAll('[' + attr + ']')) el.innerHTML = el.getAttribute(attr);
      }, 'data-' + lang);
    }
    for (const el of await page.$$('.fig')) {
      const id = await el.getAttribute('id');
      await el.screenshot({ path: path.join(outDir, id + '.png') });
    }
    console.log('rendered', lang, '->', path.relative(ROOT, outDir));
    await page.close();
  }
  await browser.close();
})();
