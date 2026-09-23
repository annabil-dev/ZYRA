const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

(async () => {
  console.log('Launching browser...');
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  
  const filePath = `file://${path.resolve(__dirname, 'whitepaper_source.html')}`;
  console.log(`Navigating to ${filePath}...`);
  
  try {
    await page.goto(filePath, {waitUntil: 'networkidle2', timeout: 15000});
  } catch (e) {
    console.log('Navigation timeout hit, proceeding to PDF generation anyway...');
  }
  
  // Give it a bit of time to settle fonts
  await new Promise(r => setTimeout(r, 2000));
  
  console.log('Generating PDF...');
  await page.pdf({
    path: 'public/zyra_whitepaper_v2.0.pdf',
    format: 'A4',
    printBackground: true,
    timeout: 0,
    margin: { top: '0', right: '0', bottom: '0', left: '0' }
  });
  
  console.log('PDF generated at public/zyra_whitepaper_v2.0.pdf');
  await browser.close();
})();
