# Collaboration Sync

Use GitHub `main` as the single shared version of the portfolio.

Before either George or Anna starts editing:

1. Open this repository folder.
2. Run `sync_before_work.bat`.
3. Confirm it ends with the current commit hash.

After making changes:

1. Commit the work in GitHub Desktop or with Git.
2. Run `publish_changes.bat`, or in GitHub Desktop click **Fetch origin**, **Pull origin**, then **Push origin**.
3. Tell the other person to run `sync_before_work.bat`.

Rules that keep both computers on the same version:

- Work on `main` unless you intentionally create a pull request branch.
- Pull before editing.
- Push immediately after committing.
- If GitHub Desktop reports a conflict, stop and resolve it before continuing.
- The version is the same when both computers show the same latest commit hash from `git log -1 --oneline`.
