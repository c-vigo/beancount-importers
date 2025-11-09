# Telegram Downloader CLI

The `beancount-telegram` CLI tool downloads transaction messages from Telegram chats and formats them as CSV files for import with the Telegram importer.

## Installation

Install the package with Telegram support:

```bash
pip install beancount-importers[telegram]
```

## Usage

```bash
beancount-telegram API_ID API_HASH CHAT_ID [OPTIONS]
```

## Required Arguments

- `API_ID`: Your Telegram API ID (obtained from https://my.telegram.org)
- `API_HASH`: Your Telegram API hash (obtained from https://my.telegram.org)
- `CHAT_ID`: The Telegram chat ID to download messages from

## Options

- `-r, --root-folder PATH`: The Beancount records root folder where CSV files will be saved
- `-t, --temp-folder PATH`: The Beancount temporary records folder for uncategorized attachments
- `-acc, --account-map MAPPINGS`: Map Telegram account names to Beancount accounts (format: `name=account`, can be specified multiple times)
- `-att, --attachment-map PATTERNS`: Configure attachment download patterns (format: `account;pattern;skip_init;skip_end;name`, can be specified multiple times)
- `-s, --session-file PATH`: Path to Telegram session file (default: `~/.config/beancount_telegram/telegram.session`)
- `-f, --force`: Force re-download of all transactions (even if already downloaded)
- `-nd, --no-download`: Skip downloading attachments
- `-n, --dry-run`: Perform a dry run without modifying any files
- `-c, --check`: Check access to Telegram chat and display chat info, then exit

## Examples

### Check Connection

Check your Telegram connection and display chat information:

```bash
beancount-telegram 12345 abcdef123456 67890 --check
```

### Basic Download

Download transactions with account mapping:

```bash
beancount-telegram 12345 abcdef123456 67890 \
  --root-folder ~/Documents/beancount/Records \
  --temp-folder ~/Documents/beancount/Temp \
  --account-map Cash=Assets:Cash:CHF \
  --account-map Bank=Assets:Bank:EUR
```

### Using Short Options

Same as above, but using short option names:

```bash
beancount-telegram 12345 abcdef123456 67890 \
  -r ~/Documents/beancount/Records \
  -t ~/Documents/beancount/Temp \
  -acc Cash=Assets:Cash:CHF Bank=Assets:Bank:EUR
```

### Download with Attachment Patterns

Configure how attachments are downloaded and named:

```bash
beancount-telegram 12345 abcdef123456 67890 \
  -r ~/Documents/beancount/Records \
  -t ~/Documents/beancount/Temp \
  -acc Cash=Assets:Cash:CHF \
  -att Assets:Cash:CHF;*.pdf;0;10;receipt
```

### Dry Run

See what would be downloaded without making any changes:

```bash
beancount-telegram 12345 abcdef123456 67890 \
  -r ~/Documents/beancount/Records \
  -t ~/Documents/beancount/Temp \
  --dry-run
```

## Attachment Pattern Format

The `--attachment-map` option allows you to configure how attachments are downloaded and named. The format is:

```
account;pattern;skip_init;skip_end;name
```

Where:
- `account`: Beancount account name
- `pattern`: Filename pattern to match (e.g., `*.pdf`, `receipt_*.jpg`)
- `skip_init`: Start position for date extraction from filename
- `skip_end`: End position for date extraction from filename
- `name`: Base name for downloaded file

### Example

For a file named `receipt_20240115_123456.pdf`, with pattern `receipt_*.pdf` and `skip_init=8, skip_end=16`, the date `20240115` would be extracted from positions 8-16 of the filename.

## Getting Telegram API Credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application (if you haven't already)
5. Copy your `api_id` and `api_hash`

## Finding Your Chat ID

You can find your chat ID by:
- Using the `--check` option with a known chat ID
- Using Telegram bots that display chat information
- Checking Telegram client logs or using Telegram's API

## Session Management

The tool stores your Telegram session in a file (default: `~/.config/beancount_telegram/telegram.session`). This allows you to stay logged in without re-entering your credentials. You can specify a custom session file path with `--session-file`.

## Troubleshooting

### Connection Issues

- Ensure your API credentials are correct
- Check your internet connection
- Verify the chat ID is correct using `--check`

### Permission Errors

- Ensure you have read access to the chat
- Check that the chat ID corresponds to a chat you have access to

### File Download Issues

- Check that the destination folders exist and are writable
- Use `--dry-run` to see what would be downloaded
- Use `--no-download` to skip attachments if needed
