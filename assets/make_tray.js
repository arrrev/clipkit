// Generates assets/trayTemplate.png (18x18 black template image of a ✂ scissors glyph).
// Run once with Electron available:  npx electron assets/make_tray.js
// (Falls back gracefully: if this file is never run, main.js renders the ✂ emoji as the tray title.)
const { app, nativeImage } = require('electron');
const fs = require('fs');
const path = require('path');

app.whenReady().then(() => {
  // A simple 2x scissors drawn into an offscreen canvas via an SVG data URL.
  const svg = `
  <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">
    <g fill="none" stroke="black" stroke-width="2.4" stroke-linecap="round">
      <circle cx="9" cy="25" r="4"/>
      <circle cx="9" cy="11" r="4"/>
      <line x1="12.5" y1="13" x2="30" y2="26"/>
      <line x1="12.5" y1="23" x2="30" y2="10"/>
    </g>
  </svg>`;
  const dataUrl = 'data:image/svg+xml;base64,' + Buffer.from(svg).toString('base64');
  const img = nativeImage.createFromDataURL(dataUrl);
  const out = path.join(__dirname, 'trayTemplate.png');
  fs.writeFileSync(out, img.toPNG());
  console.log('Wrote', out);
  app.quit();
});
