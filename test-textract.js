const fs = require('fs');
const dotenv = require('dotenv');
dotenv.config();

const { extractTextFromTextract } = require('./services/textractService');

async function test() {
  try {
    const buffer = fs.readFileSync('package.json'); // use package.json as a dummy file, textract might fail on pure json instead of image, but let's test if credentials work
    console.log("Testing textract...");
    const res = await extractTextFromTextract(buffer);
    console.log("SUCCESS:", res);
  } catch (e) {
    console.error("FAILED:", e.message);
  }
}

test();
