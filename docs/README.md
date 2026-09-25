# RPStack documentation site

The authored documentation is in `content/`; `navigation.json` defines left-menu
order and groups. CSS/JavaScript live in `assets/`. The Python builder produces
static HTML directly in `docs/`, per-page contents lists, previous/next links,
and a search index. Generated HTML, `search.json`, and `.nojekyll` are committed
so GitHub Pages can serve this folder without running Python.
It checks generated local links and fragments before succeeding.

## Build and preview

From the repository root:

```sh
python3 -m venv docs/.venv
docs/.venv/bin/python -m pip install -r docs/requirements.txt
docs/.venv/bin/python docs/build.py
python3 -m http.server 8000 --directory docs
```

Open http://localhost:8000. Serve the generated folder; don't open HTML via a
`file:` URL if you need search. All site links are relative, so project-path
hosting (such as `/RobotPrimitivesStack/`) works without a base-URL setting.

## Authoring

Add a Markdown file in `content/` and an entry in `navigation.json`. Use one H1
per document, H2s for its sections, fenced code blocks, and Markdown tables.
Link to other pages with their `.html` filenames. Mark incomplete manifest
examples as fragments. Keep device APIs aligned with their component contracts
and embedded deployment manifests.

Use fenced `mermaid` blocks for diagrams. Mermaid 11.4.1 is loaded from jsDelivr;
rendering needs network access. The rest of the site is static, and diagram
source remains available if the module cannot load. Build dependencies are
pinned in `requirements.txt`. No JavaScript framework or Node build is needed.

## GitHub Pages

After merging this change into `main`, open repository **Settings → Pages**.
Under **Build and deployment**, choose **Deploy from a branch**, select **main**
and **/docs**, and click **Save**. GitHub's built-in Pages workflow publishes
`docs/index.html` and the other static files. The committed `.nojekyll` file
turns off Jekyll processing.

The `Documentation Pages` workflow builds and link-checks the site on pull
requests and pushes, and verifies that the committed generated files are current.
It does not deploy a second copy through the Actions Pages API.

After changing Markdown, navigation, or the builder, run `python3 docs/build.py`
and commit the generated files along with the source changes. Preview with
`python3 -m http.server 8000 --directory docs`.

See GitHub's [publishing source documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
