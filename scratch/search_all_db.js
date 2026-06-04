const fs = require('fs');

const envFile = fs.readFileSync('d:/Internship/.env', 'utf8');
const env = {};
envFile.split('\n').forEach(line => {
  const parts = line.split('=');
  if (parts.length >= 2) {
    const k = parts[0].trim();
    const v = parts.slice(1).join('=').trim().replace(/^"(.*)"$/, '$1');
    env[k] = v;
  }
});

const url = env.SUPABASE_URL;
const key = env.SUPABASE_KEY;
const targetUrl = `${url}/rest/v1/topic_content?select=*`;

fetch(targetUrl, {
  headers: {
    'apikey': key,
    'Authorization': `Bearer ${key}`
  }
})
.then(res => res.json())
.then(data => {
  for (const row of data) {
    const str = JSON.stringify(row);
    if (str.includes('r_i') || str.includes('r\\_i') || str.includes('r\\_i')) {
      console.log("MATCHED ROW ID:", row.id);
      console.log("TOPIC ID:", row.topic_id);
      console.log("JSON STRINGIFY MATCH:");
      // find where 'r_i' is in str
      const idx = str.indexOf('r_i');
      if (idx !== -1) {
        console.log("Found r_i around:", str.slice(idx - 50, idx + 50));
      }
      const idxEsc = str.indexOf('r\\_i');
      if (idxEsc !== -1) {
        console.log("Found r\\_i around:", str.slice(idxEsc - 50, idxEsc + 50));
      }
    }
  }
})
.catch(err => console.error("Error:", err));
