import csv
import re
import warnings
from datetime import datetime
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D


class ZkbCSVImporter(beangulp.Importer):
    """An importer for ZKB CSV files."""

    def __init__(self, filepattern: str, account: str):
        self._filepattern = filepattern
        self._account = account

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
        return str(super().name + self.account())

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a ZKB CSV file."""
        # Handle both string filepaths and _FileMemo objects from beancount-import
        path = (
            getattr(filepath, "filepath", None)
            or getattr(filepath, "name", None)
            or getattr(filepath, "filename", None)
            or str(filepath)
        )

        entries = []

        # Handle None existing_entries
        if existing_entries is None:
            existing_entries = []

        with open(path, encoding="utf-8-sig") as csvfile:
            # Read the actual header to get column names
            reader = csv.DictReader(csvfile, delimiter=";")
            rows = list(reader)

        for index, row in enumerate(rows):
            try:
                # Get field values - handle quoted and unquoted column names
                date_str = row.get("Date", "").strip()
                booking_text = row.get("Booking text", "").strip()
                zkb_ref = row.get("ZKB reference", "").strip()
                debit_chf = row.get("Debit CHF", "").strip()
                credit_chf = row.get("Credit CHF", "").strip()

                # Skip if no date (empty date indicates continuation/detail rows)
                if not date_str:
                    continue

                # Parse transaction
                meta = data.new_metadata(path, index)
                meta_posting = meta.copy()

                # Add ZKB reference to metadata if available
                if zkb_ref:
                    meta_posting["zkb_reference"] = zkb_ref

                # Parse date with format DD.MM.YYYY
                book_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                description = booking_text if booking_text else ""

                # Determine currency (default to CHF)
                currency = "CHF"

                # Determine cash flow from Debit or Credit
                # Try to convert to Decimal - if it fails, skip this column
                debit_amount = None
                credit_amount = None

                if debit_chf:
                    try:
                        debit_amount = D(debit_chf)
                    except (ValueError, TypeError):
                        # If it's not a number, it might be a reference or other data
                        pass

                if credit_chf:
                    try:
                        credit_amount = D(credit_chf)
                    except (ValueError, TypeError):
                        # If it's not a number, it might be a reference or other data
                        pass

                if debit_amount is not None and debit_amount != 0:
                    cash_flow = amount.Amount(-debit_amount, currency)
                elif credit_amount is not None and credit_amount != 0:
                    cash_flow = amount.Amount(credit_amount, currency)
                else:
                    # Skip rows with no valid amount
                    continue

                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "",
                        description,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._account, cash_flow, None, None, None, meta_posting
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
