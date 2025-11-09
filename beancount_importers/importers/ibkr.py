import copy
import itertools
import logging
import re
import warnings
from csv import DictReader
from datetime import date
from typing import Any

import beangulp
from beancount.core import amount, data, position
from beancount.core.number import D
from dateutil.parser import parse


class Importer(beangulp.Importer):
    """An importer for Interactive Brokers Flex Query CSV files."""

    def __init__(
        self,
        filepattern: str,
        parent_account: str,
        income_account: str,
        tax_account: str,
        fees_account: str,
    ):
        self._filepattern = filepattern
        self._parent_account = parent_account
        self._income_account = income_account
        self.cash_account = parent_account + ":Cash"
        self.interests_account = income_account + ":Interests"
        self.tax_account = tax_account
        self.fees_account = fees_account

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
        return f"ibkr.csv.{self.account()}"

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._parent_account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from an IBKR CSV file."""
        # Handle both string filepaths and _FileMemo objects from beancount-import
        if hasattr(filepath, "filepath"):
            path = filepath.filepath
        elif hasattr(filepath, "name"):
            path = filepath.name
        elif hasattr(filepath, "filename"):
            path = filepath.filename
        else:
            path = str(filepath)

        entries: data.Entries = []

        # Handle None existing_entries
        if existing_entries is None:
            existing_entries = []

        withholding_taxes: list[list[Any]] = []

        try:
            with open(path, encoding="utf-8") as csvfile:
                reader = DictReader(
                    csvfile,
                    fieldnames=[
                        "Id",
                        "Date",
                        "Type",
                        "Currency",
                        "Proceeds",
                        "Security",
                        "Amount",
                        "CostBasis",
                        "TradePrice",
                        "Commission",
                        "CommissionCurrency",
                    ],
                    delimiter=",",
                )
                rows = list(reader)[1:]  # Skip header row
                for index, row in enumerate(rows, start=2):  # Start at 2 (header + 1)
                    try:
                        # Parse
                        category = row["Type"]
                        book_date = parse(row["Date"].strip()).date()
                        meta = data.new_metadata(path, index)
                        meta["document"] = (
                            f"{book_date.year}-12-31-InteractiveBrokers_"
                            "ActivityReport.pdf"
                        )
                        meta["trans_id"] = row["Id"]
                        cashFlow = amount.Amount(D(row["Proceeds"]), row["Currency"])
                        security = row["Security"]

                        # Deposits and withdrawals
                        if category == "Deposits/Withdrawals":
                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    "Deposit" if cashFlow.number > 0 else "Withdrawal",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    [
                                        data.Posting(
                                            self.cash_account,
                                            cashFlow,
                                            None,
                                            None,
                                            None,
                                            None,
                                        )
                                    ],
                                )
                            )

                        # Dividends
                        elif category == "Dividends":
                            dividend_account = (
                                self._income_account + ":" + security + ":Dividends"
                            )
                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    f"Dividends {security}",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    [
                                        data.Posting(
                                            self.cash_account,
                                            cashFlow,
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                        data.Posting(
                                            dividend_account,
                                            -cashFlow,
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                    ],
                                )
                            )

                        # Other fees, e.g. referral bonus
                        elif category == "Other Fees":
                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    "Other",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    [
                                        data.Posting(
                                            self.cash_account,
                                            cashFlow,
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                    ],
                                )
                            )

                        # Withholding tax
                        elif category == "Withholding Tax":
                            withholding_taxes.append(
                                [security, book_date, cashFlow, False, meta]
                            )

                        # Interests
                        elif category == "Broker Interest Received":
                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    "Interests",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    [
                                        data.Posting(
                                            self.cash_account,
                                            cashFlow,
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                        data.Posting(
                                            self.interests_account,
                                            -cashFlow,
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                    ],
                                )
                            )

                        # FX Exchange
                        elif (
                            category in ["BUY", "SELL"] and security and "." in security
                        ):
                            commission = amount.Amount(
                                D(row["Commission"]), row["CommissionCurrency"]
                            )
                            fx_orig = amount.Amount(
                                D(row["Amount"]), row["Security"][:3]
                            )
                            fx_dest = amount.Amount(
                                D(row["Proceeds"]), row["Security"][4:]
                            )
                            fx_rate = amount.Amount(
                                D(row["TradePrice"]), row["Security"][4:]
                            )

                            postings = [
                                data.Posting(
                                    self.cash_account,
                                    fx_orig,
                                    None,
                                    fx_rate,
                                    None,
                                    None,
                                ),
                                data.Posting(
                                    self.cash_account,
                                    fx_dest,
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                            ]

                            if commission.number != 0:
                                postings.append(
                                    data.Posting(
                                        self.cash_account,
                                        commission,
                                        None,
                                        None,
                                        None,
                                        None,
                                    )
                                )
                                postings.append(
                                    data.Posting(
                                        self.fees_account,
                                        -commission,
                                        None,
                                        None,
                                        None,
                                        None,
                                    )
                                )

                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    f"FX Exchange {row['Security']}",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    postings,
                                )
                            )

                        # Trade: buy
                        elif category == "BUY":
                            # Parse more fields
                            commission = amount.Amount(
                                D(row["Commission"]), row["CommissionCurrency"]
                            )
                            shares = amount.Amount(D(row["Amount"]), security)
                            cost_per_share = position.Cost(
                                D(row["TradePrice"]),
                                row["Currency"],
                                book_date,
                                None,
                            )
                            proceeds = amount.Amount(
                                D(row["Proceeds"]) + D(row["Commission"]),
                                row["Currency"],
                            )
                            security_account = self._parent_account + ":" + security

                            postings = [
                                data.Posting(
                                    self.cash_account,
                                    proceeds,
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                                data.Posting(
                                    security_account,
                                    shares,
                                    cost_per_share,
                                    None,
                                    None,
                                    None,
                                ),
                                data.Posting(
                                    self.fees_account,
                                    -commission,
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                            ]

                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    f"Buy {row['Security']}",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    postings,
                                )
                            )

                        # Trade: sell
                        elif category == "SELL":
                            shares = amount.Amount(D(row["Amount"]), security)
                            price = amount.Amount(D(row["TradePrice"]), row["Currency"])
                            commission = amount.Amount(
                                D(row["Commission"]), row["CommissionCurrency"]
                            )

                            entries.append(
                                data.Transaction(
                                    meta,
                                    book_date,
                                    "*",
                                    "Interactive Brokers",
                                    f"Sell {row['Security']}",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    self.build_fifo_postings(
                                        existing_entries + entries,
                                        meta["trans_id"],
                                        book_date,
                                        shares,
                                        cashFlow,
                                        price,
                                        commission,
                                    ),
                                )
                            )

                        # Unrecognized transaction
                        else:
                            warnings.warn(
                                (
                                    f"File {path}: unsupported transaction of type "
                                    f"{category} on {row['Date']}"
                                ),
                                stacklevel=2,
                            )

                    except (ValueError, KeyError, IndexError) as e:
                        warnings.warn(
                            (f"Error parsing row {index} from file {path}: {e}"),
                            stacklevel=2,
                        )
                        continue

        except FileNotFoundError:
            warnings.warn(
                f"CSV file not found: {path}",
                stacklevel=2,
            )
            return entries

        # Append withholding taxes
        for index, entry in enumerate(entries):
            # It is a transaction
            if not isinstance(entry, data.Transaction):
                continue

            # It is a dividend transaction
            if "Dividends" not in entry.narration:
                continue

            # Get date and security
            trans_date = entry.date
            security = entry.narration.replace("Dividends ", "")

            # Find withholding tax
            matched = False
            for index2, tax in enumerate(withholding_taxes):
                # Match
                if tax[0] != security or tax[1] != trans_date:
                    continue

                # Double processing?
                if tax[3]:
                    warnings.warn(
                        (
                            f"Double match withholding tax for {security} "
                            f"on {trans_date}"
                        ),
                        stacklevel=2,
                    )
                else:
                    withholding_taxes[index2][3] = True

                # Build new postings
                total_cash_flow = amount.Amount(
                    D(tax[2].number + entry.postings[0].units.number), tax[2].currency
                )
                entries[index] = data.Transaction(
                    entry.meta,
                    entry.date,
                    entry.flag,
                    entry.payee,
                    entry.narration,
                    entry.tags,
                    entry.links,
                    [
                        data.Posting(
                            self.cash_account,
                            total_cash_flow,
                            None,
                            None,
                            None,
                            None,
                        ),
                        entry.postings[1],
                        data.Posting(self.tax_account, -tax[2], None, None, None, None),
                    ],
                )
                matched = True
                break

            # Withholding tax not found
            if not matched:
                warnings.warn(
                    f"Missing withholding tax for {security} on {trans_date}",
                    stacklevel=2,
                )

        # All withholding taxes processed?
        unmatched_withholding_taxes = []
        for tax in withholding_taxes:
            if not tax[3]:
                unmatched_withholding_taxes.append(tax)

        # Withholding tax re-calculations
        indexes: list[int] = []
        for index, tax in enumerate(unmatched_withholding_taxes):
            # Check for tax re-imbursement
            if tax[2].number > 0:
                # Find tax re-calculations on same date
                for index2, match_tax in enumerate(unmatched_withholding_taxes):
                    if match_tax[0:1] == tax[0:1] and match_tax[2].number < 0:
                        # Find original dividend
                        for entry in itertools.chain(entries, existing_entries):
                            # It is a transaction
                            if not isinstance(entry, data.Transaction):
                                continue

                            # It is a dividend transaction
                            if "Dividends" not in entry.narration:
                                continue

                            # It is the same security
                            security = entry.narration.replace("Dividends ", "")
                            if security != tax[0]:
                                continue
                            dividend_account = (
                                self._income_account + ":" + security + ":Dividends"
                            )

                            # It is the same value, opposite sign
                            value = None
                            for posting in entry.postings:
                                if posting.account == self.tax_account:
                                    value = posting.units
                            if value is None or value != tax[2]:
                                continue

                            # We got a match! Get date of original dividend payout
                            trans_date = entry.date
                            indexes.append(index)
                            indexes.append(index2)
                            cash_balance = amount.Amount(
                                tax[2].number + match_tax[2].number, tax[2].currency
                            )

                            entries.append(
                                data.Transaction(
                                    tax[4],
                                    tax[1],
                                    "*",
                                    "Interactive Brokers",
                                    f"Dividends {security}",
                                    data.EMPTY_SET,
                                    data.EMPTY_SET,
                                    [
                                        data.Posting(
                                            self.cash_account,
                                            cash_balance,
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                        data.Posting(
                                            dividend_account,
                                            amount.Amount(D(0), tax[2].currency),
                                            None,
                                            None,
                                            None,
                                            None,
                                        ),
                                        data.Posting(
                                            self.tax_account,
                                            -cash_balance,
                                            None,
                                            None,
                                            None,
                                            {"effective_date": f"{trans_date}"},
                                        ),
                                    ],
                                )
                            )

        # Unmatched withholding taxes?
        for index, tax in enumerate(unmatched_withholding_taxes):
            if index not in indexes:
                logging.warning(
                    f"Unmatched withholding tax for {tax[0]} on {tax[1]}, "
                    f"value {tax[2]}"
                )

        return entries

    def build_fifo_postings(
        self,
        entries: data.Entries,
        transaction_id: str,
        lot_date: date,
        shares: amount.Amount,
        proceeds: amount.Amount,
        price: amount.Amount,
        commission: amount.Amount,
    ) -> list[data.Posting]:
        # Accounts
        security = shares.currency
        security_account = self._parent_account + ":" + security
        pnl_account = self._income_account + ":" + security + ":PnL"

        # Build inventory
        processed_transactions: list[str] = []
        buys: list[dict[str, Any]] = []
        sells: list[dict[str, Any]] = []
        for entry in entries:
            # It is a transaction
            if not isinstance(entry, data.Transaction):
                continue

            if "trans_id" not in entry.meta:
                continue
            trans_id = entry.meta["trans_id"]

            # Up to given transaction
            if trans_id >= transaction_id:
                continue

            # Avoid duplicate processing
            if trans_id in processed_transactions:
                continue
            processed_transactions.append(trans_id)

            # Find a trade with this commodity
            for posting in entry.postings:
                if posting.account == security_account:
                    # Buy or sell?
                    if posting.units.number > 0:
                        buys.append(
                            {
                                "id": trans_id,
                                "units": posting.units,
                                "cost": posting.cost,
                                "date": entry.date,
                            }
                        )
                    else:
                        sells.append(
                            {
                                "id": trans_id,
                                "units": posting.units,
                                "cost": posting.cost,
                                "date": entry.date,
                            }
                        )

        # Sort and process sales
        buys.sort(key=lambda x: x.get("date") or date.min)
        sells.sort(key=lambda x: x.get("date") or date.min)
        inventory: list[dict[str, Any] | None] = buys  # type: ignore[assignment]
        for sell in sells:
            inventory, _ = self.sell_from_lot(inventory, sell)

        # Sell lot
        inventory, sold_lots = self.sell_from_lot(
            inventory,
            {
                "id": transaction_id,
                "units": shares,
                "cost": None,
                "date": lot_date,
            },
        )

        # Calculate pnl
        pnl_cash_flow = -proceeds.number
        for lot in sold_lots:
            if lot["cost"] is not None:
                pnl_cash_flow += D(lot["cost"].number * lot["units"].number)

        # Build postings
        totalProceeds = amount.Amount(
            D(proceeds.number + commission.number), proceeds.currency
        )
        postings: list[data.Posting] = [
            data.Posting(self.cash_account, totalProceeds, None, None, None, None),
            data.Posting(
                pnl_account,
                amount.Amount(D(pnl_cash_flow), proceeds.currency),
                None,
                None,
                None,
                None,
            ),
        ]
        if commission.number != 0:
            postings.append(
                data.Posting(self.fees_account, -commission, None, None, None, None)
            )

        for lot in sold_lots:
            postings.append(
                data.Posting(
                    security_account,
                    -lot["units"],
                    lot["cost"],
                    price,
                    None,
                    None,
                )
            )

        return postings

    def sell_from_lot(
        self,
        inventory: list[dict[str, Any] | None],
        sell_lot: dict[str, Any],
    ) -> tuple[list[dict[str, Any] | None], list[dict[str, Any]]]:
        target_sell = sell_lot
        security = sell_lot["units"].currency

        # FIFO selling
        sold_lots: list[dict[str, Any]] = []
        sale_complete = False
        for index, lot in enumerate(copy.deepcopy(inventory)):
            if lot is None:
                continue
            # Difference between shares to be sold and shares in this lot
            leftover = lot["units"].number + sell_lot["units"].number

            # Exact units to cover the remaining units
            if leftover == D(0):
                # Add the entire lot to "sold lots"
                sold_lots.append(lot)

                # Remove the lot from the inventory
                inventory[index] = None

                # Break signal
                sale_complete = True
                break

            # More than enough units to cover the remaining units
            if leftover > 0:
                # Remaining units in this lot
                inventory[index] = {
                    **lot,
                    "units": amount.Amount(leftover, security),
                }

                # Sold units
                lot["units"] = amount.Amount(-sell_lot["units"].number, security)
                sold_lots.append(lot)

                # Break signal
                sale_complete = True
                break

            # Consume this lot and continue to the next one
            else:
                # Remove the lot from the inventory
                inventory[index] = None

                # Sold units
                sold_lots.append(lot)

                # Reduce the target lot
                sell_lot["units"] = amount.Amount(
                    sell_lot["units"].number + lot["units"].number, security
                )

        # Successful sale?
        if not sale_complete:
            logging.warning(
                f"Error selling {target_sell} from {inventory}\nSold: {sold_lots}"
            )

        return list(filter(None, inventory)), sold_lots
