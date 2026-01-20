import csv
import datetime
import re
from datetime import date as date_type
from typing import Any

import beangulp
from beancount.core import amount, data, position
from beancount.core.number import D
from dateutil.parser import parse


class Importer(beangulp.Importer):
    """An importer for FinPension CSV files."""

    def __init__(
        self,
        filepattern: str,
        parent_account: str,
        income_account: str,
        fees_account: str,
        securities: dict[str, list[str]],
    ):
        self._filepattern = filepattern
        self._parent_account = parent_account
        self._income_account = income_account
        self._fees_account = fees_account
        self._securities = securities

    def identify(self, filepath: str | Any) -> bool:
        # Handle both string filepaths and _FileMemo objects from beancount-import
        path = (
            getattr(filepath, "filepath", None)
            or getattr(filepath, "name", None)
            or getattr(filepath, "filename", None)
            or str(filepath)
        )
        return re.search(self._filepattern, path) is not None

    def name(self) -> str:
        return str(super().name + self.account())

    def account(self, _: str | None = None) -> str:
        return self._parent_account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        # Handle both string filepaths and _FileMemo objects from beancount-import
        path = (
            getattr(filepath, "filepath", None)
            or getattr(filepath, "name", None)
            or getattr(filepath, "filename", None)
            or str(filepath)
        )

        entries = []

        with open(path, encoding="utf-8") as csvfile:
            reader = csv.DictReader(
                csvfile,
                [
                    "date",
                    "category",
                    "asset",
                    "ISIN",
                    "shares",
                    "currency",
                    "fxRate",
                    "priceCHF",
                    "cashFlow",
                    "balance",
                ],
                delimiter=";",
                skipinitialspace=False,
            )
            rows = list(reader)[1:]

        for index, row in enumerate(reversed(rows)):
            # Parse
            parsed_date = parse(row["date"].strip())
            if isinstance(parsed_date, datetime.datetime):
                book_date: date_type = parsed_date.date()
            elif isinstance(parsed_date, date_type):
                book_date = parsed_date
            else:
                book_date = date_type.today()
            meta = data.new_metadata(path, index)
            cashFlow = amount.Amount(D(row["cashFlow"]), "CHF")
            category = row["category"].strip()

            # Fees, Deposits & Dividends
            if category == "Flat-rate administrative fee":
                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        category,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                            data.Posting(
                                self._fees_account,
                                -cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                        ],
                    )
                )
            elif category == "Deposit":
                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        category,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                        ],
                    )
                )
            elif category == "Interests":
                interests_account = f"{self._income_account}:Interests"
                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        category,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                            data.Posting(
                                interests_account,
                                -cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                        ],
                    )
                )
            elif category == "Dividend":
                security = self._securities[row["ISIN"].strip()][0]
                pnl_account = f"{self._income_account}:{security}:Dividends"
                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        f"Dividends {security}",
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                            data.Posting(
                                pnl_account,
                                -cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                        ],
                    )
                )
            elif category == "Transfer":
                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        category,
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                        ],
                    )
                )
            elif category == "Buy":
                # This is a buy
                isin = row["ISIN"].strip()
                security = self._securities[isin][0]
                shares = amount.Amount(D(row["shares"].strip()), security)
                sec_account = self._parent_account + ":" + security

                # Calculate cost per share from cash flow
                # cashFlow is negative for buys
                if shares.number is None:
                    raise ValueError("Shares amount is missing")
                if cashFlow.number is None:
                    raise ValueError("Cash flow amount is missing")
                cost_per_share = -cashFlow.number / shares.number

                cost_spec = position.CostSpec(
                    cost_per_share, None, "CHF", None, None, None
                )

                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        f"{category} {security}",
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                            data.Posting(
                                sec_account, shares, cost_spec, None, None, None
                            ),
                        ],
                    )
                )
            elif category == "Sell":
                # This is a sell
                isin = row["ISIN"].strip()
                security = self._securities[isin][0]
                shares = amount.Amount(D(row["shares"].strip()), security)
                sec_account = self._parent_account + ":" + security
                pnl_account = f"{self._income_account}:{security}:PnL"

                # Calculate price per share from cash flow
                # cashFlow is positive for sells
                if shares.number is None:
                    raise ValueError("Shares amount is missing")
                if cashFlow.number is None:
                    raise ValueError("Cash flow amount is missing")
                share_price = amount.Amount(D(-cashFlow.number / shares.number), "CHF")

                cost_spec = position.CostSpec(
                    number_per=None,
                    number_total=None,
                    currency=None,
                    date=None,
                    label=None,
                    merge=None,
                )

                entries.append(
                    data.Transaction(
                        meta,
                        book_date,
                        "*",
                        "FinPension",
                        f"{category} {security}",
                        data.EMPTY_SET,
                        data.EMPTY_SET,
                        [
                            data.Posting(
                                self._parent_account + ":Cash",
                                cashFlow,
                                None,
                                None,
                                None,
                                None,
                            ),
                            data.Posting(
                                sec_account, shares, cost_spec, share_price, None, None
                            ),
                            data.Posting(
                                pnl_account,
                                None,
                                None,
                                None,
                                None,
                                None,
                            ),
                        ],
                    )
                )
            else:
                raise Warning(f"Unknown category {category}")
        return entries
