const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');

async function testAnalyze() {
  try {
    const formData = new FormData();
    formData.append('file', fs.createReadStream('./uploads/1776364036376-214058457-1234.jpeg'));

    console.log('Sending request to /analyze...');
    const response = await axios.post('http://localhost:5001/analyze', formData, {
      headers: {
        ...formData.getHeaders()
      }
    });

    console.log('Response Status:', response.status);
    console.log('Response Data:', response.data);
  } catch (error) {
    console.error('Error:', error.response ? error.response.data : error.message);
  }
}

testAnalyze();
