import csv
import re
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D
from dateutil.parser import parse


class Importer(beangulp.Importer):
    """An importer for N26 CSV files."""

    CSV_HEADER = (
        '"Booking Date","Value Date","Partner Name","Partner Iban",Type,'
        '"Payment Reference","Account Name","Amount (EUR)","Original Amount",'
        '"Original Currency","Exchange Rate"\n'
    )

    def __init__(self, filepattern: str, account: data.Account):
        self._filepattern = filepattern
        self._account = account

    def identify(self, filepath: str | Any) -> bool:
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
        return str(super().name + self.account())

    def account(self, _: str | None = None) -> data.Account:
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries = None
    ) -> data.Entries:
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

        with open(path, encoding="utf8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

        for index, row in enumerate(rows):
            try:
                # Parse transaction
                meta = data.new_metadata(path, index)
                book_date = parse(row["Booking Date"].strip()).date()
                payee = row["Partner Name"].strip()
                description = (
                    row["Payment Reference"].strip() if row["Payment Reference"] else ""
                )
                units = amount.Amount(D(row["Amount (EUR)"]), "EUR")
                cost = None

                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        payee,
                        description,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [data.Posting(self._account, units, cost, None, None, None)],
                    )
                )

            except (ValueError, KeyError) as e:
                # More specific error handling
                raise ValueError(f"Error parsing line {index + 1}: {row}\n") from e
            except Exception as e:
                # Catch other unexpected errors
                raise RuntimeError(
                    f"Unexpected error parsing line {index + 1}: {row}"
                ) from e

        return entries
