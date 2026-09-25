"""Build the static documentation site: python3 docs/build.py."""
import html
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import markdown

ROOT = Path(__file__).resolve().parent
# Commit generated files here so GitHub Pages can publish main:/docs directly.
OUT = ROOT
nav = json.loads((ROOT / 'navigation.json').read_text())
OUT.mkdir(exist_ok=True)
search = []
for index, page in enumerate(nav):
    source = (ROOT / 'content' / (page['slug'] + '.md')).read_text()
    md = markdown.Markdown(extensions=['fenced_code', 'tables', 'toc'], extension_configs={'toc': {'permalink': '¶'}})
    body = md.convert(source)
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', r'<pre class="mermaid">\1</pre>', body, flags=re.S)
    links, group = [], None
    for item in nav:
        if item['group'] != group:
            group = item['group']
            links.append('<h2>' + html.escape(group) + '</h2>')
        current = ' aria-current="page"' if item == page else ''
        links.append(f'<a href="{item["slug"]}.html"{current}>{html.escape(item["title"])}</a>')
    previous = nav[index - 1] if index else None
    following = nav[index + 1] if index + 1 < len(nav) else None
    pager = ''.join(f'<a href="{p["slug"]}.html"><small>{label}</small>{html.escape(p["title"])}</a>' for p, label in [(previous, 'Previous'), (following, 'Next')] if p)
    title = html.escape(page['title'])
    output = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · RPStack</title><meta name="description" content="RPStack documentation: {title}">
<link rel="stylesheet" href="assets/site.css"><script src="assets/site.js" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a>
<header><a class="brand" href="index.html"><span class="mark">RP</span> RPStack <small>Documentation</small></a>
<button id="menu" aria-controls="sidebar" aria-expanded="false">Menu</button>
<a class="repo" href="https://github.com/ROSMicroPy/RobotPrimitivesStack">GitHub ↗</a></header>
<div class="layout"><aside id="sidebar"><label for="search">Search documentation</label>
<input id="search" type="search" placeholder="Find a topic…" autocomplete="off">
<div id="results" aria-live="polite"></div><nav aria-label="Documentation">{''.join(links)}</nav></aside>
<main id="main"><div class="eyebrow">{html.escape(page['group'])}</div><article>{body}</article>
<nav class="pager" aria-label="Adjacent pages">{pager}</nav>
<footer>RPStack · Robot Primitives Software Stack</footer></main>
<aside class="on-page"><h2>On this page</h2>{md.toc}</aside></div>
<script type="module">
const diagrams = document.querySelectorAll('.mermaid');
if (diagrams.length) {{
  try {{
    const {{ default: mermaid }} = await import('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs');
    mermaid.initialize({{ startOnLoad: false, securityLevel: 'strict', theme: 'neutral', fontFamily: 'system-ui', flowchart: {{ useMaxWidth: true }} }});
    await mermaid.run({{ nodes: diagrams }});
  }} catch (error) {{
    for (const diagram of diagrams) {{
      const note = document.createElement('p');
      note.textContent = 'Diagram rendering unavailable. Mermaid source is shown below.';
      diagram.before(note);
    }}
    console.error(error);
  }}
}}
</script></body></html>'''
    (OUT / (page['slug'] + '.html')).write_text(output)
    search.append({'title': page['title'], 'url': page['slug'] + '.html', 'text': re.sub(r'<[^>]+>', ' ', body)})
(OUT / 'search.json').write_text(json.dumps(search))
(OUT / '.nojekyll').touch()
# Check every generated local link, asset, and fragment before deployment.
class Links(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.links = []; self.ids = set(); self.feed(text)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs: self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs: self.links.append(attrs[key])
pages = {p: Links(p.read_text()) for p in OUT.glob('*.html')}
for path, parsed in pages.items():
    for link in parsed.links:
        url = urlsplit(link)
        if url.scheme or url.netloc: continue
        target = (path.parent / unquote(url.path)).resolve() if url.path else path
        if not target.is_file(): raise ValueError(f'{path.name}: missing link {link}')
        if url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
            raise ValueError(f'{path.name}: missing fragment {link}')
print(f'Built and link-checked {len(nav)} pages in {OUT}')
