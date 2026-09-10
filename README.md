# Battery Value Chain

A small data-engineering and Neo4j prototype for exploring dependencies across a battery manufacturing value chain.

## Current scope

The project starts with synthetic source-system exports and a medallion-style pipeline:

```text
synthetic source systems -> Bronze -> Silver -> Neo4j
```

Bronze preserves source files as received. Silver will standardize, validate, deduplicate, and resolve entities before the graph-loading phase.

## Repository layout

```text
data/
  bronze/       Raw source-system exports
  silver/       Canonical graph-ready data
src/
  battery_value_chain/
tests/
```

## Development

Create a virtual environment and install the package in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run checks with:

```bash
pytest
python -m compileall src
```

The Neo4j and LLM layers will be added after the source data and Silver transformations are working.