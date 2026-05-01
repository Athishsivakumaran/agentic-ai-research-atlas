# Agentic AI Research Atlas

Single-file HTML app for browsing a curated list of free, high-signal resources on:

- Agentic AI
- Context engineering
- Advanced RAG

## What is in this repo

- `index.html`: the standalone app
- `.github/workflows/deploy-pages.yml`: publishes the app to GitHub Pages
- `.github/workflows/atlas-maintenance.yml`: scheduled maintenance workflow
- `tools/atlas/link_check.py`: audits resource links and writes machine-readable reports

## GitHub Pages

This repo is set up to deploy the atlas as a static GitHub Pages site using GitHub Actions.

The publish workflow only uploads `index.html`, so unrelated files in the repository are not exposed on the public site.

## Scheduled pipeline

The maintenance workflow runs weekly and:

1. Parses the resource URLs embedded in `index.html`
2. Audits them for broken links
3. Uploads JSON and Markdown audit artifacts in GitHub Actions

## Important honesty note

This pipeline keeps the current atlas healthy and deployable, but it does **not** automatically discover brand-new best resources on its own.

For true "latest resource" refreshes, the scheduled job would need an additional curator step, such as:

- a trusted upstream dataset
- an LLM-backed curation script with an API key
- or a manual review workflow that updates the source list before deploy
