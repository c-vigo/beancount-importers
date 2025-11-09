import csv
import re
import warnings
from datetime import datetime
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D


def clean_decimal(formatted_number: str) -> D:
    """Clean and convert a formatted number string to Decimal."""
    return D(formatted_number.replace("'", ""))


class HouseHoldSplitWiseImporter(beangulp.Importer):
    """An importer for SplitWise household CSV files."""

    def __init__(
        self,
        filepattern: str,
        account: str,
        owner: str,
        partner: str,
        account_map: dict[str, str] | None = None,
        tag: str | None = None,
    ):
        self._filepattern = filepattern
        self._account = account
        self.owner = owner
        self.partner = partner
        self.account_map = account_map or {}
        self.tag = {tag} if tag is not None else data.EMPTY_SET

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
        return f"splitwise.household.{self.account()}"

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a SplitWise household CSV file."""
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

        # Read the CSV file
        with open(path, encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile, delimiter=",")
            rows = list(reader)

        # First row: header, sanity checks
        if len(rows) < 1:
            return entries

        people = rows[0][5:]
        if len(people) != 2:
            warnings.warn(
                f"House-hold Splitwise requires two people, found {len(people)}",
                stacklevel=2,
            )
            return entries

        if self.owner not in people:
            warnings.warn(
                f"Owner '{self.owner}' not found in the group: {people}",
                stacklevel=2,
            )
            return entries

        if self.partner not in people:
            warnings.warn(
                f"Partner '{self.partner}' not found in the group: {people}",
                stacklevel=2,
            )
            return entries

        idx_owner = people.index(self.owner)
        idx_partner = people.index(self.partner)

        # Loop over transactions (skip header and empty row)
        for index, row in enumerate(rows[2:], start=2):
            # Skip empty rows
            if not row or len(row) < 7:
                continue

            # Split fields
            try:
                if idx_owner > idx_partner:
                    date_str, description, category, cost, currency, _, value = tuple(
                        row
                    )
                else:
                    date_str, description, category, cost, currency, value, _ = tuple(
                        row
                    )
            except ValueError:
                warnings.warn(
                    f"Error parsing line {row} from file {path}", stacklevel=2
                )
                continue

            # Parse date
            try:
                trans_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                warnings.warn(
                    f"Error parsing date '{date_str}' from file {path}",
                    stacklevel=2,
                )
                continue

            # Balance?
            if description == "Total balance":
                entries.append(
                    data.Balance(
                        data.new_metadata(path, index),
                        trans_date,
                        self._account,
                        amount.Amount(clean_decimal(value), currency),
                        None,
                        None,
                    )
                )

            else:
                # Parse fields
                cost_decimal = clean_decimal(cost)
                value_decimal = clean_decimal(value)

                # Identify account from map
                exp_account = self.account_map.get(category, "Expenses:FIXME")

                # Case 1: (partially) paid by owner
                if value_decimal > 0:
                    entries.append(
                        data.Transaction(
                            data.new_metadata(path, index, {"category": category}),
                            trans_date,
                            "*",
                            self.owner,
                            description,
                            self.tag,
                            data.EMPTY_SET,
                            [
                                data.Posting(
                                    self._account,
                                    amount.Amount(value_decimal, currency),
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                                data.Posting(
                                    exp_account,
                                    amount.Amount(
                                        cost_decimal - value_decimal, currency
                                    ),
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                            ],
                        )
                    )
                else:
                    entries.append(
                        data.Transaction(
                            data.new_metadata(path, index, {"category": category}),
                            trans_date,
                            "*",
                            self.partner,
                            description,
                            self.tag,
                            data.EMPTY_SET,
                            [
                                data.Posting(
                                    self._account,
                                    amount.Amount(value_decimal, currency),
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                                data.Posting(
                                    exp_account,
                                    amount.Amount(-value_decimal, currency),
                                    None,
                                    None,
                                    None,
                                    None,
                                ),
                            ],
                        )
                    )

        return entries


class TripSplitWiseImporter(beangulp.Importer):
    """An importer for SplitWise trip CSV files."""

    def __init__(
        self,
        filepattern: str,
        account: str,
        owner: str,
        expenses_account: str | None = None,
        tag: str | None = None,
    ):
        self._filepattern = filepattern
        self._account = account
        self.owner = owner
        self.expenses_account = expenses_account
        self.tag = {tag} if tag is not None else data.EMPTY_SET
        self.fixme_account = "Expenses:FIXME"

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
        return f"splitwise.trip.{self.account()}"

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from a SplitWise trip CSV file."""
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

        # Read the CSV file
        with open(path, encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile, delimiter=",")
            rows = list(reader)

        # First row: header, sanity checks
        if len(rows) < 1:
            return entries

        people = rows[0][5:]
        if len(people) < 2:
            warnings.warn(
                f"Trip Splitwise requires at least two people, found {len(people)}",
                stacklevel=2,
            )
            return entries

        if self.owner not in people:
            warnings.warn(
                f"Owner '{self.owner}' not found in the group: {people}",
                stacklevel=2,
            )
            return entries

        idx_owner = people.index(self.owner)

        # Loop over transactions (skip header and empty row)
        for index, row in enumerate(rows[2:], start=2):
            # Skip empty rows
            if not row or len(row) < 6:
                continue

            # Split fields
            try:
                date_str, description, category, cost, currency, *splits = tuple(row)
            except ValueError:
                warnings.warn(
                    f"Error parsing line {row} from file {path}", stacklevel=2
                )
                continue

            # Parse date
            try:
                trans_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                warnings.warn(
                    f"Error parsing date '{date_str}' from file {path}",
                    stacklevel=2,
                )
                continue

            # Balance?
            if description == "Total balance":
                if idx_owner < len(splits):
                    entries.append(
                        data.Balance(
                            data.new_metadata(path, index),
                            trans_date,
                            self._account,
                            amount.Amount(clean_decimal(splits[idx_owner]), currency),
                            None,
                            None,
                        )
                    )
                continue

            # Parse fields
            splits_decimal = [clean_decimal(split) for split in splits]
            owner_balance = (
                splits_decimal[idx_owner] if idx_owner < len(splits_decimal) else D(0)
            )
            others_balance = sum(splits_decimal) - owner_balance
            all_zeroes = all(split == D(0) for split in splits_decimal)

            # Case 1: no liability for anyone, fully paid by owner and just tracked here
            if all_zeroes:
                continue
            # Case 2: owner not involved, paid and owed by others
            elif owner_balance == D(0) and others_balance == D(0):
                continue
            # Case 3: negative balance for owner
            elif owner_balance < D(0):
                # Build postings
                postings = [
                    data.Posting(
                        self._account,
                        amount.Amount(owner_balance, currency),
                        None,
                        None,
                        None,
                        None,
                    ),
                ]
                if self.expenses_account is not None:
                    postings.append(
                        data.Posting(
                            self.expenses_account,
                            amount.Amount(-owner_balance, currency),
                            None,
                            None,
                            None,
                            None,
                        )
                    )

                # Append transaction
                entries.append(
                    data.Transaction(
                        data.new_metadata(path, index, {"category": category}),
                        trans_date,
                        "*",
                        "",
                        description,
                        self.tag,
                        data.EMPTY_SET,
                        postings,
                    )
                )
            # Case 4: positive balance for owner
            else:
                # Build postings
                postings = [
                    data.Posting(
                        self._account,
                        amount.Amount(owner_balance, currency),
                        None,
                        None,
                        None,
                        None,
                    ),
                ]
                if self.expenses_account is not None:
                    postings.append(
                        data.Posting(
                            self.expenses_account,
                            amount.Amount(-owner_balance, currency),
                            None,
                            None,
                            None,
                            None,
                        )
                    )

                # Append transaction
                entries.append(
                    data.Transaction(
                        data.new_metadata(path, index, {"category": category}),
                        trans_date,
                        "*",
                        "",
                        description,
                        self.tag,
                        data.EMPTY_SET,
                        postings,
                    )
                )

        return entries
