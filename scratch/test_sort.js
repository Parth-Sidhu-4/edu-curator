const fs = require('fs');
const path = require('path');

const topics = JSON.parse(fs.readFileSync(path.join(__dirname, '../data/seed/syllabus_topics.json'), 'utf8'));

function compareTopicNumbers(a, b) {
  const parse = (name) => {
    const match = name.match(/^(\d+(?:\.\d+)*)/);
    return match ? match[1].split('.').map(Number) : [999];
  };
  const numA = parse(a.topic_name || '');
  const numB = parse(b.topic_name || '');
  for (let i = 0; i < Math.max(numA.length, numB.length); i++) {
    const valA = numA[i] !== undefined ? numA[i] : 0;
    const valB = numB[i] !== undefined ? numB[i] : 0;
    if (valA !== valB) return valA - valB;
  }
  return (a.topic_name || '').localeCompare(b.topic_name || '');
}

console.log("Original order of first 5:");
topics.slice(0, 5).forEach(t => console.log(` - ${t.topic_name}`));

topics.sort(compareTopicNumbers);

console.log("\nSorted order:");
topics.forEach((t, i) => console.log(`${i+1}. ${t.topic_name}`));
