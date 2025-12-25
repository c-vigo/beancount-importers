"""Telegram chat history archiver for Beancount.

This module provides a CLI tool to download transaction messages from Telegram
and format them as CSV files compatible with the Telegram importer.
"""

import csv
import sys
from argparse import Action, ArgumentError, ArgumentParser, ArgumentTypeError
from collections.abc import Sequence
from datetime import date, datetime
from fnmatch import fnmatch
from os import remove
from os.path import expanduser, isfile
from pathlib import Path
from typing import Any

from dateutil import parser
from telethon.sync import TelegramClient

# Package metadata
MODULE_NAME = "beancount-telegram"
DESCRIPTION = "Download Telegram chat messages and format them for Beancount import"
DOCS_URL = "https://github.com/c-vigo/beancount-importers"


class AttachmentPattern:
    """Pattern for matching and processing Telegram attachments."""

    def __init__(
        self,
        account: str,
        pattern: str,
        skip_init: int,
        skip_end: int,
        name: str,
    ) -> None:
        """Initialize attachment pattern.

        Args:
            account: Beancount account name
            pattern: Filename pattern to match
            skip_init: Start position for date extraction
            skip_end: End position for date extraction
            name: Base name for downloaded file
        """
        self.account = account
        self.pattern = pattern
        self.skip_init = skip_init
        self.skip_end = skip_end
        self.name = name

    def __str__(self) -> str:
        """Return string representation."""
        return (
            f"(Account {self.account}; Pattern {self.pattern}, "
            f"Skip {self.skip_init}-{self.skip_end}, Name {self.name})"
        )


class ParseAttachmentPattern(Action):
    """Argument parser action for attachment patterns."""

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Any,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Parse attachment pattern arguments."""
        # First pattern?
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, [])

        # Add pattern
        if values is None:
            return
        if isinstance(values, str):
            values = [values]
        try:
            for value in values:
                if not isinstance(value, str):
                    raise ValueError(f"Expected string, got {type(value)}")
                parts = value.split(";")
                if len(parts) != 5:
                    raise ValueError("Invalid attachment pattern format")
                account, pattern, skip_init, skip_end, name = parts
                getattr(namespace, self.dest).append(
                    AttachmentPattern(
                        account, pattern, int(skip_init), int(skip_end), name
                    )
                )
        except (ValueError, IndexError) as e:
            raise ArgumentTypeError(f"Invalid attachment pattern: {e}") from e


class ParseDict(Action):
    """Argument parser action for dictionary arguments."""

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Any,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        """Parse dictionary arguments."""
        if values is None:
            setattr(namespace, self.dest, {})
            return
        if isinstance(values, str):
            values = [values]
        result = {}
        for value in values:
            if not isinstance(value, str):
                raise ArgumentTypeError(
                    f"Invalid format: {value}. Expected string, got {type(value)}"
                )
            if "=" not in value:
                raise ArgumentTypeError(f"Invalid format: {value}. Expected key=value")
            key, val = value.split("=", 1)
            result[key] = val
        setattr(namespace, self.dest, result)


def build_file_name(account: str, year: str, args: Any) -> str:
    """Build CSV filename for an account and year.

    Args:
        account: Account name
        year: Year string
        args: Parsed arguments containing account_map and root_folder

    Returns:
        Full path to CSV file

    Raises:
        KeyError: If account is not in account_map
    """
    if account not in args.account_map:
        raise KeyError(f"Account '{account}' not found in account map")
    account_info = args.account_map[account]
    base_folder = Path(args.root_folder) / account_info.replace(":", "/")
    filename = f"{year}-12-31-{account.replace(' ', '')}_Transactions_TelegramBot.csv"
    return str(base_folder / filename)


def check_connection(args: Any) -> None:
    """Check Telegram connection and display chat information.

    Args:
        args: Parsed arguments containing session_file, api_id, api_hash, chat_id
    """
    print("Connecting to Telegram client...")
    client = TelegramClient(args.session_file, args.api_id, args.api_hash)
    with client:
        # Loop over messages
        the_chat = client.get_entity(args.chat_id)  # type: ignore[attr-defined]
        # get_entity works synchronously in sync mode, but type checker doesn't know
        print(f"Chat name: {the_chat.title}")  # type: ignore[attr-defined]
        for msg in client.iter_messages(args.chat_id, reverse=False, limit=1):
            print(f"Last message ({msg.date}): {msg.text}")


def beancount_telegram() -> None:
    """Main CLI routine for Telegram downloader.

    Parses command-line arguments and downloads/processes Telegram messages
    to create CSV files compatible with the Telegram importer.
    """
    fieldnames = [
        "id",
        "sender",
        "message_date",
        "transaction_date",
        "account",
        "payee",
        "description",
        "amount",
        "currency",
        "tag",
    ]

    # The argument parser
    ap = ArgumentParser(
        prog=MODULE_NAME,
        description=DESCRIPTION,
        add_help=True,
        epilog=f"Check out the package documentation for more information:\n{DOCS_URL}",
    )

    # Arguments:
    # API ID
    ap.add_argument(
        "api_id",
        help="The API ID you obtained from https://my.telegram.org",
        type=int,
    )
    # API hash
    ap.add_argument(
        "api_hash",
        help="The API hash you obtained from https://my.telegram.org",
        type=str,
    )
    # Chat ID
    ap.add_argument(
        "chat_id",
        help="The chat ID",
        type=int,
    )
    # Root Folder
    root_arg = ap.add_argument(
        "-r",
        "--root-folder",
        help="The beancount records root folder",
        type=str,
    )
    # Uncategorized attachment path
    tmp_arg = ap.add_argument(
        "-t",
        "--temp-folder",
        help="The beancount temporary records folder",
        type=str,
    )
    # Account map
    acc_arg = ap.add_argument(
        "-acc",
        "--account-map",
        nargs="*",
        action=ParseDict,
        help="Account mapping in format: account_name=beancount_account",
    )
    # Attachments map
    ap.add_argument(
        "-att",
        "--attachment-map",
        nargs="*",
        action=ParseAttachmentPattern,
        help=(
            "Attachment pattern mapping in format: "
            "account;pattern;skip_init;skip_end;name"
        ),
    )
    # Session file
    ap.add_argument(
        "-s",
        "--session-file",
        help="Session file to store credentials",
        type=str,
        default=expanduser("~/.config/beancount_telegram/telegram.session"),
    )
    # Force update
    ap.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force re-download of old transactions",
        default=False,
    )
    # Download files
    ap.add_argument(
        "-and",
        "--no-download",
        action="store_true",
        help="Do not download files",
        default=False,
    )
    # Dry run
    ap.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Perform a dry run without altering any file",
        default=False,
    )
    # Check connection
    ap.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="Check access to Telegram chat and quit",
        default=False,
    )

    # Parse the arguments
    args = ap.parse_args()

    # Create session file directory if it does not exist
    Path(args.session_file).parent.mkdir(parents=True, exist_ok=True)

    # Check connection?
    if args.check:
        check_connection(args)
        return

    # Mandatory arguments
    if args.account_map is None:
        raise ArgumentError(acc_arg, "Missing account map")
    if not args.no_download:
        if args.root_folder is None:
            raise ArgumentError(root_arg, "Missing beancount records root folder")
        if args.temp_folder is None:
            raise ArgumentError(tmp_arg, "Missing beancount records temporary folder")

    last_message_id = 0
    if args.force and not args.dry_run:
        # Clean files if --force
        print("Cleaning old files...")
        for account in args.account_map.keys():
            filename = build_file_name(account, "2022", args)
            if isfile(filename):
                print(f"Deleting {filename}")
                remove(filename)
    else:
        # Only update files, find the latest message in saved files
        for account in args.account_map.keys():
            for year in range(2022, 2300):
                try:
                    filename = build_file_name(account, str(year), args)
                    if isfile(filename):
                        with open(filename, encoding="utf-8") as csvfile:
                            reader = csv.DictReader(
                                csvfile,
                                [
                                    "id",
                                    "sender",
                                    "message_date",
                                    "transaction_date",
                                    "account",
                                    "payee",
                                    "description",
                                    "amount",
                                    "currency",
                                    "tag",
                                ],
                                delimiter=";",
                            )
                            rows = list(reader)[1:]  # Skip header
                            for row in rows:
                                try:
                                    message_id = int(row["id"])
                                    if message_id > last_message_id:
                                        last_message_id = message_id
                                except (ValueError, KeyError):
                                    continue
                except (KeyError, OSError):
                    # File doesn't exist or can't be read, continue
                    continue
        print(f"Updating messages with ID > {last_message_id}")

    # Connect to the Telegram client
    client = TelegramClient(args.session_file, args.api_id, args.api_hash)
    with client:
        # Loop over messages
        for msg in client.iter_messages(
            args.chat_id, reverse=True, min_id=last_message_id
        ):
            # Retrieve message info
            if msg.sender is None:
                print(f"Warning: Message {msg.id} has no sender, skipping")
                continue

            sender_name = msg.sender.first_name.strip() if msg.sender.first_name else ""
            message_date_str = msg.date.strftime("%Y-%m-%d") if msg.date else ""
            entry: dict[str, str] = {
                "id": str(msg.id),
                "sender": sender_name,
                "message_date": message_date_str,
            }

            # Parse fields of a valid transaction
            transaction_parsed = False
            if msg.text:
                try:
                    # Parse message text
                    fields = msg.text.split(";")
                    if len(fields) < 5:
                        raise ValueError("Not enough fields in transaction message")

                    parsed_date = parser.parse(fields[0])
                    if isinstance(parsed_date, datetime):
                        entry["transaction_date"] = parsed_date.strftime("%Y-%m-%d")
                    elif isinstance(parsed_date, date):
                        entry["transaction_date"] = parsed_date.strftime("%Y-%m-%d")
                    else:
                        # Fallback for unexpected types
                        entry["transaction_date"] = str(parsed_date)
                    entry["account"] = fields[1].strip().replace(" ", "")
                    entry["payee"] = fields[2].strip()
                    entry["description"] = fields[3].strip()
                    amount_parts = fields[4].strip().split(" ")
                    if len(amount_parts) < 2:
                        raise ValueError("Invalid amount format")
                    entry["amount"] = amount_parts[0].strip()
                    entry["currency"] = amount_parts[1].strip()
                    entry["tag"] = fields[5].strip() if len(fields) > 5 else ""

                    # Identify account
                    if entry["account"] not in args.account_map:
                        print(
                            f"Warning: Invalid account <{entry['account']}> "
                            f"in message <{msg.text}> from {entry['message_date']}"
                        )
                        continue

                    # File name associated to transaction
                    filename = build_file_name(
                        entry["account"], entry["transaction_date"][0:4], args
                    )

                    # Ensure directory exists
                    Path(filename).parent.mkdir(parents=True, exist_ok=True)

                    # Dry run?
                    if args.dry_run:
                        print(f"{filename}: {entry}")
                        transaction_parsed = True
                        continue

                    # Create new file?
                    if not isfile(filename):
                        print(f"Creating file {filename}")
                        with open(filename, "w", encoding="UTF-8", newline="") as f:
                            # Create the csv writer and write the header
                            writer = csv.DictWriter(
                                f, fieldnames=fieldnames, delimiter=";"
                            )
                            writer.writeheader()

                            # Write the entry
                            writer.writerow(entry)
                    # Open file to append entry
                    else:
                        with open(filename, "a", encoding="UTF-8", newline="") as f:
                            # Create the csv writer and append the entry
                            writer = csv.DictWriter(
                                f, fieldnames=fieldnames, delimiter=";"
                            )
                            writer.writerow(entry)

                    # Parsing successful
                    transaction_parsed = True
                    continue

                except (ValueError, IndexError, parser.ParserError):
                    # Not a valid transaction, try attachments
                    pass

            # Attachments
            if not transaction_parsed and msg.document:
                try:
                    document = msg.document
                    if not document.attributes or not hasattr(
                        document.attributes[0], "file_name"
                    ):
                        continue

                    name = document.attributes[0].file_name
                    if not name:
                        continue

                    extension = name[-4:] if len(name) >= 4 else ""

                    # Download?
                    if args.no_download:
                        continue

                    # Pattern matching
                    attachment_handled = False
                    if args.attachment_map:
                        for pattern in args.attachment_map:
                            if fnmatch(name, pattern.pattern):
                                try:
                                    # Parse date
                                    date_str = parser.isoparse(
                                        name[pattern.skip_init : pattern.skip_end]
                                    ).strftime("%Y-%m-%d")

                                    # Build filename
                                    account_path = pattern.account.replace(":", "/")
                                    base_folder = Path(args.root_folder) / account_path
                                    filename = str(
                                        base_folder
                                        / f"{date_str}-{pattern.name}{extension}"
                                    )

                                    # Handle duplicates
                                    if isfile(filename):
                                        filename = filename[:-4] + "_2" + filename[-4:]

                                    # Ensure directory exists
                                    Path(filename).parent.mkdir(
                                        parents=True, exist_ok=True
                                    )

                                    # Download file?
                                    if args.dry_run:
                                        real_filename = filename
                                    else:
                                        real_filename = client.download_media(
                                            message=msg, file=filename
                                        )
                                    print(f"File downloaded: {real_filename}")
                                    attachment_handled = True
                                    break

                                except (ValueError, IndexError, parser.ParserError):
                                    continue

                    if not attachment_handled:
                        # File does not match any pattern
                        filename = str(Path(args.temp_folder) / name)
                        if isfile(filename):
                            filename = filename[:-4] + "_2" + filename[-4:]

                        # Ensure directory exists
                        Path(filename).parent.mkdir(parents=True, exist_ok=True)

                        if args.dry_run:
                            real_filename = filename
                        else:
                            real_filename = client.download_media(
                                message=msg, file=filename
                            )
                        print(f"File downloaded: {real_filename}")
                    continue

                except (AttributeError, IndexError, OSError):
                    pass

            if not transaction_parsed:
                print(
                    f"Warning: Invalid message <{msg.text}> "
                    f"from {entry['message_date']}"
                )


def main() -> None:
    """Entry point for the CLI command."""
    try:
        beancount_telegram()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
