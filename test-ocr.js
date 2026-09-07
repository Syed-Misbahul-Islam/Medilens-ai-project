require('dotenv').config();
const Tesseract = require('tesseract.js');
const fs = require('fs');
const path = require('path');

// Use the most recent file in uploads
const testFile = path.join(__dirname, 'uploads', '1776364036376-214058457-1234.jpeg');

async function test() {
  console.log('Reading file from:', testFile);
  const buf = fs.readFileSync(testFile);
  console.log('Buffer size:', buf.length);

  try {
    const result = await Tesseract.recognize(buf, 'eng', {
      logger: m => { if (m.status === 'recognizing text') process.stdout.write('.'); }
    });
    console.log('\nExtracted text length:', result.data.text.length);
    console.log('First 500 chars:\n', result.data.text.slice(0, 500));
  } catch (e) {
    console.error('\nTesseract error:', e.message);
  }
}
test();
