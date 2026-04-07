# Releasing

Guide for publishing **ensemble-mcp** releases.

## Versioning

This project follows [PEP 440](https://peps.python.org/pep-0440/) and [Semantic Versioning](https://semver.org/):

| Stage | Version format | Example | `pip install ensemble-mcp` installs it? |
|---|---|---|---|
| Alpha | `X.Y.ZaN` | `0.1.0a1` | No (requires `--pre` or explicit version) |
| Beta | `X.Y.ZbN` | `0.1.0b1` | No |
| Release Candidate | `X.Y.ZrcN` | `0.1.0rc1` | No |
| Stable | `X.Y.Z` | `0.1.0` | Yes |

## Closed Alpha Release (via GitHub Releases)

The alpha is distributed as a wheel attached to a GitHub Release on a **private repo**. Access is controlled by GitHub repository permissions — only collaborators can download the asset.

### Prerequisites

- Python 3.11+
- `build` package installed: `pip install build`
- GitHub CLI (`gh`) authenticated: `gh auth status`
- Push access to the repository

### Step-by-step

#### 1. Set the version

In `pyproject.toml`, set the version to an alpha tag:

```toml
version = "0.1.0a1"
```

Also ensure the classifier reflects the development status:

```toml
"Development Status :: 3 - Alpha",
```

Increment the alpha number (`a1` -> `a2` -> `a3` ...) for each subsequent alpha release.

#### 2. Update the changelog

Add an entry to `CHANGELOG.md`:

```markdown
## [0.1.0a1] - YYYY-MM-DD

Closed alpha release for early testers.

### Added
- ...

### Fixed
- ...
```

#### 3. Run quality checks

```bash
python -m pytest tests/ -v
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
```

All checks must pass before releasing.

#### 4. Build the package

```bash
python -m build
```

This produces two files in `dist/`:

```
dist/
  ensemble_mcp-0.1.0a1.tar.gz          # sdist
  ensemble_mcp-0.1.0a1-py3-none-any.whl  # wheel
```

#### 5. Verify the build

```bash
# Check the package metadata
python -m zipfile -l dist/ensemble_mcp-0.1.0a1-py3-none-any.whl

# Test install in a clean venv
python -m venv /tmp/test-install
source /tmp/test-install/bin/activate
pip install dist/ensemble_mcp-0.1.0a1-py3-none-any.whl
ensemble-mcp --help
deactivate
rm -rf /tmp/test-install
```

#### 6. Create the GitHub Release

```bash
gh release create v0.1.0a1 \
  --title "v0.1.0a1 - Alpha 1" \
  --notes "Closed alpha release. See CHANGELOG.md for details." \
  --prerelease \
  dist/ensemble_mcp-0.1.0a1-py3-none-any.whl \
  dist/ensemble_mcp-0.1.0a1.tar.gz
```

#### 7. Commit and tag

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "release: v0.1.0a1"
git tag v0.1.0a1
git push origin main --tags
```

> Note: `gh release create` already creates the tag on the remote if it doesn't exist. If you ran step 6 first, you can skip the `git tag` command and just push the commit.

## How Testers Install

> **Note:** Modern Debian/Ubuntu systems (Python 3.12+) block global `pip install` with an `externally-managed-environment` error ([PEP 668](https://peps.python.org/pep-0668/)). Use `pipx` or a virtual environment as described below.

### 1. Download the wheel

For a **private** repository, testers need a [GitHub Personal Access Token](https://github.com/settings/tokens) (classic with `repo` scope, or fine-grained with **Contents: Read** permission).

**Option A — using `gh` CLI (simplest):**

```bash
gh release download v0.1.0a1 --repo LynkByte/ensemble --pattern "*.whl"
```

**Option B — direct URL with token:**

```bash
curl -L -H "Authorization: token <GITHUB_PAT>" \
  -o ensemble_mcp-0.1.0a1-py3-none-any.whl \
  "https://github.com/LynkByte/ensemble/releases/download/v0.1.0a1/ensemble_mcp-0.1.0a1-py3-none-any.whl"
```

For a **public** repository, no authentication is needed:

```bash
curl -L -o ensemble_mcp-0.1.0a1-py3-none-any.whl \
  "https://github.com/LynkByte/ensemble/releases/download/v0.1.0a1/ensemble_mcp-0.1.0a1-py3-none-any.whl"
```

### 2. Install the wheel

#### Using pipx (recommended)

`pipx` is ideal for CLI tools like `ensemble-mcp` — it automatically creates an isolated environment and makes the command available globally. No need to activate a venv every time.

```bash
# Install pipx if you don't have it
sudo apt install pipx    # Debian/Ubuntu
# or: brew install pipx  # macOS
# or: pip install --user pipx

pipx ensurepath  # add ~/.local/bin to PATH (one-time setup, restart shell after)

# Install the wheel
pipx install ensemble_mcp-0.1.0a1-py3-none-any.whl

# Verify
ensemble-mcp --help
```

#### Using a virtual environment

If you prefer to manage your own environment or need `ensemble-mcp` as a library dependency:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ensemble_mcp-0.1.0a1-py3-none-any.whl

# Verify
ensemble-mcp --help
```

> Remember to activate the venv (`source .venv/bin/activate`) each time you open a new terminal.

### Pinning in requirements.txt

For projects using a `requirements.txt` (inside a venv):

```
ensemble-mcp @ https://github.com/LynkByte/ensemble/releases/download/v0.1.0a1/ensemble_mcp-0.1.0a1-py3-none-any.whl
```

## Upgrading Testers to a New Alpha

1. Bump the version in `pyproject.toml` (e.g., `0.1.0a1` -> `0.1.0a2`)
2. Repeat steps 2-7 above
3. Tell testers to upgrade:

   **pipx:**
   ```bash
   gh release download v0.1.0a2 --repo LynkByte/ensemble --pattern "*.whl"
   pipx install --force ensemble_mcp-0.1.0a2-py3-none-any.whl
   ```

   **venv:**
   ```bash
   gh release download v0.1.0a2 --repo LynkByte/ensemble --pattern "*.whl"
   source .venv/bin/activate
   pip install --upgrade ensemble_mcp-0.1.0a2-py3-none-any.whl
   ```

## Transitioning to Public PyPI

When the alpha period is complete and you're ready for a public release:

1. Set the version to a stable release (e.g., `0.1.0`) in `pyproject.toml`
2. Update the classifier back to `"Development Status :: 4 - Beta"` (or `5 - Production/Stable`)
3. Follow the PyPI trusted publishing setup in [CONTRIBUTING.md](CONTRIBUTING.md#1-pypi-trusted-publishing-package-releases)
4. Create a GitHub Release **without** the `--prerelease` flag — the `publish.yml` workflow will automatically build and publish to PyPI via OIDC
