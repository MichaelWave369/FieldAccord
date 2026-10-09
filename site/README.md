# FieldAccord public React showcase

This directory hosts the **public, static, interactive documentation site** for FieldAccord. It is intentionally separate from the Python coordination protocol and does not replace or alter its contracts.

## Live Pages address after enabling deployment

https://michaelwave369.github.io/FieldAccord/

## Local development

Run the following commands from the repository root:

    cd site
    npm install
    npm test
    npm run dev

Build with \`npm run build\`. Vite uses \`/FieldAccord/\` as its base path, so production assets load correctly from project GitHub Pages.

## Publish

1. Merge the PR containing this folder and \`.github/workflows/pages.yml\`.
2. Open the repository **Settings > Pages > Build and deployment** and select **GitHub Actions** as the source.
3. Open **Actions > Deploy FieldAccord Showcase > Run workflow** if the merge does not trigger a deployment.
4. Check the URL above once the build and deploy jobs succeed.

PR checks build and test the site but **cannot deploy it**. Deployment only occurs on a \`main\` push or manual workflow dispatch.

## What the browser does

- Interactive navigation, protocol illustrations, ecosystem browser, and expandable non-authority principles.
- A synthetic **Protocol Lab**, teaching the distinction between \`BLOCKED\` and \`REVIEW_REQUIRED\` using a deliberately limited client-side function (\`src/policy.js\`). It is **not** the canonical Python \`fieldaccord.core\` policy implementation and it never grants authority.
- An in-memory example WorkEvent timeline, closed/blocked/review states and an advisory attention toggle. This is **not** replay-verifying a real work journal, cryptographically linked or authenticated, and it does not send any notification.
- Boundaries for the documented source bridges, with links to public repositories. No live network fetches are initiated by the bridge explorer.

All demo state is discarded on page reload. No authentication, credentials, persistent storage, agent runtime, device control, API connector, or external effect is included. Do not add real work records, secrets, medical information, or environment variables to static site assets.

## Security and provenance

Keep \`site/\` an independent **public storytelling surface**, not an authority boundary. Real permission must be obtained and revalidated in the independently trusted executor. Source digests do not prove author identity. All bridge descriptions reflect documented repo capabilities, not live integrations. The existing FieldAccord Python tests remain the authoritative contract checks.

See the root README and AGENTS.md for implementation boundaries.
