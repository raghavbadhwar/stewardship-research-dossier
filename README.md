# Stewardship Research Dossier

[![CI](https://github.com/raghavbadhwar/stewardship-research-dossier/actions/workflows/ci.yml/badge.svg)](https://github.com/raghavbadhwar/stewardship-research-dossier/actions/workflows/ci.yml)

A local candidate prototype for turning public company evidence into a source-linked governance and risk brief, retaining a counter-view, and comparing later research runs.

## Status

Foundation scaffold only. It currently provides environment checks and a CLI smoke test; source retrieval, dossiers, MCP tools, host packaging and research delegation are planned but not implemented.

The project is informed by publicly described priorities around AI-assisted research and human review in investment management. It is not a product requested, used or endorsed by NBIM.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --all-groups
uv run srd --version
uv run srd doctor
```

## Development checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

## Boundaries

This project does not execute trades, connect to brokers, make investment decisions, access private sources, store credentials, bypass access controls, or claim investment performance. It will remain local and single-user in its first version.

## Licence

MIT. See [LICENSE](LICENSE).
