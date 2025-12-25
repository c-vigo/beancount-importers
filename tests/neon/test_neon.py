"""Tests for the Neon importer."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import data
from beancount.core.number import D

from beancount_importers.importers.neon import Importer


class TestNeonImporter:
    """Tests for the Neon importer covering all transaction types."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance."""
        return Importer(
            r"Neon.*\.csv$",
            "Assets:Neon:CHF",
        )

    @pytest.fixture  # type: ignore[misc]
    def importer_with_map(self) -> Importer:
        """Create an importer instance with description mapping."""
        return Importer(
            r"Neon.*\.csv$",
            "Assets:Neon:CHF",
            map={
                "Employer Name": ("Employer Corp", "Monthly salary"),
                "Landlord": ("Jane Doe", "Rent payment"),
            },
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/neon/Neon_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test that the importer initializes correctly."""
        assert importer._filepattern == r"Neon.*\.csv$"
        assert importer._account == "Assets:Neon:CHF"
        assert importer.map == {}

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test that the importer identifies files correctly."""
        assert importer.identify("Neon_Sample.csv") is True
        assert importer.identify("2024-12-31-Neon_AccountStatement.csv") is True
        assert importer.identify("revolut.csv") is False
        assert importer.identify("other_file.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test that the importer name is correct."""
        name = importer.name()
        assert "neon" in name.lower()
        assert "Assets:Neon:CHF" in name

    def test_account(self, importer: Importer) -> None:
        """Test that the account method returns the correct account."""
        assert importer.account() == "Assets:Neon:CHF"

    def test_extract_all_transaction_types(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting all transaction types from the sample file."""
        entries = importer.extract(sample_csv_file)

        # Should have extracted transactions (processed in reverse order)
        assert len(entries) > 0

        # Check that all entries are transactions
        for entry in entries:
            assert isinstance(entry, data.Transaction)

        # Find a specific transaction by date (last in file = first processed)
        jan_25_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.date == date(2024, 1, 25)
            ),
            None,
        )
        assert jan_25_entry is not None
        assert isinstance(jan_25_entry, data.Transaction)
        assert jan_25_entry.narration == "Employer Name"
        assert jan_25_entry.payee == ""

    def test_extract_chf_transaction(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting a CHF transaction."""
        entries = importer.extract(sample_csv_file)

        # Find a CHF transaction (no foreign currency)
        chf_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 12, 30)
                and e.postings
                and e.postings[0].units is not None
                and e.postings[0].units.currency == "CHF"
            ),
            None,
        )
        assert chf_entry is not None
        assert chf_entry.postings
        posting_units = chf_entry.postings[0].units
        assert posting_units is not None
        assert posting_units.number is not None
        assert posting_units.number == D("-3000.00")
        assert posting_units.currency == "CHF"

        # Check metadata - should have category but no foreign currency info
        posting_meta = chf_entry.postings[0].meta
        assert posting_meta is not None
        assert posting_meta.get("category") == "finances"
        assert "original_currency" not in posting_meta

    def test_extract_foreign_currency_transaction(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting a foreign currency transaction."""
        entries = importer.extract(sample_csv_file)

        # Find a USD transaction
        usd_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 5, 26)
                and e.postings
                and e.postings[0].units is not None
                and e.postings[0].units.currency == "CHF"
            ),
            None,
        )
        assert usd_entry is not None
        assert usd_entry.postings
        posting_units = usd_entry.postings[0].units
        assert posting_units is not None
        assert posting_units.number is not None
        assert posting_units.number == D("-69.46")
        assert posting_units.currency == "CHF"

        # Check metadata - should have foreign currency info
        posting_meta = usd_entry.postings[0].meta
        assert posting_meta is not None
        assert posting_meta.get("category") == "travel"
        assert posting_meta.get("original_currency") == "USD"
        assert posting_meta.get("original_amount") == "-75.80"
        assert posting_meta.get("exchange_rate") == "1.09128"

    def test_extract_multiple_currencies(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transactions with multiple foreign currencies."""
        entries = importer.extract(sample_csv_file)

        # Find EUR transaction
        eur_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 3, 1)
                and e.postings
                and e.postings[0].meta
                and e.postings[0].meta.get("original_currency") == "EUR"
            ),
            None,
        )
        assert eur_entry is not None
        assert isinstance(eur_entry, data.Transaction)
        assert eur_entry.postings
        posting_meta = eur_entry.postings[0].meta
        assert posting_meta is not None
        assert posting_meta.get("original_currency") == "EUR"
        assert posting_meta.get("original_amount") == "-14.70"
        assert posting_meta.get("exchange_rate") == "1.04701"

        # Find MXN transaction
        mxn_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 5, 21)
                and e.postings
                and e.postings[0].meta
                and e.postings[0].meta.get("original_currency") == "MXN"
            ),
            None,
        )
        assert mxn_entry is not None
        assert isinstance(mxn_entry, data.Transaction)
        assert mxn_entry.postings
        posting_meta = mxn_entry.postings[0].meta
        assert posting_meta is not None
        assert posting_meta.get("original_currency") == "MXN"
        assert posting_meta.get("exchange_rate") == "18.18182"

        # Find CAD transaction
        cad_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 4, 5)
                and e.postings
                and e.postings[0].meta
                and e.postings[0].meta.get("original_currency") == "CAD"
            ),
            None,
        )
        assert cad_entry is not None
        assert isinstance(cad_entry, data.Transaction)
        assert cad_entry.postings
        posting_meta = cad_entry.postings[0].meta
        assert posting_meta is not None
        assert posting_meta.get("original_currency") == "CAD"
        assert posting_meta.get("exchange_rate") == "1.48305"

    def test_extract_description_mapping(
        self, importer_with_map: Importer, sample_csv_file: str
    ) -> None:
        """Test that description mapping works correctly."""
        entries = importer_with_map.extract(sample_csv_file)

        # Find an entry with mapped description
        mapped_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 12, 20)
                and e.narration == "Monthly salary"
            ),
            None,
        )
        assert mapped_entry is not None
        assert isinstance(mapped_entry, data.Transaction)
        assert mapped_entry.payee == "Employer Corp"
        assert mapped_entry.narration == "Monthly salary"

        # Find an entry without mapping
        unmapped_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 12, 30)
                and e.narration == "Investment Broker"
            ),
            None,
        )
        assert unmapped_entry is not None
        assert unmapped_entry.payee == ""
        assert unmapped_entry.narration == "Investment Broker"

    def test_extract_categories(self, importer: Importer, sample_csv_file: str) -> None:
        """Test that categories are correctly extracted."""
        entries = importer.extract(sample_csv_file)

        # Check various categories
        categories_found = set()
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.postings
                and entry.postings[0].meta
            ):
                cat = entry.postings[0].meta.get("category")
                if cat:
                    categories_found.add(cat)

        # Should have multiple categories
        assert "finances" in categories_found
        assert "housing" in categories_found
        assert "income_salary" in categories_found
        assert "food" in categories_found
        assert "travel" in categories_found
        assert "income" in categories_found

    def test_extract_metadata(self, importer: Importer, sample_csv_file: str) -> None:
        """Test that transaction metadata is correctly set."""
        entries = importer.extract(sample_csv_file)

        # Check first entry metadata
        first_entry = entries[0]
        assert isinstance(first_entry, data.Transaction)
        assert first_entry.meta["filename"] == sample_csv_file
        assert isinstance(first_entry.date, date)
        assert first_entry.flag == "*"

    def test_extract_with_existing_entries(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that extract works with existing entries."""
        existing: data.Entries = [
            data.Transaction(
                data.new_metadata("test.beancount", 0),
                date(2024, 1, 1),
                "*",
                "",
                "Existing entry",
                data.EMPTY_SET,
                data.EMPTY_SET,
                [],
            )
        ]

        entries = importer.extract(sample_csv_file, existing_entries=existing)
        # Should still extract all transactions
        assert len(entries) > 0

    def test_extract_nonexistent_file(self, importer: Importer) -> None:
        """Test that extract handles nonexistent files gracefully."""
        with pytest.raises(FileNotFoundError):
            importer.extract("nonexistent_file.csv")

    def test_extract_empty_csv_file(self, importer: Importer) -> None:
        """Test that extract handles empty CSV files."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                '"Date";"Amount";"Original amount";"Original currency";'
                '"Exchange rate";"Description";"Subject";"Category";"Tags";'
                '"Wise";"Spaces"\n'
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            assert entries == []
        finally:
            os.unlink(temp_path)

    def test_extract_reversed_order(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that transactions are processed in reverse order."""
        entries = importer.extract(sample_csv_file)

        # First entry should be from the last line in the file
        # (2024-01-25 is the last date in the sample file)
        assert isinstance(entries[0], data.Transaction)
        assert entries[0].date == date(2024, 1, 25)

        # Last entry should be from the first line in the file
        # (2024-12-30 is the first date in the sample file)
        assert isinstance(entries[-1], data.Transaction)
        assert entries[-1].date == date(2024, 12, 30)

    def test_extract_income_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting income transactions."""
        entries = importer.extract(sample_csv_file)

        # Find salary transaction
        salary_entry = next(
            (
                e
                for e in entries
                if (
                    isinstance(e, data.Transaction)
                    and e.date == date(2024, 12, 20)
                    and e.postings
                    and e.postings[0].units is not None
                    and e.postings[0].units.number is not None
                    and e.postings[0].units.number > 0
                )
            ),
            None,
        )
        assert salary_entry is not None
        assert isinstance(salary_entry, data.Transaction)
        assert salary_entry.postings
        posting_units = salary_entry.postings[0].units
        assert posting_units is not None
        assert posting_units.number is not None
        assert posting_units.number == D("7484.95")
        posting_meta = salary_entry.postings[0].meta
        assert posting_meta is not None
        assert posting_meta.get("category") == "income_salary"

    def test_extract_expense_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting expense transactions."""
        entries = importer.extract(sample_csv_file)

        # Find expense transaction (there are two on 2024-12-24, find the smaller one)
        expense_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 12, 24)
                and e.postings
                and e.postings[0].units is not None
                and e.postings[0].units.number is not None
                and e.postings[0].units.number == D("-24.95")
                and e.postings[0].meta is not None
                and e.postings[0].meta.get("category") == "housing"
            ),
            None,
        )
        assert expense_entry is not None
        assert isinstance(expense_entry, data.Transaction)
        assert expense_entry.postings
        posting_units = expense_entry.postings[0].units
        assert posting_units is not None
        assert posting_units.number is not None
        assert posting_units.number == D("-24.95")
        assert expense_entry.narration == "Internet Provider"
