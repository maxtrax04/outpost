# How work is organized on GitHub

A quick guide to the GitHub features this project uses and how they fit together.

## The pieces

| Piece | What it is | How Outpost uses it |
|---|---|---|
| **Issue** | A task, bug, or idea with a discussion thread | One issue per piece of work |
| **Label** | A colored tag on an issue | Says what kind (`bug`, `enhancement`) and which area (`themes`, `providers`) |
| **Milestone** | A group of issues for one release | `v0.3.0`, `v0.4.0`, and so on; shows a progress bar |
| **Branch** | A separate line of work | One short-lived branch per issue |
| **Pull request (PR)** | A proposal to merge a branch into `main` | Where changes are reviewed and CI runs |
| **Release** | A published version built from a tag | Created from a tag like `v0.3.0` |

`main` is always the stable line. There are no long-lived dev or prod branches; releases are marked by tags.

## The loop for one change

1. **Pick an issue.** Open the milestone and choose one. Note its number, for example `#7`.
2. **Make a branch.**
   ```
   git switch main
   git pull
   git switch -c fix-alerts-message
   ```
3. **Make the change and commit it.**
   ```
   git add -A
   git commit -m "Say when a source does not provide alerts"
   ```
4. **Push the branch and open a PR.**
   ```
   git push -u origin fix-alerts-message
   ```
   GitHub prints a link to open the pull request. Fill in the template and write `Closes #7` so the issue closes by itself when the PR is merged.
5. **Wait for the checks** (once CI exists), fix anything that fails by pushing more commits to the same branch.
6. **Merge** the PR (a squash merge keeps `main` tidy), then delete the branch and update your copy:
   ```
   git switch main
   git pull
   ```

## Releasing

When a milestone is finished, follow `docs/releasing.md`: bump `VERSION`, update the changelog, tag, and publish a GitHub Release.

## Handy tips

- Use `Closes #7`, `Fixes #7`, or `Resolves #7` in a PR description to link and auto-close issues.
- Click a label to see every issue with it, or a milestone to see its progress.
- Never put real coordinates, `weather.json`, `.env`, or API keys in an issue, PR, or screenshot.
