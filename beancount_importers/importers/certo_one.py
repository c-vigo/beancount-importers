import csv
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import beangulp
import camelot
from beancount.core import amount, data
from beancount.core.number import D
from dateutil.parser import parse
from pypdf import PdfReader


def cleanDecimal(formatted_number: str) -> Decimal:
    return D(formatted_number.replace("'", ""))


def parse_pdf_to_csv(pdf_file_name: str, csv_file_name: str) -> None:
    transactions = []

    # get number of pages
    reader = PdfReader(pdf_file_name)
    n_pages = len(reader.pages)

    # Read tables
    try:
        tables = camelot.read_pdf(
            pdf_file_name,
            pages=f"2-{n_pages - 2}",
            flavor="stream",
            table_areas=["50,700,560,90"],
        )
    except (ValueError, TypeError):
        try:
            tables = camelot.read_pdf(
                pdf_file_name,
                pages=f"2-{n_pages - 3}",
                flavor="stream",
                table_areas=["50,700,560,90"],
            )
        except (ValueError, TypeError):
            # If both attempts fail, try with different parameters
            tables = camelot.read_pdf(
                pdf_file_name,
                pages=f"2-{n_pages - 1}",
                flavor="stream",
            )

    # Visual debugging
    # camelot.plot(tables[0], kind='text').show()
    # camelot.plot(tables[0], kind='grid').show()

    balance_date = None
    balance_amount = None

    for table in tables:
        for _index, row in table.df.iterrows():
            if len(tuple(row)) == 5:
                _, book_date, text, credit, debit = tuple(row)
            elif len(tuple(row)) == 4:
                book_date, text, credit, debit = tuple(row)
            else:
                # Balance in a separate table
                text, value = tuple(row)
                balance_match = re.search(
                    r"Saldo per (\d\d\.\d\d\.\d\d\d\d) zu unseren Gunsten CHF", text
                )
                if balance_match:
                    balance_date = balance_match.group(1)
                    balance_date = datetime.strptime(balance_date, "%d.%m.%Y").date()
                    # add 1 day: cembra provides balance at EOD, beancount checks at SOD
                    balance_date = balance_date + timedelta(days=1)
                    balance_amount = cleanDecimal(value)
                continue

            book_date, text, credit, debit = (
                book_date.strip(),
                text.strip(),
                credit.strip(),
                debit.strip(),
            )

            # Transaction entry
            try:
                book_date = datetime.strptime(book_date, "%d.%m.%Y").date()
            except Exception:
                book_date = None

            if book_date:
                value = -cleanDecimal(debit) if debit else cleanDecimal(credit)
                transactions.append([book_date, value, text])
                continue

            # Balance entry
            try:
                balance_match = re.search(
                    r"Saldo per (\d\d\.\d\d\.\d\d\d\d) zu unseren Gunsten CHF", text
                )
                if balance_match:
                    balance_date = balance_match.group(1)
                    balance_date = datetime.strptime(balance_date, "%d.%m.%Y").date()
                    # add 1 day: cembra provides balance at EOD, beancount checks at SOD
                    balance_date = balance_date + timedelta(days=1)
                    balance_amount = (
                        cleanDecimal(debit) if debit else -cleanDecimal(credit)
                    )
            except Exception:
                pass

    # Write to CSV file
    with open(csv_file_name, "w") as f:
        # Header
        f.write("Date;Amount;Description\n")

        # Balance
        if balance_date is not None and balance_amount is not None:
            f.write(f"{balance_date};{balance_amount};BALANCE\n")

        # Transactions
        for transaction in transactions:
            f.write("{};{};{}\n".format(*transaction))


class Importer(beangulp.Importer):
    """An importer for Cembra Certo One Statement PDF files."""

    def __init__(
        self,
        filepattern: str,
        account: data.Account,
        narration_map: dict[str, tuple[str, str]] | None = None,
    ):
        self._filepattern = filepattern
        self._account = account
        self.currency = "CHF"
        self.narration_map: dict[str, tuple[str, str]] = narration_map or {}

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

    def account(self, _: str | None = None) -> data.Account:
        return self._account

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

        # Parse the PDF to a CSV file
        csv_file = Path(path).with_suffix(".csv")
        if not csv_file.is_file():
            parse_pdf_to_csv(path, str(csv_file))

        # Read the CSV file
        with open(str(csv_file)) as csvfile:
            reader = csv.reader(csvfile, delimiter=";")
            rows = list(reader)

        # Balance
        parsed_balance_date = parse(rows[1][0].strip(), dayfirst=False)
        if isinstance(parsed_balance_date, datetime):
            balance_date = parsed_balance_date.date()
        elif isinstance(parsed_balance_date, date):
            balance_date = parsed_balance_date
        else:
            balance_date = date.today()
        entries.append(
            data.Balance(
                data.new_metadata(path, 0),
                balance_date,
                self._account,
                amount.Amount(-D(rows[1][1]), self.currency),
                None,
                None,
            )
        )

        # Transactions
        for row in rows[2:]:
            parsed_date = parse(row[0].strip(), dayfirst=False)
            if isinstance(parsed_date, datetime):
                transaction_date = parsed_date.date()
            elif isinstance(parsed_date, date):
                transaction_date = parsed_date
            else:
                transaction_date = date.today()
            cash_flow = D(row[1])
            beschreibung = row[2]
            meta = data.new_metadata(path, 0)

            payee = ""
            narration = beschreibung
            for pattern, (p, n) in self.narration_map.items():
                if re.search(pattern, beschreibung):
                    payee = p
                    narration = n
                    break

            entries.append(
                data.Transaction(
                    meta,
                    transaction_date,
                    "*",
                    payee,
                    narration,
                    data.EMPTY_SET,
                    data.EMPTY_SET,
                    [
                        data.Posting(
                            self._account,
                            amount.Amount(D(cash_flow), self.currency),
                            None,
                            None,
                            None,
                            None,
                        )
                    ],
                )
            )

        return entries
