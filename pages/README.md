# RPStack documentation site

The authored documentation is in `content/`; `navigation.json` defines left-menu
order and groups. CSS/JavaScript live in `assets/`. The Python builder produces
static HTML, per-page contents lists, previous/next links, and a search index.
It checks generated local links and fragments before succeeding.

## Build and preview

From the repository root:

```sh
python3 -m venv pages/.venv
pages/.venv/bin/python -m pip install -r pages/requirements.txt
pages/.venv/bin/python pages/build.py
python3 -m http.server 8000 --directory pages/_site
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

In repository **Settings → Pages**, select **GitHub Actions** as the build source.
The `Documentation Pages` workflow builds on documentation pull requests and
pushes; only default-branch pushes or a manual run on the default branch deploy.
It publishes `pages/_site`, not the repository root. No deployment was performed
when creating these files.

A custom Actions workflow is needed because `pages/` is not the built-in `/docs`
branch-source directory. See GitHub's [custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
