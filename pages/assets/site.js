const menu = document.querySelector('#menu');
const sidebar = document.querySelector('#sidebar');
menu.addEventListener('click', () => {
  const open = sidebar.classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && sidebar.classList.contains('open')) {
    sidebar.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); menu.focus();
  }
});
let index;
const input = document.querySelector('#search');
const results = document.querySelector('#results');
input.addEventListener('input', async () => {
  const query = input.value.trim().toLowerCase();
  results.replaceChildren();
  if (!query) return;
  try {
    index ||= fetch('search.json').then(response => { if (!response.ok) throw new Error('Search unavailable'); return response.json(); });
    const pages = await index;
    if (input.value.trim().toLowerCase() !== query) return;
    const hits = pages.filter(p => (p.title + ' ' + p.text).toLowerCase().includes(query))
      .sort((a,b) => Number(b.title.toLowerCase().includes(query)) - Number(a.title.toLowerCase().includes(query))).slice(0,8);
    results.replaceChildren();
    if (!hits.length) { const p = document.createElement('p'); p.textContent = 'No matching topics.'; results.append(p); }
    for (const hit of hits) { const a = document.createElement('a'); a.href = hit.url; a.textContent = hit.title; results.append(a); }
  } catch (_) { results.textContent = 'Search unavailable. Use the menu below.'; index = undefined; }
});
