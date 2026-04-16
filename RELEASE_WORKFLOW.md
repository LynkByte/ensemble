# Release Workflow Guide

## Overview

The **Release to PyPI** workflow (`release.yml`) automates the entire release process for ensemble-mcp via a GitHub Actions button click. It:

1. ✅ Validates code (lint, type check, tests)
2. 📦 Builds distributions (wheel + source)
3. 🚀 Publishes to PyPI
4. 🏷️ Creates git tag and GitHub release
5. 📢 Posts release summary

**Trigger**: Manual button click via GitHub UI (workflow_dispatch) — never automatic on merge.

---

## How to Trigger a Release

### Via GitHub Web UI

1. Go to **Actions** tab in the repository
2. Select **"Release to PyPI"** workflow on the left
3. Click **"Run workflow"** button
4. Fill in the form:
   - **Version**: e.g., `0.1.0b5` or `1.0.0`
   - **Create GitHub release**: ✅ (recommended, auto-detects if beta/RC)
5. Click **"Run workflow"**
6. Monitor the workflow run in the Actions tab

### Via GitHub CLI

```bash
gh workflow run release.yml \
  -f version=0.1.0b5 \
  -f create_github_release=true
```

### Via curl

```bash
curl -X POST \
  -H "Authorization: token <YOUR_GITHUB_TOKEN>" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows/release.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "version": "0.1.0b5",
      "create_github_release": "true"
    }
  }'
```

---

## Workflow Steps Explained

### 1. **Validate** Job
- Checks out code
- Runs `ruff check` (linting)
- Runs `mypy` (type checking)
- Runs full pytest suite (582 tests)
- **Validates CHANGELOG.md** — checks that a `## [X.Y.Z]` section exists for the release version (blocks release if missing)
- **Fails fast** if any validation fails

### 2. **Build** Job (after validation passes)
- Updates `pyproject.toml` with the new version
- Builds sdist (`.tar.gz`) and wheel (`.whl`)
- Validates distributions with `twine check`
- Uploads artifacts for the publish job

### 3. **Publish** Job (after build succeeds)
- Downloads distribution artifacts
- Uses **OIDC trusted publishing** (no secrets needed!)
- Publishes to PyPI
- Waits 10 seconds for PyPI indexing
- **Automatically commits updated `pyproject.toml` to main** with commit message: `chore: bump version to X.Y.Z [skip ci]`
- Pushes the version commit to origin

### 4. **Create Tag** Job (after publish succeeds)
- Creates an annotated git tag: `v{version}`
- Pushes tag to origin
- Optionally creates a GitHub Release with auto-generated body
- Detects pre-release status (alpha, beta, RC) automatically

### 5. **Notify** Job (final step)
- Posts a summary to the workflow run's summary page
- Shows PyPI link, installation command, etc.

---

## Version Format

The version you provide should match semantic versioning:

| Format | Example | Type |
|--------|---------|------|
| Stable | `1.0.0`, `0.2.1` | Full release |
| Beta | `0.1.0b5`, `1.0.0b1` | Pre-release |
| Alpha | `0.1.0a1`, `1.0.0a3` | Pre-release |
| Release Candidate | `1.0.0rc1`, `0.2.0rc2` | Pre-release |

The workflow automatically detects pre-release status and marks the GitHub Release accordingly.

---

## Security

### OIDC Trusted Publishing (No Secrets!)

The workflow uses **OIDC trusted publishing** to publish to PyPI without storing secrets:

- No need to paste API tokens
- No GitHub Secrets required
- GitHub's identity is verified by PyPI
- More secure than token-based auth

**Requirements**:
- PyPI project must have OIDC configured (ours already is)
- GitHub environment named `pypi` (already configured in `publish` job)

### GitHub Environment

The `publish` job runs in the `pypi` environment. This adds an extra layer of protection:
- You can require branch protections
- You can require manual approval (optional)
- Runs isolated from other secrets

To configure approval (optional):
1. Go to **Settings → Environments → pypi**
2. Enable **Required reviewers**
3. Add your GitHub users

---

## Troubleshooting

### CHANGELOG.md validation fails
**Problem**: Workflow fails with "CHANGELOG.md is missing a section for version X.Y.Z"  
**Solution**: Add `## [X.Y.Z] - YYYY-MM-DD` with at least one sub-heading (`### Added`, etc.) to `CHANGELOG.md`, commit, push, and retry.

### Workflow fails at validation
**Problem**: Tests or linting fail  
**Solution**: Fix the issue locally, push to main, then retry the workflow

### Version already exists on PyPI
**Problem**: Workflow succeeds but version already published  
**Solution**: Use a different version number next time

### Tag already exists
**Problem**: Git tag creation fails  
**Solution**: The workflow skips tag creation if tag exists (safe). Use a new version.

### OIDC publishing fails
**Problem**: "OIDC token verification failed"  
**Solution**: This shouldn't happen if PyPI is configured. Check PyPI trusted publishers settings.

### Workflow hangs
**Problem**: Workflow stuck at a step  
**Solution**: 
1. Cancel the run
2. Check logs for error details
3. Retry after fixing the issue

---

## Before First Release

Ensure:
1. ✅ `pyproject.toml` has correct metadata
2. ✅ `README.md` is up to date
3. ✅ `CHANGELOG.md` documents the version *(enforced — workflow fails without it)*
4. ✅ All tests pass locally
5. ✅ PyPI environment is configured in GitHub
6. ✅ PyPI has OIDC trusted publishers configured (it does)

---

## After Release

The workflow automatically:
1. ✅ Updates and commits `pyproject.toml` to main
2. ✅ Creates `vX.Y.Z` git tag
3. ✅ Pushes tag to origin
4. ✅ Creates GitHub Release
5. ✅ Posts summary in Actions tab

What you should do:
1. Verify the version commit was pushed to main
2. Update CHANGELOG.md with release notes (if not already done)
3. Share the release link: `https://pypi.org/project/ensemble-mcp/X.Y.Z/`
4. Update docs/website if needed

---

## Example Workflow Run

```
[Validate] ✅ Linting, typing, tests, changelog check
    ↓
[Build] ✅ Build sdist + wheel, validate with twine
    ↓
[Publish] ✅ Upload to PyPI via OIDC, commit version to main
    ↓
[Create Tag] ✅ Create git tag v0.1.0b5, GitHub Release
    ↓
[Notify] ✅ Post summary to Actions

🎉 Released v0.1.0b5 to PyPI and GitHub
```

---

## Configuration

The workflow is zero-config — it works out of the box. Optional customizations:

### Skip GitHub Release Creation

When triggering, set `create_github_release=false` to skip GitHub Release creation.

### Customize Release Notes

Edit the `Create GitHub Release` step in `release.yml` to customize the release body.

### Require Approval

To require manual approval before publishing to PyPI:
1. Go to **Settings → Environments → pypi**
2. Enable **Required reviewers**
3. Add approvers

---

## FAQ

**Q: Can I release from a branch other than main?**  
A: Yes, you can edit the workflow trigger to allow other branches, but it's recommended to use main.

**Q: What if the version is already released?**  
A: PyPI rejects duplicate versions. Update the version number and retry.

**Q: Can I undo a release?**  
A: No, PyPI prevents re-uploading the same version. You can only yank it (mark as unsafe) from PyPI settings.

**Q: Do I need to commit CHANGELOG.md changes first?**  
A: **Yes.** The workflow validates that `CHANGELOG.md` has a section for the release version. If it's missing, the release is blocked. Update `CHANGELOG.md`, commit and push to `main`, then trigger the workflow.

**Q: Can I test the workflow before a real release?**  
A: Yes, use a test version like `0.1.0b999` and publish to TestPyPI (edit workflow to use `--repository testpypi`).

---

## Next Steps

1. ✅ Commit this workflow to git
2. ✅ Push to main
3. ✅ Go to **Actions** → **"Release to PyPI"**
4. ✅ Click **"Run workflow"**
5. ✅ Enter version (e.g., `0.1.0b5`)
6. ✅ Click **"Run workflow"**
7. ✅ Monitor the run and celebrate! 🎉
