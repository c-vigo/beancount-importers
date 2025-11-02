import copy
import csv
import datetime
import logging
import re
from typing import Any

import beangulp
from beancount.core import amount, data, position
from beancount.core.number import D
from dateutil.parser import parse


def build_sell_postings(
    entries: data.Entries,
    sec_account: str,
    cash_account: str,
    pnl_account: str,
    lot_date: datetime.date,
    shares: amount.Amount,
    price: amount.Amount,
    proceeds: amount.Amount,
    fx_rate: amount.Amount,
    currency: str,
) -> list[data.Posting]:
    buys: list[dict[str, Any]] = []
    sells: list[dict[str, Any]] = []
    for entry in entries:
        # It is a transaction
        if not isinstance(entry, data.Transaction):
            continue
        entry = entry

        # Up to given date
        if entry.date > lot_date:
            continue

        # Find this account
        for posting in entry.postings:
            if posting.account == sec_account:
                # Buy or sell?
                if posting.units[0] > 0:
                    buys.append(
                        {
                            "units": posting.units,
                            "cost": posting.cost,
                            "date": entry.date,
                        }
                    )
                else:
                    sells.append(
                        {
                            "units": posting.units,
                            "cost": posting.cost,
                            "date": entry.date,
                        }
                    )

    # Sort and process sales
    buys.sort(key=lambda x: x.get("date") or datetime.date.min)
    sells.sort(key=lambda x: x.get("date") or datetime.date.min)
    inventory: list[dict[str, Any] | None] = buys  # type: ignore[assignment]
    for sell in sells:
        inventory, _ = sell_from_lot(inventory, sell)

    # Sell lot
    inventory, sold_lots = sell_from_lot(
        inventory, {"units": shares, "cost": None, "date": lot_date}
    )

    # Calculate pnl
    pnl_cash_flow = -proceeds[0]
    share_currency = "CHF"
    if fx_rate is not None:
        pnl_cash_flow = -proceeds[0] * fx_rate[0]
        share_currency = fx_rate[1]
        price = amount.Amount(D(price[0] * fx_rate[0]), fx_rate[1])
    for lot in sold_lots:
        pnl_cash_flow += D(lot["cost"][0] * lot["units"][0])

    # Build postings
    postings = [
        data.Posting(cash_account, proceeds, None, fx_rate, None, None),
        data.Posting(
            pnl_account,
            amount.Amount(D(pnl_cash_flow), share_currency),
            None,
            None,
            None,
            None,
        ),
    ]

    for lot in sold_lots:
        postings.append(
            data.Posting(sec_account, -lot["units"], lot["cost"], price, None, None)
        )

    return postings


def sell_from_lot(
    inventory: list[dict[str, Any] | None], sell_lot: dict[str, Any]
) -> tuple[list[dict[str, Any] | None], list[dict[str, Any]]]:
    target_sell = sell_lot
    security = sell_lot["units"][1]

    # FIFO selling
    sold_lots = []
    sale_complete = False
    for index, lot in enumerate(copy.deepcopy(inventory)):
        if lot is None:
            continue
        # Difference between shares to be sold and shares in this lot
        leftover = lot["units"][0] + sell_lot["units"][0]

        # Exact units to cover the remaining units
        if leftover == D(0):
            # Add the entire lot to "sold lots"
            sold_lots += [lot]

            # Remove the lot from the inventory
            inventory[index] = None

            # Break signal
            sale_complete = True
            break

        # More than enough units to cover the remaining units
        if leftover > 0:
            # Remaining units in this lot
            inventory[index]["units"] = data.Amount(leftover, security)  # type: ignore[index]

            # Sold units
            lot["units"] = data.Amount(-sell_lot["units"][0], security)
            sold_lots += [lot]

            # Break signal
            sale_complete = True
            break

        # Consume this lot and continue to the next one
        else:
            # Remove the lot from the inventory
            inventory[index] = None

            # Sold units
            sold_lots += [lot]

            # Reduce the target lot
            sell_lot["units"] = data.Amount(
                sell_lot["units"][0] + lot["units"][0], security
            )

    # Successful sale?
    if not sale_complete:
        logging.warning(
            f"Error selling {target_sell} from {inventory}\nSold: {sold_lots}"
        )

    return list(filter(None, inventory)), sold_lots


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

    def account(self, _: str | None = None) -> str:
        return self._parent_account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
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
            book_date = parse(row["date"].strip()).date()
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
            elif category in ["Buy", "Sell"]:
                # This is a trade: buy or sell
                isin = row["ISIN"].strip()
                security = self._securities[isin][0]
                shares = amount.Amount(D(row["shares"].strip()), security)
                sec_account = self._parent_account + ":" + security

                # Calculate cost per share from total cost
                # cashFlow is negative for buys, positive for sells
                shares_number = abs(shares.number)
                total_cost = abs(cashFlow.number)
                cost_per_share = (
                    total_cost / shares_number if shares_number > 0 else D("0")
                )

                cost_spec = position.CostSpec(
                    cost_per_share, total_cost, "CHF", None, None, None
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
            else:
                raise Warning(f"Unknown category {category}")
        return entries
