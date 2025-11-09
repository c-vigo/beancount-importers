# Beancount Importers

This document provides comprehensive documentation for all importers available in the `beancount-importers` package. Each importer follows the `beangulp.Importer` interface and can be used with tools like `beancount-import` or `beangulp`.

## Table of Contents

- [Overview](#overview)
- [Common Usage Pattern](#common-usage-pattern)
- [Importers](#importers)
  - [CertoOne](#certoone)
  - [Finpension](#finpension)
  - [IBKR (Interactive Brokers)](#ibkr-interactive-brokers)
  - [Mintos](#mintos)
  - [N26](#n26)
  - [Neon](#neon)
  - [Revolut](#revolut)
  - [SBB](#sbb)
  - [Splitwise](#splitwise)
  - [Telegram](#telegram)
  - [ZKB](#zkb)

## Overview

All importers in this package:

- Follow the `beangulp.Importer` interface
- Support file pattern matching for automatic identification
- Generate Beancount `Transaction` entries with proper metadata
- Handle multiple currencies and date formats
- Include comprehensive error handling and warnings

## Common Usage Pattern

All importers are typically used with `beancount-import` or `beangulp`. Here's a general pattern:

```python
from beancount_importers.importers import ibkr_importer, n26_importer

# Configure importers
importers = [
    ibkr_importer.Importer(
        filepattern=r"IBKR.*\.csv$",
        parent_account="Assets:Investments:IBKR",
        income_account="Income:Investments",
        tax_account="Expenses:Taxes",
        fees_account="Expenses:Fees:Brokerage",
    ),
    n26_importer.Importer(
        filepattern=r"N26.*\.csv$",
        account="Assets:Bank:N26",
    ),
]

# Use with beancount-import or beangulp
```

## Importers

### CertoOne

**Description:** Imports transactions from CertoOne credit card PDF statements.

**File Format:** PDF files containing credit card statements.

**Configuration:**

```python
from beancount_importers.importers import certo_one_importer

importer = certo_one_importer.Importer(
    filepattern=r"CertoOne.*\.pdf$",
    account="Liabilities:CreditCard:CertoOne",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match CertoOne PDF files
- `account` (str): Beancount account for the credit card

**Features:**
- Extracts transactions from PDF statements using `camelot-py` and `pypdf`
- Handles balance entries
- Parses dates, amounts, and transaction descriptions
- Supports multiple date formats

**Example Usage:**

```python
importer = certo_one_importer.Importer(
    filepattern=r".*CertoOne.*\.pdf$",
    account="Liabilities:CreditCard:CertoOne",
)
```

**Dependencies:** Requires `camelot-py` and `pypdf` (optional dependencies).

---

### Finpension

**Description:** Imports investment transactions from Finpension CSV files.

**File Format:** CSV files with investment transaction data.

**Configuration:**

```python
from beancount_importers.importers import finpension_importer

importer = finpension_importer.Importer(
    filepattern=r"Finpension.*\.csv$",
    account="Assets:Investments:Finpension",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Finpension CSV files
- `account` (str): Beancount account for Finpension investments

**Features:**
- Handles buy/sell transactions
- Calculates cost basis and proceeds
- Supports FIFO (First-In, First-Out) lot tracking
- Handles dividends and interest

**Example Usage:**

```python
importer = finpension_importer.Importer(
    filepattern=r".*Finpension.*\.csv$",
    account="Assets:Investments:Finpension",
)
```

---

### IBKR (Interactive Brokers)

**Description:** Imports transactions from Interactive Brokers Flex Query CSV files. Supports comprehensive trading activity including stocks, options, dividends, and fees.

**File Format:** CSV files exported from IBKR Flex Query reports with the following columns:
- `Id`, `Date`, `Type`, `Currency`, `Proceeds`, `Security`, `Amount`, `CostBasis`, `TradePrice`, `Commission`, `CommissionCurrency`

**Configuration:**

```python
from beancount_importers.importers import ibkr_importer

importer = ibkr_importer.Importer(
    filepattern=r"IBKR.*\.csv$",
    parent_account="Assets:Investments:IBKR",
    income_account="Income:Investments",
    tax_account="Expenses:Taxes",
    fees_account="Expenses:Fees:Brokerage",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match IBKR CSV files
- `parent_account` (str): Base account for IBKR (creates sub-accounts like `{parent_account}:Cash`)
- `income_account` (str): Base account for investment income (creates `{income_account}:Interests`)
- `tax_account` (str): Account for withholding taxes
- `fees_account` (str): Account for brokerage fees and commissions

**Features:**
- **Transaction Types Supported:**
  - `BUY`: Stock/security purchases
  - `SELL`: Stock/security sales with FIFO cost basis calculation
  - `Dividends`: Dividend payments
  - `Withholding Tax`: Tax withholding on dividends
  - `Deposits/Withdrawals`: Cash movements
  - `FX Exchange`: Foreign exchange transactions
  - `Broker Interest Received`: Interest on cash balances
  - `Other Fees`: Various fees and commissions

- **FIFO Logic:** Automatically calculates profit/loss on sales using First-In, First-Out inventory tracking
- **Multi-Currency Support:** Handles transactions in different currencies
- **Cost Basis Tracking:** Maintains accurate cost basis for tax reporting

**Example Usage:**

```python
importer = ibkr_importer.Importer(
    filepattern=r".*IBKR.*\.csv$",
    parent_account="Assets:Investments:IBKR",
    income_account="Income:Investments",
    tax_account="Expenses:Taxes:Withholding",
    fees_account="Expenses:Fees:Brokerage",
)
```

**Transaction Examples:**

- **Stock Purchase:**
  ```
  2024-01-15 * "BUY 10 VEA @ 46.925"
    Assets:Investments:IBKR:VEA    10 VEA {46.925 USD}
    Assets:Investments:IBKR:Cash   -469.25 USD
  ```

- **Stock Sale with P&L:**
  ```
  2024-02-15 * "SELL 5 VEA @ 48.00"
    Assets:Investments:IBKR:Cash    240.00 USD
    Assets:Investments:IBKR:VEA    -5 VEA {46.925 USD} @ 48.00 USD
    Income:Investments:PnL          -5.375 USD
  ```

- **Dividend:**
  ```
  2024-03-15 * "Dividend VEA"
    Assets:Investments:IBKR:Cash    12.50 USD
    Income:Investments:Dividends   -12.50 USD
  ```

---

### Mintos

**Description:** Imports peer-to-peer lending transactions from Mintos CSV files.

**File Format:** CSV files with columns: `Date`, `Details`, `Turnover`

**Configuration:**

```python
from beancount_importers.importers import mintos_importer

importer = mintos_importer.Importer(
    filepattern=r"Mintos.*\.csv$",
    account="Assets:Investments:Mintos",
    income_account="Income:Investments:Mintos",
    fees_account="Expenses:Fees:Investments",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Mintos CSV files
- `account` (str): Beancount account for Mintos investments
- `income_account` (str): Account for investment income (dividends, interest)
- `fees_account` (str): Account for fees

**Features:**
- **Transaction Types:**
  - `Deposit`: Capital deposits
  - `Removal`: Capital withdrawals
  - `Buy`: Investment in loans
  - `Sell`: Principal received from loan payback
  - `Dividend`: Interest and late fees received
  - `Interest`: Secondary market discounts, campaign bonuses
  - `Fees`: Secondary market transaction fees
  - `Repurchase`: Principal from repurchase of small loan parts

- Automatically categorizes transactions based on description
- Handles secondary market transactions
- Tracks principal and interest separately

**Example Usage:**

```python
importer = mintos_importer.Importer(
    filepattern=r".*Mintos.*\.csv$",
    account="Assets:Investments:Mintos",
    income_account="Income:Investments:Mintos",
    fees_account="Expenses:Fees:Investments",
)
```

---

### N26

**Description:** Imports bank transactions from N26 CSV export files.

**File Format:** CSV files with columns: `Booking Date`, `Value Date`, `Partner Name`, `Partner Iban`, `Type`, `Payment Reference`, `Account Name`, `Amount (EUR)`, `Original Amount`, `Original Currency`, `Exchange Rate`

**Configuration:**

```python
from beancount_importers.importers import n26_importer

importer = n26_importer.Importer(
    filepattern=r"N26.*\.csv$",
    account="Assets:Bank:N26",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match N26 CSV files
- `account` (str): Beancount account for N26 bank account

**Features:**
- Handles EUR and foreign currency transactions
- Extracts partner information (name, IBAN)
- Parses payment references
- Supports exchange rate conversion

**Example Usage:**

```python
importer = n26_importer.Importer(
    filepattern=r".*N26.*\.csv$",
    account="Assets:Bank:N26",
)
```

---

### Neon

**Description:** Imports bank transactions from Neon CSV files with optional payee mapping.

**File Format:** CSV files with transaction data.

**Configuration:**

```python
from beancount_importers.importers import neon_importer

importer = neon_importer.Importer(
    filepattern=r"Neon.*\.csv$",
    account="Assets:Bank:Neon",
    map={
        "PAYEE_NAME": ("Expenses:Category", "Description"),
    },
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Neon CSV files
- `account` (str): Beancount account for Neon bank account
- `map` (dict, optional): Dictionary mapping payee names to `(account, description)` tuples

**Features:**
- Payee mapping for automatic categorization
- Custom description generation
- Supports multiple currencies

**Example Usage:**

```python
importer = neon_importer.Importer(
    filepattern=r".*Neon.*\.csv$",
    account="Assets:Bank:Neon",
    map={
        "COOP": ("Expenses:Groceries", "COOP Supermarket"),
        "Migros": ("Expenses:Groceries", "Migros Supermarket"),
    },
)
```

---

### Revolut

**Description:** Imports transactions from Revolut CSV export files.

**File Format:** CSV files with Revolut transaction data.

**Configuration:**

```python
from beancount_importers.importers import revolut_importer

importer = revolut_importer.Importer(
    filepattern=r"Revolut.*\.csv$",
    account="Assets:Bank:Revolut",
    fee_account="Expenses:Fees:Banking",
    currency="EUR",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Revolut CSV files
- `account` (str): Beancount account for Revolut account
- `fee_account` (str): Account for banking fees
- `currency` (str): Default currency for transactions

**Features:**
- Handles fees separately
- Multi-currency support
- Extracts merchant information

**Example Usage:**

```python
importer = revolut_importer.Importer(
    filepattern=r".*Revolut.*\.csv$",
    account="Assets:Bank:Revolut",
    fee_account="Expenses:Fees:Banking",
    currency="EUR",
)
```

---

### SBB

**Description:** Imports SBB (Swiss Federal Railways) ticket purchases from CSV files.

**File Format:** CSV files with columns: `Tariff`, `Route`, `Via (optional)`, `Price`, `Co-passenger(s)`, `Travel date`, `Validity`, `Order date`, `Order number`, `Payment methods`, `Purchaser e-mail`

**Configuration:**

```python
from beancount_importers.importers import sbb_importer

importer = sbb_importer.Importer(
    filepattern=r"SBB.*\.csv$",
    account="Expenses:Transport:Train",
    owner="your-email@example.com",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match SBB CSV files
- `account` (str): Beancount account for train expenses
- `owner` (str): Email address to filter transactions (only imports tickets purchased by this email)

**Features:**
- Filters transactions by purchaser email
- Constructs transaction descriptions from tariff, route, and via information
- Handles multiple date formats (`DD.MM.YYYY` and `YYYY-MM-DD`)
- Includes metadata: order number, traveller, email, travel date, tariff, route

**Example Usage:**

```python
importer = sbb_importer.Importer(
    filepattern=r".*SBB.*\.csv$",
    account="Expenses:Transport:Train",
    owner="carviher1990@gmail.com",
)
```

**Transaction Example:**

```
2024-01-20 * "ZVV Single Ticket: Zürich HB → Bern"
    Expenses:Transport:Train    25.50 CHF
    Assets:Bank:ZKB            -25.50 CHF
    orderno: "12345678"
    traveller: "Person A"
    email: "person@example.com"
    travel_date: 2024-01-20
    tariff: "ZVV Single Ticket"
    route: "Zürich HB → Bern"
```

---

### Splitwise

**Description:** Imports expense splits from Splitwise CSV files. Two separate importers are available for different use cases.

#### HouseHoldSplitWiseImporter

**Description:** For household expense splits between two people.

**File Format:** CSV files with household expense data (two people).

**Configuration:**

```python
from beancount_importers.importers import splitwise_hh_importer

importer = splitwise_hh_importer.HouseHoldSplitWiseImporter(
    filepattern=r"Splitwise.*Household.*\.csv$",
    account="Expenses:Household",
    owner="Person A",
    partner="Person B",
    account_map={
        "Groceries": "Expenses:Groceries",
        "Restaurants": "Expenses:Dining",
    },
    tag="household",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Splitwise CSV files
- `account` (str): Base account for expenses
- `owner` (str): Name of the owner (must match CSV header)
- `partner` (str): Name of the partner (must match CSV header)
- `account_map` (dict, optional): Maps Splitwise category names to Beancount accounts
- `tag` (str, optional): Tag to apply to all transactions

**Features:**
- Handles expense splits between two people
- Creates transactions for both owner and partner shares
- Supports category mapping
- Optional tagging

**Example Usage:**

```python
importer = splitwise_hh_importer.HouseHoldSplitWiseImporter(
    filepattern=r".*Splitwise.*Household.*\.csv$",
    account="Expenses:Household",
    owner="Carlos",
    partner="Maria",
    account_map={
        "Groceries": "Expenses:Groceries",
        "Utilities": "Expenses:Utilities",
    },
    tag="household",
)
```

#### TripSplitWiseImporter

**Description:** For trip/group expense splits.

**File Format:** CSV files with trip expense data (multiple people).

**Configuration:**

```python
from beancount_importers.importers import splitwise_trip_importer

importer = splitwise_trip_importer.TripSplitWiseImporter(
    filepattern=r"Splitwise.*Trip.*\.csv$",
    account="Expenses:Travel",
    owner="Person A",
    account_map={
        "Food": "Expenses:Travel:Food",
        "Transport": "Expenses:Travel:Transport",
    },
    tag="trip-paris-2024",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Splitwise CSV files
- `account` (str): Base account for expenses
- `owner` (str): Name of the owner (must match CSV header)
- `account_map` (dict, optional): Maps Splitwise category names to Beancount accounts
- `tag` (str, optional): Tag to apply to all transactions

**Features:**
- Handles expense splits among multiple people
- Creates transactions for owner's share only
- Supports category mapping
- Optional tagging for trip identification

**Example Usage:**

```python
importer = splitwise_trip_importer.TripSplitWiseImporter(
    filepattern=r".*Splitwise.*Trip.*\.csv$",
    account="Expenses:Travel",
    owner="Carlos",
    account_map={
        "Food": "Expenses:Travel:Food",
        "Transport": "Expenses:Travel:Transport",
        "Accommodation": "Expenses:Travel:Accommodation",
    },
    tag="trip-paris-2024",
)
```

---

### Telegram

**Description:** Imports transactions from Telegram CSV files (generated by the `beancount-telegram` CLI tool).

**File Format:** CSV files with semicolon-delimited columns: `id`, `sender`, `message_date`, `transaction_date`, `account`, `payee`, `description`, `amount`, `currency`, `tag`

**Configuration:**

```python
from beancount_importers.importers import telegram_importer

importer = telegram_importer.Importer(
    filepattern=r"Telegram.*\.csv$",
    account="Assets:Cash",
    map={
        "Assets:Cash": ("Assets:Cash:CHF", "Cash transaction"),
        "Assets:Bank": ("Assets:Bank:EUR", "Bank transaction"),
    },
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match Telegram CSV files
- `account` (str): Default Beancount account for transactions
- `map` (dict, optional): Dictionary mapping Telegram account names to `(beancount_account, description)` tuples

**Features:**
- Payee mapping from Telegram account names to Beancount accounts
- Tag support (removes leading `#` from tags)
- Handles multiple currencies
- Extracts metadata: sender, message date, transaction date

**Example Usage:**

```python
importer = telegram_importer.Importer(
    filepattern=r".*Telegram.*\.csv$",
    account="Assets:Cash",
    map={
        "Cash": ("Assets:Cash:CHF", "Cash transaction"),
        "Bank": ("Assets:Bank:EUR", "Bank transaction"),
        "Credit": ("Liabilities:CreditCard", "Credit card transaction"),
    },
)
```

**Transaction Example:**

```
2024-01-15 * "Grocery Shopping" #food
    Expenses:Groceries    50.00 CHF
    Assets:Cash:CHF      -50.00 CHF
    sender: "User"
    message_date: 2024-01-15
    transaction_date: 2024-01-14
```

**Related:** See [CLI README](../cli/README.md) for information on the `beancount-telegram` tool that generates these CSV files.

---

### ZKB

**Description:** Imports bank transactions from ZKB (Zürcher Kantonalbank) CSV files.

**File Format:** CSV files with ZKB transaction data.

**Configuration:**

```python
from beancount_importers.importers import zkb_importer

importer = zkb_importer.ZkbCSVImporter(
    filepattern=r"ZKB.*\.csv$",
    account="Assets:Bank:ZKB",
)
```

**Parameters:**
- `filepattern` (str): Regular expression pattern to match ZKB CSV files
- `account` (str): Beancount account for ZKB bank account

**Features:**
- Handles Swiss bank transaction formats
- Parses dates and amounts
- Extracts transaction descriptions

**Example Usage:**

```python
importer = zkb_importer.ZkbCSVImporter(
    filepattern=r".*ZKB.*\.csv$",
    account="Assets:Bank:ZKB",
)
```

---

## Integration with beancount-import

To use these importers with `beancount-import`, create a configuration file:

```python
# config.py
from beancount_importers.importers import (
    ibkr_importer,
    n26_importer,
    sbb_importer,
)

CONFIG = [
    ibkr_importer.Importer(
        filepattern=r".*IBKR.*\.csv$",
        parent_account="Assets:Investments:IBKR",
        income_account="Income:Investments",
        tax_account="Expenses:Taxes:Withholding",
        fees_account="Expenses:Fees:Brokerage",
    ),
    n26_importer.Importer(
        filepattern=r".*N26.*\.csv$",
        account="Assets:Bank:N26",
    ),
    sbb_importer.Importer(
        filepattern=r".*SBB.*\.csv$",
        account="Expenses:Transport:Train",
        owner="your-email@example.com",
    ),
]
```

Then run:

```bash
beancount-import config.py /path/to/beancount/file.beancount
```

## Integration with beangulp

To use with `beangulp`, create a script:

```python
# importers.py
from beangulp import importer
from beancount_importers.importers import (
    ibkr_importer,
    n26_importer,
)

IMPORTERS = [
    ibkr_importer.Importer(
        filepattern=r".*IBKR.*\.csv$",
        parent_account="Assets:Investments:IBKR",
        income_account="Income:Investments",
        tax_account="Expenses:Taxes:Withholding",
        fees_account="Expenses:Fees:Brokerage",
    ),
    n26_importer.Importer(
        filepattern=r".*N26.*\.csv$",
        account="Assets:Bank:N26",
    ),
]

if __name__ == "__main__":
    importer.main(IMPORTERS)
```

## Troubleshooting

### Common Issues

1. **File Not Identified:**
   - Check that your `filepattern` regex matches the file path
   - Use `.*` for flexible matching: `r".*IBKR.*\.csv$"`

2. **Missing Transactions:**
   - Check for warnings in the output
   - Verify CSV format matches expected structure
   - Check date formats (some importers are strict)

3. **Currency Issues:**
   - Ensure currency codes match Beancount conventions (e.g., `USD`, `EUR`, `CHF`)
   - Check for currency conversion entries

4. **Account Mapping:**
   - Verify account names match your Beancount account structure
   - Check for typos in account names

### Getting Help

- Check the test files in `tests/` for examples of expected CSV formats
- Review sample CSV files in test directories
- Open an issue on GitHub with:
  - Sample CSV data (anonymized)
  - Error messages or warnings
  - Your importer configuration

## Contributing

To add a new importer:

1. Create a new file in `beancount_importers/importers/`
2. Implement the `beangulp.Importer` interface
3. Add tests in `tests/`
4. Create a sample CSV file (anonymized)
5. Update this README
6. Update `beancount_importers/importers/__init__.py`

See existing importers for reference implementations.
