# Automated Release Workflow

This guide covers the new **automated release workflow** for publishing ensemble-mcp via GitHub Actions with a single button click.

## Overview

The **Release to PyPI** workflow (`release.yml`) fully automates the release process:

- ✅ Validates code (lint, type check, tests)
- ✅ Builds distributions (sdist + wheel)
- ✅ Publishes to PyPI using OIDC trusted publishing
- ✅ Creates git tags and GitHub Releases
- ✅ Posts release summaries

**Key feature**: Manual trigger only via GitHub UI or CLI — no automatic releases on merge.

---

## Quick Start

### Trigger a Release

1. Go to **GitHub** → your repository → **Actions** tab
2. Select **"Release to PyPI"** workflow
3. Click **"Run workflow"** button
4. Enter the version (e.g., `0.1.0b5` or `1.0.0`)
5. Check **"Create GitHub release"** (recommended)
6. Click **"Run workflow"**
7. Monitor in the Actions tab (typically completes in 4-5 minutes)

### Via GitHub CLI

```bash
gh workflow run release.yml \
  -f version=0.1.0b5 \
  -f create_github_release=true
```

---

## Workflow Stages

### Stage 1: Validate
Runs before building to catch issues early.

- **Linting**: `ruff check src/ tests/`
- **Type checking**: `mypy src/`
- **Test suite**: `pytest tests/` (582 tests)
- **Changelog validation**: Checks that `CHANGELOG.md` contains a section for the release version (e.g., `## [0.1.0b5]`) with content under a sub-heading (e.g., `### Added`)

**Fails if**:
- Linting issues found
- Type errors detected
- Any test fails
- `CHANGELOG.md` is missing a section for the release version

### Stage 2: Build
Builds both source and wheel distributions.

- Updates `pyproject.toml` with the new version
- Builds sdist (`.tar.gz`) and wheel (`.whl`)
- Validates with `twine check`
- Uploads artifacts for publishing

**Output**:
- `ensemble_mcp-X.Y.Z.tar.gz` (~500 KB)
- `ensemble_mcp-X.Y.Z-py3-none-any.whl` (~150 KB)

### Stage 3: Publish
Publishes to PyPI using OIDC trusted publishing and commits version updates to git.

- Downloads distribution artifacts
- Authenticates via GitHub's OIDC token (no secrets needed)
- Uploads to PyPI
- Waits 10 seconds for indexing
- **Commits updated `pyproject.toml` to `main`** with message: `chore: bump version to X.Y.Z [skip ci]`
- Pushes the commit to origin

**No manual steps required** — OIDC handles authentication, and version management is fully automated.

### Stage 4: Create Tag
Creates git tag and optionally GitHub Release.

- Creates annotated git tag `vX.Y.Z`
- Pushes tag to origin
- Auto-detects pre-release status (alpha, beta, RC)
- Optionally creates GitHub Release with auto-generated body

### Stage 5: Notify
Posts a summary to the workflow run.

Shows:
- Version released
- PyPI link
- Installation instructions
- Actor who triggered the release

---

## Version Format

Use semantic versioning per [PEP 440](https://peps.python.org/pep-0440/):

| Type | Format | Example | PyPI Pre-release? |
|------|--------|---------|-------------------|
| Stable | `X.Y.Z` | `1.0.0`, `0.2.1` | No |
| Beta | `X.Y.ZbN` | `0.1.0b5`, `1.0.0b1` | Yes |
| Alpha | `X.Y.ZaN` | `0.1.0a1`, `1.0.0a3` | Yes |
| RC | `X.Y.ZrcN` | `1.0.0rc1`, `0.2.0rc2` | Yes |

**The workflow automatically detects pre-release versions** and marks GitHub Releases accordingly.

---

## Before You Release

### Checklist

- [ ] Code is merged to `main`
- [ ] All tests pass locally: `pytest tests/ -v`
- [ ] Linting passes: `ruff check src/ tests/`
- [ ] Type checking passes: `mypy src/`
- [ ] **CHANGELOG.md is updated with release notes** ⚠️ *(enforced by the workflow — release will fail without it)*
- [ ] Version number is decided (e.g., `0.1.0b5` or `1.0.0`)

> ℹ️ **Version Management**: The workflow automatically updates `pyproject.toml` with the version you provide and commits it back to `main` after publishing. No manual version edits needed.

### Update CHANGELOG

Add an entry to `CHANGELOG.md` **before** releasing. The workflow **will fail** if a section for the release version is missing.

The section header must match the exact version being released:

```markdown
## [0.1.0b5] - 2026-04-16

Public beta release.

### Added
- Automated release workflow for PyPI publishing
- OIDC trusted publishing (no secrets required)

### Fixed
- Bug fixes...

### Changed
- API improvements...
```

> ⚠️ **Enforced**: The workflow checks for `## [X.Y.Z]` in `CHANGELOG.md` and will **block the release** if it's missing. An empty section (no `### Added`, `### Fixed`, etc.) produces a warning but does not block.

---

## After Release

### What the Workflow Does Automatically

✅ Updates `pyproject.toml` with the new version  
✅ Commits `pyproject.toml` back to `main`  
✅ Creates `vX.Y.Z` git tag  
✅ Pushes tag to origin  
✅ Creates GitHub Release  
✅ Publishes to PyPI  

### What You Should Do

1. **Verify the version commit**: Check that `pyproject.toml` was updated on `main` (it's automatically committed with `[skip ci]` flag)
2. **Share the release**: https://pypi.org/project/ensemble-mcp/X.Y.Z/
3. **Update docs** if needed (API changes, breaking changes, etc.)
4. **Announce** to users/stakeholders
5. **Monitor feedback** (PyPI discussions, issues, etc.)

---

## Workflow Inputs

### `version` (Required)
The version to release (e.g., `0.1.0b5`, `1.0.0`)

**Format**: Semantic versioning per PEP 440  
**Example**: `0.1.0b5`, `1.0.0`, `2.0.0rc1`

### `create_github_release` (Optional)
Whether to create a GitHub Release for this version.

**Default**: `true`  
**Options**: `true` or `false`

Set to `false` if you want to publish to PyPI without creating a GitHub Release.

---

## Security

### OIDC Trusted Publishing

The workflow uses **OIDC trusted publishing** instead of API tokens:

- ✅ No tokens stored in GitHub Secrets
- ✅ GitHub's identity verified by PyPI
- ✅ Time-limited tokens (valid only during the workflow)
- ✅ More secure than long-lived API tokens

**Requirements**:
- PyPI project must be configured for OIDC (already done for ensemble-mcp)
- GitHub repository must have access to `id-token: write` permission (already configured)

### GitHub Environment

The `publish` job runs in the `pypi` environment, which can require approval:

**To require manual approval (optional)**:
1. Go to **Settings** → **Environments** → **pypi**
2. Enable **Required reviewers**
3. Add your GitHub users/teams

This adds an extra protection layer before publishing to PyPI.

---

## Troubleshooting

### Workflow Fails at Changelog Validation

**Problem**: Workflow fails with "CHANGELOG.md is missing a section for version X.Y.Z"  
**Solution**:
1. Add a section to `CHANGELOG.md` with the exact version: `## [X.Y.Z] - YYYY-MM-DD`
2. Add at least one sub-heading (`### Added`, `### Fixed`, etc.) with entries
3. Commit and push to `main`
4. Re-trigger the workflow

### Workflow Fails at Validation

**Problem**: Tests fail, linting errors, or type issues  
**Solution**:
1. Check the workflow logs for details
2. Fix the issue locally
3. Commit and push to `main`
4. Retry the workflow

### Version Already Exists on PyPI

**Problem**: Workflow succeeds but says version already published  
**Solution**: 
- Use a **new version number** next time
- PyPI prevents republishing the same version (by design)

### Git Tag Already Exists

**Problem**: "tag already exists" error  
**Solution**:
- Workflow safely skips tag creation if tag exists
- Use a new version number for the next release

### OIDC Publishing Fails

**Problem**: "OIDC token verification failed"  
**Solution**:
1. Check that PyPI project is configured for OIDC
2. Verify GitHub environment is set up
3. Try again — may be transient

### Workflow Stuck/Hangs

**Problem**: Workflow stuck at a step  
**Solution**:
1. Cancel the run (click "Cancel" in Actions tab)
2. Check logs for error details
3. Fix the issue
4. Retry

### Multiple Jobs Running Sequentially

**Problem**: Workflow taking longer than expected  
**Solution**:
- Validate job runs first (required for code quality)
- Build job runs after validation succeeds
- Publish waits for build
- Tag creation waits for publish
- This serial execution is intentional for safety

**Typical duration**: 4-5 minutes total

---

## Examples

### Release Beta 5

```bash
gh workflow run release.yml \
  -f version=0.1.0b5 \
  -f create_github_release=true
```

Result:
- Publishes to PyPI: `ensemble-mcp 0.1.0b5`
- Creates git tag: `v0.1.0b5`
- Creates GitHub Release marked as pre-release
- Link: https://pypi.org/project/ensemble-mcp/0.1.0b5/

### Release Stable v1.0.0

```bash
gh workflow run release.yml \
  -f version=1.0.0 \
  -f create_github_release=true
```

Result:
- Publishes to PyPI: `ensemble-mcp 1.0.0`
- Creates git tag: `v1.0.0`
- Creates GitHub Release marked as stable (not pre-release)
- Link: https://pypi.org/project/ensemble-mcp/1.0.0/

### Publish to PyPI Only (No GitHub Release)

```bash
gh workflow run release.yml \
  -f version=0.1.0b5 \
  -f create_github_release=false
```

Result:
- Publishes to PyPI only
- Creates git tag but no GitHub Release

---

## FAQ

### Q: Can I release from a different branch?
**A**: The workflow is configured for `main` only. To release from other branches, edit `.github/workflows/release.yml` and add branch names to the `ref` field. Recommended: use `main` for all releases.

### Q: What if I made a mistake in the version?
**A**: 
- If already published: Use a new version next time. PyPI prevents re-uploading.
- If still running: Cancel the workflow and retry with correct version.
- If caught before publish: Cancel and retry.

### Q: Can I test the workflow before a real release?
**A**: Yes, use a test version like `0.1.0b999` and manually edit the workflow to publish to TestPyPI instead:
```yaml
- name: Publish to TestPyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    repository-url: https://test.pypi.org/legacy/
```

### Q: What if PyPI is down during publishing?
**A**: The workflow will fail at the publish step. No harm done — you can retry later with the same version.

### Q: Do I need to tag manually?
**A**: No! The workflow creates the tag automatically. If you try to create it manually first, the workflow will skip it.

### Q: Can multiple releases happen in parallel?
**A**: Each workflow run is independent. Multiple releases can be triggered at once, but they'll publish separately (PyPI enforces unique versions).

### Q: Where can I see the release summary?
**A**: 
1. In the GitHub Actions tab — scroll to the bottom of the workflow run
2. In PyPI — check the project page
3. In GitHub Releases — see the release details

### Q: What if I forget to update CHANGELOG.md?
**A**: The workflow will **fail** at the validation stage with a clear error message telling you exactly what to add. Update `CHANGELOG.md`, commit, push, and re-run the workflow.

---

## Comparison: Manual vs Automated

| Task | Manual (Old) | Automated (New) |
|------|------|----------|
| Run tests | Command line | Workflow stage |
| Build distributions | Command line | Workflow stage |
| Validate | Manual | Automatic |
| Changelog check | None (easy to forget) | Enforced by workflow |
| Upload to PyPI | Manual (with token) | OIDC automatic |
| Create tag | Manual git commands | Workflow automatic |
| Create GitHub Release | Manual `gh release create` | Workflow automatic |
| Time taken | 10-15 minutes | 4-5 minutes |
| Error handling | Manual recovery | Workflow handles |
| Audit trail | Git log only | GitHub Actions logs |

---

## Next Steps

1. ✅ Review this guide
2. ✅ Update CHANGELOG.md with release notes
3. ✅ Commit and push to `main`
4. ✅ Go to **Actions** → **"Release to PyPI"**
5. ✅ Enter version (e.g., `0.1.0b5`)
6. ✅ Click **"Run workflow"**
7. ✅ Monitor and celebrate! 🎉

---

## Related Docs

- [RELEASING.md](RELEASING.md) — Original manual release guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contributing guidelines
- [.github/workflows/release.yml](../../.github/workflows/release.yml) — Workflow source code
