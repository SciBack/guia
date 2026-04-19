# Contributing to GUIA

Thank you for your interest in contributing to GUIA — Gateway Universitario de Información y Asistencia.

GUIA is an open source project maintained by [SciBack](https://sciback.com). We welcome contributions from the community, especially from universities, developers, and researchers working with institutional repositories.

## What lives in this repository

This repository (`SciBack/guia`) contains the **documentation and project website** for GUIA, built with MkDocs Material. The open source core code lives in [`SciBack/guia-node`](https://github.com/SciBack/guia-node).

## Ways to contribute

### Documentation

- Fix typos, broken links, or outdated information
- Improve explanations or add examples
- Translate content (Spanish ↔ English)
- Add documentation for new connectors or standards

### Issues

- Report documentation bugs via [GitHub Issues](https://github.com/SciBack/guia/issues)
- Suggest improvements to the project website
- Request documentation for missing topics

### Code (in `guia-node`)

See the contributing guide in [`SciBack/guia-node`](https://github.com/SciBack/guia-node/blob/main/CONTRIBUTING.md) for code contributions.

## Getting started

### Prerequisites

- Python 3.9+
- pip

### Local development

```bash
git clone https://github.com/SciBack/guia.git
cd guia
pip install -r requirements.txt
python3 -m mkdocs serve
```

The site will be available at `http://localhost:8000`.

## Submitting changes

1. Fork the repository
2. Create a branch: `git checkout -b fix/typo-arquitectura`
3. Make your changes
4. Run `python3 -m mkdocs build --strict` to verify the site builds without errors
5. Commit with a clear message: `git commit -m "fix: correct OAI-PMH endpoint description"`
6. Push and open a Pull Request

## Commit message conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `fix:` — correction to existing content
- `docs:` — new documentation
- `feat:` — new section or page
- `refactor:` — restructuring without content change
- `chore:` — maintenance (deps, CI, config)

## Code of Conduct

By participating in this project you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions

Open an issue or contact us at [hola@sciback.com](mailto:hola@sciback.com).
