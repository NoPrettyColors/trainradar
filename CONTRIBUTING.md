# Contributing to TrainRadar

Thanks for helping. TrainRadar is a small project, so the process is light, but `main` is protected and every change goes through a pull request.

## How to propose a change

1. **Open an issue first** for anything bigger than a small fix, so we can agree on the approach before you write code.
2. **Fork** the repository and create a branch from `main` (`fix/stop-panel-scroll`, `feat/ld-trains`).
3. **Make the change**, keeping to the conventions below. Run it locally (see the README) and check it in the browser, in light and dark themes and at phone width.
4. **Open a pull request** against `main` and fill in the template. Keep each PR to one topic.
5. **CI must pass**, and a maintainer listed in `.github/CODEOWNERS` must approve it. Address review comments by pushing new commits; they are squashed on merge.

Maintainers merge with **squash merge** only, so the PR title becomes the commit message: write it as a short imperative sentence ("Add long-distance trains to the map").

## Rules for `main`

- No direct pushes, force pushes or branch deletion. Changes land only through reviewed pull requests.
- The `check` CI job must pass and the branch must be up to date with `main`.
- Review conversations must be resolved before merging.
- Production is deployed by a maintainer from `main` after merging. Contributors never need access to the server.

## Conventions

- **Server:** Python standard library only (plus `tzdata`). Don't add runtime dependencies without discussing it in an issue.
- **Upstream etiquette:** one shared poll per feed serves every viewer. Never add per-request calls to Renfe or other data providers.
- **UI:** values come from Brokkr tokens (`--npc-*`); app-only variables use the `--app-` prefix. No hard-coded colours or sizes.
- **Data:** only open, documented sources with a licence that allows reuse. Credit them in the app's data panel and in `THIRD-PARTY-NOTICES.md`.
- **Line endings:** LF.

## Security

- Never commit server addresses, SSH keys, certificates, private keys, API tokens or account IDs. Secret scanning with push protection is enabled on this repository.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

## Licence

By contributing you agree that your contribution is licensed under the [MIT licence](LICENSE).
