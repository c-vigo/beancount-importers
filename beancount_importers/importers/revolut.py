import csv
import logging
import re
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D
from dateutil.parser import parse


class Importer(beangulp.Importer):
    """An importer for Revolut CSV files."""

    def __init__(
        self,
        filepattern: str,
        account: str,
        fee_account: str,
        currency: str,
    ):
        self._filepattern = filepattern
        self._account = account
        self._fee_account = fee_account
        self._currency = currency

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
        return str(super().name + self.account())

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a Revolut CSV file."""
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
            reader = csv.DictReader(
                csvfile,
                [
                    "Type",
                    "Product",
                    "Started Date",
                    "Completed Date",
                    "Description",
                    "Amount",
                    "Fee",
                    "Currency",
                    "State",
                    "Balance",
                ],
                delimiter=",",
                skipinitialspace=True,
            )
            rows = list(reader)[1:]  # Skip header

        for index, row in enumerate(rows):
            try:
                meta = data.new_metadata(path, index)
                book_date = parse(row["Started Date"].strip()).date()
                description = row["Type"].strip() + " " + row["Description"].strip()
                cash_flow = amount.Amount(
                    D(row["Amount"]) - D(row["Fee"]), row["Currency"]
                )

                # Skip zero amounts
                if cash_flow.number == D(0):
                    continue

                # Skip non-completed transactions
                if row["State"].strip() != "COMPLETED":
                    continue

                # Process entry
                entry = data.Transaction(
                    meta,
                    book_date,
                    "*",
                    "",
                    description,
                    data.EMPTY_SET,
                    data.EMPTY_SET,
                    [data.Posting(self._account, cash_flow, None, None, None, None)],
                )
                entries.append(entry)

                # Note: Balance entries are commented out in original code
                # If needed, they can be added here:
                # balance = data.Balance(
                #     meta,
                #     book_date + timedelta(days=1),
                #     self._account,
                #     amount.Amount(D(row["Balance"]), self._currency),
                #     None,
                #     None,
                # )
                # entries.append(balance)

            except Exception as e:
                logging.warning(f"Error processing row {index + 1}: {e}")
                continue

        return entries
