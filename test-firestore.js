require('dotenv').config();
const { db } = require('./config/firebase');

async function test() {
  try {
    console.log('Testing Firestore connection...');
    const snapshot = await db.collection('reports').limit(1).get();
    console.log('SUCCESS! Connected to Firestore. Docs found:', snapshot.size);
  } catch (e) {
    console.error('FAILED:', e.message);
  }
}
test();
