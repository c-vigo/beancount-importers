import csv
import re
import warnings
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D
from dateutil.parser import parse


class Importer(beangulp.Importer):
    """An importer for Neon CSV files."""

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
        if hasattr(filepath, "filepath"):
            path = filepath.filepath
        elif hasattr(filepath, "name"):
            path = filepath.name
        elif hasattr(filepath, "filename"):
            path = filepath.filename
        else:
            path = str(filepath)
        return re.search(self._filepattern, path) is not None

    def name(self) -> str:
        """Return the name of the importer."""
        return f"neon.{self.account()}"

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a Neon CSV file."""
        # Handle both string filepaths and _FileMemo objects from beancount-import
        if hasattr(filepath, "filepath"):
            path = filepath.filepath
        elif hasattr(filepath, "name"):
            path = filepath.name
        elif hasattr(filepath, "filename"):
            path = filepath.filename
        else:
            path = str(filepath)

        entries = []

        # Handle None existing_entries
        if existing_entries is None:
            existing_entries = []

        with open(path, encoding="utf-8") as csvfile:
            # Read the actual header to get column names
            reader = csv.DictReader(csvfile, delimiter=";")
            rows = list(reader)

        for index, row in enumerate(reversed(rows)):
            try:
                # Parse transaction
                meta = data.new_metadata(path, index)
                book_date = parse(row["Date"].strip()).date()
                amt = amount.Amount(D(row["Amount"]), "CHF")
                metakv = {
                    "category": row["Category"],
                }
                if row.get("Original currency", "").strip():
                    metakv["original_currency"] = row["Original currency"]
                    metakv["original_amount"] = row["Original amount"]
                    metakv["exchange_rate"] = row["Exchange rate"]

                meta_posting = data.new_metadata(path, 0, metakv)
                description = row["Description"].strip()
                if description in self.map:
                    payee = self.map[description][0]
                    note = self.map[description][1]
                else:
                    payee = ""
                    note = description

                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        payee,
                        note,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._account, amt, None, None, None, meta_posting
                            ),
                        ],
                    )
                )

            except Exception as e:
                # Log warning and continue
                warnings.warn(
                    f"Error parsing line {row}\n{e} from file {path}", stacklevel=2
                )
                continue

        return entries
