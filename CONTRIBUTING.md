# Contributing to Chrisnov Media Toolkit

Thanks for your interest in contributing! This project is in early beta, so
every bit of help goes a long way.

## How to contribute

### Bug reports

Open a [GitHub Issue](https://github.com/chrisnov-it/Chrisnov-Media-Toolkit/issues/new/choose)
using the **Bug Report** template. Include:

- Steps to reproduce
- Your OS and app version (see About dialog)
- Screenshot or error message if possible
- The URL you tried to download/convert (if applicable)

### Feature requests

Use the **Feature Request** template. Describe what you want to do, why the
current approach doesn't work, and — if you have one — how you imagine it
working.

### Pull requests

1. Fork the repo and create a branch from `main`.
2. If your change touches UI, include a screenshot or mockup.
3. Run the app locally to verify your change works:
   ```bash
   .venv\Scripts\python.exe main.py
   ```
4. Open a pull request using the **Pull Request** template.

### Code style

- Python 3.12+, PySide6, typed.
- Follow the existing code style — naming, imports, comments.
- Prefer focused, single-responsibility additions over large refactors.
- No external dependencies unless absolutely needed (stdlib first).

### Commit messages

We use conventional commits:

```
feat: add download history tab
fix: prevent Info/Start race
docs: update OLD-MAC-WORKAROUND.md
chore: bump to v0.1.0-beta.5
```

## Questions?

Open a [Discussion](https://github.com/chrisnov-it/Chrisnov-Media-Toolkit/discussions)
or email **contact@chrisnov.com**.
