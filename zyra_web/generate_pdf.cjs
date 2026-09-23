const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  console.log('Launching browser...');
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  
  console.log('Navigating to localhost:5173...');
  await page.goto('http://localhost:5173', {waitUntil: 'networkidle2'});
  
  // Navigate to Learn view by evaluating script to set React state? No, just click the link.
  console.log('Clicking Learn link...');
  await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('.nav-links a'));
    const learnLink = links.find(a => a.textContent === 'Learn');
    if(learnLink) {
        learnLink.click();
    }
  });
  
  // Wait for the 'Read Whitepaper v1.0' button and click it
  console.log('Clicking Read Whitepaper button...');
  await page.waitForFunction(() => {
    return Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('Read Whitepaper'));
  });
  
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const readBtn = btns.find(b => b.textContent.includes('Read Whitepaper'));
    if(readBtn) readBtn.click();
  });
  
  // Wait for whitepaper-doc to render
  console.log('Waiting for whitepaper to render...');
  await page.waitForSelector('.whitepaper-doc');
  
  // Give it a tiny bit of time to settle fonts
  await new Promise(r => setTimeout(r, 1000));
  
  // We need to hide the PDF Viewer UI for the print if it's there
  await page.evaluate(() => {
     // The current index.css handles .no-print for the PDF toolbar and sidebar
     // Let's just make sure we print the page nicely
  });
  
  console.log('Generating PDF...');
  await page.pdf({
    path: 'public/zyra_whitepaper_v1.3.pdf',
    format: 'A4',
    printBackground: true,
    margin: { top: '0', right: '0', bottom: '0', left: '0' }
  });
  
  console.log('PDF generated at public/zyra_whitepaper_v1.3.pdf');
  await browser.close();
})();
