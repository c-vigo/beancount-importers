import csv
import datetime
import os
import re
import warnings
from enum import Enum
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D
from dateutil.parser import parse


class TransactionType(Enum):
    Deposit = "A deposit into the account"
    Removal = "A withdrawal of capital"
    Buy = "An investment"
    Sell = "Payback of principal"
    Dividend = "Return on the principal"
    Interest = "Payment of interests (secondary market discounts, campaign bonus...)"
    Fees = "Various fees (e.g. secondary market transactions)"
    Repurchase = "Special: rincipal received from repurchase of small loan parts"

    @staticmethod
    def from_description(desc: str, value: D) -> "TransactionType":
        if " - discount/premium for secondary market transaction" in desc:
            if value > 0:
                return TransactionType.Interest
            else:
                raise ValueError(f"Negative discount?: {desc}")
        elif "repurchase of small loan parts" in desc:
            return TransactionType.Repurchase
        elif " - secondary market fee" in desc:
            return TransactionType.Fees
        elif " - secondary market transaction" in desc:
            if value > 0:
                return TransactionType.Sell
            else:
                return TransactionType.Buy
        elif "deposits" in desc:
            return TransactionType.Deposit
        elif "withdrawal" in desc:
            return TransactionType.Removal
        elif " - investment in loan" in desc:
            return TransactionType.Buy
        elif (
            "interest received" in desc
            or "late fees received" in desc
            or "delayed interest income" in desc
        ):
            return TransactionType.Dividend
        elif "principal received" in desc:
            return TransactionType.Sell
        elif "refer a friend bonus" in desc or "cashback bonus" in desc:
            if value > 0:
                return TransactionType.Interest
            else:
                raise ValueError(f"Negative bonus?: {desc}")
        elif "deposit reversed" in desc:
            return TransactionType.Fees

        # Unknown
        raise ValueError(f"Invalid transaction details: {desc}")


class Transaction:
    """Represents a Mintos transaction."""

    type: TransactionType
    value: D
    date: datetime.date

    def __init__(self, info: dict[str, str]) -> None:
        self.value = D(info["Turnover"])
        self.type = TransactionType.from_description(
            info["Details"].strip().lower(), self.value
        )
        if self.type != TransactionType.Repurchase:
            self.date = parse(info["Date"].strip()).date()


class Importer(beangulp.Importer):
    """An importer for Mintos CSV files."""

    def __init__(
        self,
        filepattern: str,
        cash_account: str,
        loan_account: str,
        fees_account: str,
        pnl_account: str,
        external_account: str | None = None,
        loan_currency: str = "MNTS",
    ):
        self._filepattern = filepattern
        self._cash_account = cash_account
        self._pnl_account = pnl_account
        self._loan_account = loan_account
        self._fees_account = fees_account
        self._external_account = external_account
        self._loan_currency = loan_currency

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
        return self._cash_account

    def build_postings(
        self,
        accumulated_fees: D,
        accumulated_interest: D,
        accumulated_cashflow: D,
    ) -> list[data.Posting]:
        """Build postings for accumulated transactions."""
        postings: list[data.Posting] = []
        total = accumulated_cashflow + accumulated_fees + accumulated_interest

        # Price annotation: 1 MNTS = 1 EUR
        price = amount.Amount(D("1"), "EUR")

        if accumulated_interest != 0:
            postings.append(
                data.Posting(
                    self._pnl_account,
                    -amount.Amount(D(accumulated_interest), "EUR"),
                    None,
                    None,
                    None,
                    None,
                )
            )
        if accumulated_fees != 0:
            postings.append(
                data.Posting(
                    self._fees_account,
                    -amount.Amount(D(accumulated_fees), "EUR"),
                    None,
                    None,
                    None,
                    None,
                )
            )
        if accumulated_cashflow != 0:
            # Loans are tracked in MNTS (pegged currency, 1 MNTS = 1 EUR)
            # Negative cashflow (investments) = negative MNTS (loans increase)
            postings.append(
                data.Posting(
                    self._loan_account,
                    amount.Amount(D(accumulated_cashflow), "MNTS"),
                    None,
                    price,
                    None,
                    None,
                )
            )
        if total != 0:
            postings.append(
                data.Posting(
                    self._cash_account,
                    amount.Amount(D(total), "EUR"),
                    None,
                    None,
                    None,
                    None,
                )
            )

        return postings

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a Mintos CSV file."""
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

        # Summary of entries only
        accumulated_fees = D("0")
        accumulated_interest = D("0")
        accumulated_cashflow = D("0")
        last_date: datetime.date | None = None
        last_index: int | None = None

        with open(path, encoding="utf-8") as csvfile:
            reader = csv.DictReader(
                csvfile,
                delimiter=",",
                skipinitialspace=False,
            )

            for last_index, row in enumerate(reader):
                # Parse transaction
                try:
                    transaction = Transaction(row)
                except Exception as e:
                    # Log warning and continue
                    warnings.warn(f"Error parsing line {row}\n{e}", stacklevel=2)
                    continue

                # Repurchase?
                if transaction.type == TransactionType.Repurchase:
                    accumulated_interest = accumulated_interest + transaction.value
                    continue

                # Accumulate?
                if transaction.type in [
                    TransactionType.Interest,
                    TransactionType.Dividend,
                ]:
                    accumulated_interest = accumulated_interest + transaction.value
                    last_date = transaction.date
                    continue
                if transaction.type == TransactionType.Fees:
                    accumulated_fees = accumulated_fees + transaction.value
                    last_date = transaction.date
                    continue
                if transaction.type in [TransactionType.Buy, TransactionType.Sell]:
                    accumulated_cashflow = accumulated_cashflow + transaction.value
                    last_date = transaction.date
                    continue

                # It's a deposit or removal, create entry with accumulated
                # transactions and reset
                postings = self.build_postings(
                    accumulated_fees, accumulated_interest, accumulated_cashflow
                )
                accumulated_cashflow = accumulated_fees = accumulated_interest = D("0")
                if postings:
                    # Create metadata with date, document, and source_desc
                    meta = data.new_metadata(path, last_index)
                    meta["date"] = transaction.date
                    meta["document"] = os.path.basename(path)
                    meta["source_desc"] = "Summary"

                    entries.append(
                        data.Transaction(
                            meta,
                            transaction.date,
                            "*",
                            "Mintos",
                            "Summary",
                            data.EMPTY_SET,
                            data.EMPTY_SET,
                            postings,
                        )
                    )

                # Now add entry for the deposit/removal
                postings = [
                    data.Posting(
                        self._cash_account,
                        amount.Amount(transaction.value, "EUR"),
                        None,
                        None,
                        None,
                        None,
                    )
                ]
                if self._external_account is not None:
                    postings.append(
                        data.Posting(
                            self._external_account,
                            -amount.Amount(transaction.value, "EUR"),
                            None,
                            None,
                            None,
                            None,
                        )
                    )

                entries.append(
                    data.Transaction(
                        data.new_metadata(path, last_index),
                        transaction.date,
                        "*",
                        "Mintos",
                        (
                            "Deposit"
                            if transaction.type == TransactionType.Deposit
                            else "Withdrawal"
                        ),
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        postings,
                    )
                )

        # Last entry
        if last_date is not None:
            postings = self.build_postings(
                accumulated_fees, accumulated_interest, accumulated_cashflow
            )
            if postings:
                # Create metadata with date, document, and source_desc
                meta = data.new_metadata(
                    path,
                    last_index if last_index is not None else 0,
                )
                meta["date"] = last_date
                meta["document"] = os.path.basename(path)
                meta["source_desc"] = "Summary"

                entries.append(
                    data.Transaction(
                        meta,
                        last_date,
                        "*",
                        "Mintos",
                        "Summary",
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        postings,
                    )
                )

        return entries
