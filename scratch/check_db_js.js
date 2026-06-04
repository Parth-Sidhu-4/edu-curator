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
    const cur = typeof row.content_json === 'string' ? JSON.parse(row.content_json) : row.content_json;
    if (!cur) continue;
    const def = cur.definition;
    if (def && (def.includes('records changes') || def.includes('Version control'))) {
      console.log("MATCHED TOPIC:", row.topic_id);
      console.log("RAW JS STRING VALUE:");
      console.log(JSON.stringify(def));
    }
  }
})
.catch(err => console.error("Error:", err));
