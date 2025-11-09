"""SBB CSV importer for Beancount."""

import csv
import re
import warnings
from datetime import datetime
from typing import Any

import beangulp
from beancount.core import amount, data
from beancount.core.number import D


class Importer(beangulp.Importer):
    """An importer for SBB CSV files."""

    def __init__(self, filepattern: str, account: str, owner: str):
        self._filepattern = filepattern
        self._account = account
        self.owner = owner

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
        return f"sbb.{self.account()}"

    def account(self, _: str | None = None) -> str:
        """Return the account for this importer."""
        return self._account

    def extract(
        self, filepath: str | Any, existing_entries: data.Entries | None = None
    ) -> data.Entries:
        """Extract transactions from an SBB CSV file."""
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
        try:
            with open(path, encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for line_number, row in enumerate(reader, start=2):
                    try:
                        # Skip empty rows
                        if not row or all(
                            not str(v).strip() if v is not None else True
                            for v in row.values()
                        ):
                            continue

                        # Parse fields
                        price_str = row.get("Price", "") or ""
                        price_str = price_str.strip() if price_str else ""
                        if not price_str:
                            continue

                        # Check if this transaction is for the owner
                        co_passengers = row.get("Co-passenger(s)", "") or ""
                        co_passengers = co_passengers.strip() if co_passengers else ""
                        if self.owner not in co_passengers:
                            continue

                        # Parse dates
                        order_date_str = row.get("Order date", "") or ""
                        order_date_str = (
                            order_date_str.strip() if order_date_str else ""
                        )
                        travel_date_str = row.get("Travel date", "") or ""
                        travel_date_str = (
                            travel_date_str.strip() if travel_date_str else ""
                        )

                        # Parse order date (format: DD.MM.YYYY or YYYY-MM-DD)
                        try:
                            if "-" in order_date_str:
                                order_date = datetime.strptime(
                                    order_date_str, "%Y-%m-%d"
                                ).date()
                            else:
                                order_date = datetime.strptime(
                                    order_date_str, "%d.%m.%Y"
                                ).date()
                        except ValueError:
                            warnings.warn(
                                (
                                    f"Error parsing order date '{order_date_str}' "
                                    f"in row {line_number} from file {path}"
                                ),
                                stacklevel=2,
                            )
                            continue

                        # Validate travel date format (format: DD.MM.YYYY or YYYY-MM-DD)
                        try:
                            if "-" in travel_date_str:
                                datetime.strptime(travel_date_str, "%Y-%m-%d").date()
                            else:
                                datetime.strptime(travel_date_str, "%d.%m.%Y").date()
                        except ValueError:
                            warnings.warn(
                                (
                                    f"Error parsing travel date '{travel_date_str}' "
                                    f"in row {line_number} from file {path}"
                                ),
                                stacklevel=2,
                            )
                            continue

                        # Parse price
                        try:
                            price = D(price_str)
                        except Exception as e:
                            warnings.warn(
                                (
                                    f"Error parsing price '{price_str}' "
                                    f"in row {line_number} from file {path}: {e}"
                                ),
                                stacklevel=2,
                            )
                            continue

                        # Get other fields
                        tariff = row.get("Tariff", "") or ""
                        tariff = tariff.strip() if tariff else ""
                        route = row.get("Route", "") or ""
                        route = route.strip() if route else ""
                        via = row.get("Via (optional)", "") or ""
                        via = via.strip() if via else ""
                        order_number = row.get("Order number", "") or ""
                        order_number = order_number.strip() if order_number else ""
                        email = row.get("Purchaser e-mail", "") or ""
                        email = email.strip() if email else ""

                        # Build description
                        description_parts = []
                        if tariff:
                            description_parts.append(tariff)
                        if route:
                            description_parts.append(route)
                        if via:
                            description_parts.append(f"via {via}")
                        description = (
                            " - ".join(description_parts)
                            if description_parts
                            else "SBB Ticket"
                        )

                        # Create transaction
                        entries.append(
                            data.Transaction(
                                data.new_metadata(
                                    filename=path,
                                    lineno=line_number,
                                    kvlist={
                                        "orderno": order_number,
                                        "traveller": co_passengers,
                                        "email": email,
                                        "travel_date": travel_date_str,
                                        "tariff": tariff,
                                        "route": route,
                                    },
                                ),
                                order_date,
                                "*",
                                "SBB",
                                description,
                                data.EMPTY_SET,
                                data.EMPTY_SET,
                                [
                                    data.Posting(
                                        self._account,
                                        amount.Amount(-price, "CHF"),
                                        None,
                                        None,
                                        None,
                                        None,
                                    )
                                ],
                            )
                        )
                    except (ValueError, KeyError, IndexError) as e:
                        warnings.warn(
                            (f"Error parsing row {line_number} from file {path}: {e}"),
                            stacklevel=2,
                        )
                        continue

        except FileNotFoundError:
            warnings.warn(
                f"CSV file not found: {path}",
                stacklevel=2,
            )
            return entries
        except Exception as e:
            warnings.warn(
                f"Error reading CSV file {path}: {e}",
                stacklevel=2,
            )
            return entries

        return entries
