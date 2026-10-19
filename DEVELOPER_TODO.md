# Developer TODO

Actions only the maintainer can take. Remove an entry once it is done.

## Developer Action Required

### GitHub: confirm Actions runs on this private repo
- **What:** Check that GitHub Actions is enabled for `sorawit-w/job-scout` and that the `ci` workflow runs on the setup PR.
- **Why:** The Standard gate runs in CI on Python 3.9 and 3.13; a PR without a CI result has no independent check.
- **How:** Repo → Settings → Actions → General → "Allow all actions and reusable workflows". Private repos use your account's Actions minutes.
- **Where to put the result:** Nothing to record; the green check on the PR is the evidence.
- **Blocked tasks:** None now; CI evidence for every milestone PR.

### GitHub: let the weekly seed check open pull requests
- **What:** Allow workflows to write to the repo and to create pull requests.
- **Why:** M1b task D14 adds a weekly seed-check workflow that pushes a `chore/seed-check-<date>` branch and opens a PR with board status changes. It never pushes to `main`.
- **How:** Repo → Settings → Actions → General → Workflow permissions → "Read and write permissions", and tick "Allow GitHub Actions to create and approve pull requests".
- **Where to put the result:** Nothing to record.
- **Blocked tasks:** M1b D14 (the workflow will fail its PR step until this is set).
