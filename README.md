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

1. Clone the repository:
```bash
git clone https://github.com/c-vigo/beancount-importers.git
cd beancount-importers
```

2. Create a virtual environment:
```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:
```bash
pre-commit install
```

5. Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=beancount_importers

# Run specific test file
pytest tests/test_base.py

# Run with verbose output
pytest -v
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `pytest`
6. Format your code: `black src tests && isort src tests`
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
