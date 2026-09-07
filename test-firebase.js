require('dotenv').config();
let k = process.env.FIREBASE_PRIVATE_KEY || '';
k = k.trim().replace(/^"|"$/g, '').replace(/\\n/g, '\n');
console.log('Starts correctly:', k.startsWith('-----BEGIN PRIVATE KEY-----'));
console.log('Ends correctly:', k.trimEnd().endsWith('-----END PRIVATE KEY-----'));
console.log('Has real newlines:', k.includes('\n'));
