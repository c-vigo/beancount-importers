import csv
import re
from collections.abc import Iterable
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

# Header of the transaction table, repeated on every page it spans.
TRANSACTION_HEADER_RE = re.compile(r"Verbucht am\s+Beschreibung")
# Closing balance. The amount is captured too, because the balance sometimes
# comes as a table of its own whose columns are not the transaction columns.
BALANCE_RE = re.compile(
    r"Saldo per (\d\d\.\d\d\.\d\d\d\d) zu unseren Gunsten CHF\s*([\d'.]*)"
)
# Area of a statement page holding the transaction table, in PDF points.
TABLE_AREA = "50,700,560,90"


def cleanDecimal(formatted_number: str) -> Decimal:
    return D(formatted_number.replace("'", ""))


def balance_as_of(formatted_date: str) -> date:
    """Day on which a stated closing balance holds.

    Cembra states the balance at the end of the billing day, beancount asserts
    it at the start of one, so the assertion belongs to the following day.
    """
    return datetime.strptime(formatted_date, "%d.%m.%Y").date() + timedelta(days=1)


def statement_pages(pdf_file_name: str) -> list[int]:
    """Page numbers of the pages that carry statement data.

    The statement proper starts on page 2 — page 1 is the invoice summary, and
    it repeats the balance line — and runs over as many pages as the
    transactions need. What follows it varies from month to month: a payment
    slip, the terms, and once a quarter the cashback summary (#11). Deriving
    the length of that trailer from the page count silently changes which pages
    are read whenever the issuer adds one, so select on content instead and
    keep the pages carrying the transaction header or the closing balance.
    """
    reader = PdfReader(pdf_file_name)
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        if number == 1:
            continue
        text = page.extract_text()
        if TRANSACTION_HEADER_RE.search(text) or BALANCE_RE.search(text):
            pages.append(number)
    return pages


def parse_tables(
    tables: Iterable[Any],
) -> tuple[list[list[Any]], date | None, Decimal | None]:
    """Split tables read off a statement into transactions and the balance.

    Accepts anything iterable over objects exposing camelot's ``.df``.
    """
    transactions: list[list[Any]] = []
    balance_date: date | None = None
    balance_amount: Decimal | None = None

    for table in tables:
        for _index, row in table.df.iterrows():
            cells = [str(cell).strip() for cell in tuple(row)]

            if len(cells) == 5:
                _, book_date, text, credit, debit = cells
            elif len(cells) == 4:
                book_date, text, credit, debit = cells
            else:
                # Any other table: the balance when it stands on its own, the
                # quarterly cashback summary, or a stray bit of the trailer.
                # Match the joined row so that no column count is assumed.
                balance_match = BALANCE_RE.search(" ".join(c for c in cells if c))
                if balance_match:
                    balance_date = balance_as_of(balance_match.group(1))
                    balance_amount = cleanDecimal(balance_match.group(2) or cells[-1])
                continue

            # Transaction entry
            try:
                booked_on = datetime.strptime(book_date, "%d.%m.%Y").date()
            except ValueError:
                booked_on = None

            if booked_on:
                if not credit and not debit:
                    # A dated row with both amount columns empty is not a
                    # transaction: the table area missed the amounts, as it
                    # does on the oldest statement layout.
                    continue
                value = -cleanDecimal(debit) if debit else cleanDecimal(credit)
                transactions.append([booked_on, value, text])
                continue

            # Balance entry
            try:
                balance_match = BALANCE_RE.search(text)
                if balance_match:
                    balance_date = balance_as_of(balance_match.group(1))
                    balance_amount = (
                        cleanDecimal(debit) if debit else -cleanDecimal(credit)
                    )
            except Exception:
                pass

    return transactions, balance_date, balance_amount


def parse_pdf_to_csv(pdf_file_name: str, csv_file_name: str) -> None:
    pages = statement_pages(pdf_file_name)
    if not pages:
        raise ValueError(
            f"{pdf_file_name}: no page carries the transaction header or the "
            "closing balance, the statement layout may have changed"
        )

    # Read tables
    tables = camelot.read_pdf(
        pdf_file_name,
        pages=",".join(str(page) for page in pages),
        flavor="stream",
        table_areas=[TABLE_AREA],
    )

    # Visual debugging
    # camelot.plot(tables[0], kind='text').show()
    # camelot.plot(tables[0], kind='grid').show()

    transactions, balance_date, balance_amount = parse_tables(tables)

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
