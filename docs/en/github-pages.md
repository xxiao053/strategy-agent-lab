# GitHub Pages

[English](github-pages.md) | [简体中文](../zh-CN/github-pages.md)

GitHub Pages hosts the read-only workbench: saved conversations, methods, code, tests, results and media. It does not run Python, Docker workers or live agents and needs no model credentials. The local application remains the way to create, build and run new projects.

## Hosting and address

[GitHub Free supports Pages for public repositories](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages). A project site uses `https://<owner>.github.io/<repository>/`; no purchased domain is needed. These are address patterns, not an announcement that this repository or site is already public. A custom domain is optional.

The current [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) include a 1 GB published-site maximum, a soft 100 GB/month bandwidth limit and a 10-minute deployment timeout. Pages is intended for static project sites, not a commercial transaction service or paid SaaS backend. This project's static viewer sends no credentials and makes no model calls. GitHub itself logs visitor IP addresses under its privacy policy.

## Preview without publishing

From the repository root:

```sh
pnpm --dir web install --frozen-lockfile
pnpm --dir web build:showcase-preview
pnpm --dir web exec vite preview --outDir dist-showcase-preview --host 127.0.0.1
```

Open the local address printed by Vite. This builds only static files and does not create a GitHub repository, upload anything or call a model. Install Node.js 22 and pnpm 11.25.0 for this frontend workflow; Docker is not needed to serve the static output.

## Review and publish from GitHub

The included [workflow](../../.github/workflows/pages.yml) is **manual-only**. A push or pull request does not publish a website.

1. After reviewing source, credentials, examples and distribution rights, create or use the approved public GitHub repository and upload only the reviewed source.
2. In **Actions → Review or publish static showcase → Run workflow**, keep **publish** off. The job installs the pinned dependencies, runs frontend tests, builds `web/dist-showcase/` and uploads a `github-pages` review artifact. Source links derive from the repository running the workflow.
3. Inspect that artifact before deployment. Repository source, databases, keys and private archives are not the Pages upload path. All shipped static files are downloadable by visitors, including bundled records not currently visible on screen.
4. When publication is approved, select **Settings → Pages → Build and deployment → Source → GitHub Actions**. Review the `github-pages` environment's deployment rules; use the default branch and require a reviewer where that account supports it.
5. Run the same workflow on the approved branch with **publish** on. The deploy job depends on the successful build and is the only job granted `pages: write` and `id-token: write`. Its deployment output supplies the actual website URL.

The workflow uses GitHub's temporary token/OIDC, not a personal access token or model key. See [GitHub's custom-workflow guide](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages). No GitHub-side run or public deployment is implied by a local build.

## Checks before sharing the address

- Verify navigation and refresh at the project subpath, including a direct `#/project/...` link. Assets are relative and navigation uses hashes; no server routing or custom 404 fallback is needed.
- Open both Builder examples, source files, results, charts and the video. Verify source/local-run links point to the approved repository and guide.
- Confirm that no local `/api` requests, provider requests or credential forms are present. Never add a model API key to `VITE_*` variables: those values can become public JavaScript.
- Retain `LICENSE`, `THIRD_PARTY_NOTICES.txt` and both data notices in the built artifact. The [data notice](../../DATA_NOTICE.md) distinguishes provenance from permission; attribution alone is not rights clearance.

Redeployment uses the same manual review/publish flow. Removing a site later does not revoke already downloaded copies of its files.
