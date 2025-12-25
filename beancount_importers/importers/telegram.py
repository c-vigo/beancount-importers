import csv
import re
import warnings
from datetime import date, datetime
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D
from dateutil.parser import parse


class Importer(beangulp.Importer):
    """An importer for Telegram downloader."""

    def __init__(
        self,
        filepattern: str,
        account: str,
        map: dict[str, tuple[str, str]] | None = None,
    ):
        self._filepattern = filepattern
        self._account = account
        self.map = map or {}

    def identify(self, filepath: str | Any) -> bool:
        """Identify if the file matches the pattern."""
        # Handle both string filepaths and _FileMemo objects from beancount-import
        path = (
            getattr(filepath, "filepath", None)
            or getattr(filepath, "name", None)
            or getattr(filepath, "filename", None)
            or str(filepath)
        )
        return re.search(self._filepattern, path) is not None

    def name(self) -> str:
        """Return the name of the importer."""
        return f"telegram.{self.account()}"

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a Telegram CSV file."""
        entries: data.Entries = []

        # Handle both string filepaths and _FileMemo objects
        path = (
            getattr(filepath, "filepath", None)
            or getattr(filepath, "name", None)
            or getattr(filepath, "filename", None)
            or str(filepath)
        )

        try:
            with open(path, encoding="utf-8") as csvfile:
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
                rows = list(reader)[1:]

            for index, row in enumerate(reversed(rows)):
                try:
                    # Parse entry
                    meta = data.new_metadata(path, index)
                    parsed_date = parse(row["transaction_date"].strip())
                    if isinstance(parsed_date, datetime):
                        book_date = parsed_date.date()
                    elif isinstance(parsed_date, date):
                        book_date = parsed_date
                    else:
                        book_date = date.today()
                    amt = amount.Amount(D(row["amount"]), row["currency"])
                    note = row["description"].strip()
                    payee = row["payee"].strip()
                    tag_str = row["tag"].strip()

                    # Handle tags
                    if tag_str == "":
                        tags = data.EMPTY_SET
                    else:
                        # Remove leading # if present
                        tag_clean = tag_str[1:] if tag_str.startswith("#") else tag_str
                        tags = frozenset([tag_clean])

                    # Apply mapping if available
                    if payee in self.map:
                        payee, note = self.map[payee]

                    # Transaction or balance?
                    if payee == "Balance":
                        entries.append(
                            data.Balance(
                                meta, book_date, self._account, amt, None, None
                            )
                        )
                    else:
                        entries.append(
                            data.Transaction(
                                meta,
                                book_date,
                                "*",
                                payee if payee else None,
                                note,
                                tags,
                                data.EMPTY_SET,
                                [
                                    data.Posting(
                                        self._account, amt, None, None, None, None
                                    ),
                                ],
                            )
                        )

                except Exception as e:
                    warnings.warn(
                        f"Error parsing line {row}\n{e}",
                        stacklevel=2,
                    )

        except FileNotFoundError:
            warnings.warn(
                f"File not found: {path}",
                stacklevel=2,
            )
        except Exception as e:
            warnings.warn(
                f"Error reading CSV file {path}: {e}",
                stacklevel=2,
            )

        return entries
