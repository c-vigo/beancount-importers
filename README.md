# Beancount Importers

A collection of importers for [Beancount](https://beancount.github.io/), the double-entry bookkeeping software.

## Features

- **Modular Design**: Easy to extend with new importers
- **Type Safety**: Full type hints and mypy support
- **Modern Python**: Requires Python 3.12
- **Comprehensive Testing**: pytest-based test suite
- **Code Quality**: Ruff (linting & formatting), isort, and mypy integration

## Importers

The following importers are available in this package:

- **certo_one**: CertoOne credit card PDF statements
- **finpension**: Finpension CSV
- **ibkr**: Interactive Brokers custom flex query
- **mintos**: Mintos CSV
- **n26**: N26 CSV
- **neon**: Neon CSV
- **revolut**: Revolut CSV
- **sbb**: SBB orders CSV
- **splitwise** Splitwise CSV
  - `HouseHoldSplitWiseImporter`: Household
  - `TripSplitWiseImporter`: Trips
- **telegram**: Telegram chat/transaction CSV
- **zkb**: ZKB CSV

## CLI Tools

### Telegram Downloader

The package includes a CLI tool (`beancount-telegram`) to download transaction messages from Telegram chats and format them as CSV files for import with the Telegram importer.

**Installation:**

```bash
pip install beancount-importers[telegram]
```

**Quick Start:**

```bash
beancount-telegram API_ID API_HASH CHAT_ID \
  --root-folder /path/to/records \
  --temp-folder /path/to/temp \
  --account-map Cash=Assets:Cash:CHF
```

For detailed documentation, usage examples, and troubleshooting, see the [CLI README](beancount_importers/cli/README.md).

## Installation

```bash
pip install beancount-importers
```

For Telegram support:

```bash
pip install beancount-importers[telegram]
```

## Development Setup

### Recommended: Using DevContainer

The easiest way to get started is using the pre-configured DevContainer. Simply open the repository in VS Code and select "Reopen in Container" when prompted, or use the Dev Containers extension.

The DevContainer is pre-configured with all dependencies and tools needed for development.

### Manual Setup

1. Clone the repository:

```bash
git clone https://github.com/c-vigo/beancount-importers.git
cd beancount-importers
```

1. Install development dependencies:

```bash
uv sync --dev
```

1. Install pre-commit hooks:

```bash
uv run pre-commit install
```

1. Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=beancount_importers

# Run specific test file
uv run pytest tests/test_base.py

# Run with verbose output
uv run pytest -v
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `uv run pytest`
6. Format your code: `uv run ruff format . && uv run ruff check --fix .`
7. Commit your changes: `git commit -m 'Add feature'`
8. Push to the branch: `git push origin feature-name`
9. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

Carlos Vigo - [carviher1990@gmail.com](mailto:carviher1990@gmail.com)

## Acknowledgments

- [Beancount](https://beancount.github.io/) - The double-entry bookkeeping software
- [Python Packaging Authority](https://www.pypa.io/) - For packaging standards
