#!/bin/bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_slug='JHegstad/QuotaMonitor'
cd "$project_dir"

command -v git >/dev/null || { echo 'Git is required.' >&2; exit 1; }
command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required.' >&2; exit 1; }

if ! gh auth status --hostname github.com; then
    echo 'Authenticate from Terminal, then rerun this script:' >&2
    echo '  gh auth login --hostname github.com --git-protocol https --web' >&2
    exit 1
fi
github_login="$(gh api user --jq .login)"
if [ "$github_login" != 'JHegstad' ]; then
    echo "Expected GitHub account JHegstad; authenticated as $github_login. No upload performed." >&2
    exit 1
fi

if [ -e .git ]; then
    if [ "$(git rev-parse --show-toplevel)" != "$project_dir" ]; then
        echo 'Unexpected Git repository root; stopping.' >&2
        exit 1
    fi
    if [ -n "$(git remote)" ]; then
        echo 'This project already has a Git remote. No remote or history was changed.' >&2
        echo 'Inspect it with: git remote -v' >&2
        exit 1
    fi
else
    git init -b main
fi

if [ "$(git branch --show-current)" != main ]; then
    echo 'Expected branch main. No upload performed.' >&2
    exit 1
fi
if [ -n "$(git diff --cached --name-only)" ]; then
    echo 'There are already staged changes. Review and commit them before rerunning.' >&2
    exit 1
fi
if gh repo view "$repo_slug" --json name >/dev/null 2>&1; then
    echo "$repo_slug already exists. No existing repository was modified." >&2
    exit 1
fi

# Explicit source paths plus .gitignore exclude build products and local files.
git add -- .gitignore README.md publish-github.sh App Shared Widget Linux project.yml QuotaMonitor.xcodeproj
if ! git diff --cached --quiet; then
    git commit -m 'Add QuotaMonitor for macOS and Ubuntu GNOME 46'
fi
gh repo create "$repo_slug" --private \
    --description 'Read-only Work/Codex quota monitoring for macOS and Ubuntu GNOME 46' \
    --source "$project_dir" --remote origin --push
gh repo view "$repo_slug" --json url --jq .url
