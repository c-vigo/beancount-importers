"""Tests for the SBB importer."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import data
from beancount.core.number import D

from beancount_importers.importers.sbb import Importer


class TestSBBImporter:
    """Tests for the SBB importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance."""
        return Importer(
            r"SBB.*\.csv$",
            "Expenses:Transport:SBB",
            "Person A",
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/sbb/SBB_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test that the importer initializes correctly."""
        assert importer._filepattern == r"SBB.*\.csv$"
        assert importer._account == "Expenses:Transport:SBB"
        assert importer.owner == "Person A"

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test that the importer identifies files correctly."""
        assert importer.identify("SBB_Sample.csv") is True
        assert importer.identify("2024-12-31-SBB_Tickets.csv") is True
        assert importer.identify("sbb_tickets.pdf") is False
        assert importer.identify("other_file.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test that the importer name is correct."""
        name = importer.name()
        assert "sbb" in name.lower()
        assert "Expenses:Transport:SBB" in name

    def test_account(self, importer: Importer) -> None:
        """Test that the account method returns the correct account."""
        assert importer.account() == "Expenses:Transport:SBB"

    def test_extract_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transactions from the sample file."""
        entries = importer.extract(sample_csv_file)

        # Should have extracted transactions
        assert len(entries) == 5

        # Check that all entries are transactions
        for entry in entries:
            assert isinstance(entry, data.Transaction)

        # Find a specific transaction
        transaction = next(
            (
                e
                for e in entries
                if e.date == date(2024, 1, 15) and "Zürich HB → Bern" in e.narration
            ),
            None,
        )
        assert transaction is not None
        assert transaction.payee == "SBB"
        assert transaction.postings[0].units.number == D("-25.50")
        assert transaction.postings[0].units.currency == "CHF"

    def test_extract_metadata(self, importer: Importer, sample_csv_file: str) -> None:
        """Test that transaction metadata is correctly set."""
        entries = importer.extract(sample_csv_file)

        # Check first entry metadata
        first_entry = entries[0]
        assert first_entry.meta["filename"] == sample_csv_file
        assert first_entry.meta.get("orderno") == "12345678"
        assert first_entry.meta.get("traveller") == "Person A"
        assert first_entry.meta.get("travel_date") == "2024-01-20"
        assert isinstance(first_entry.date, date)
        assert first_entry.flag == "*"

    def test_extract_all_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that all transactions are extracted correctly."""
        entries = importer.extract(sample_csv_file)

        # Check all transactions have correct amounts
        expected_amounts = [
            D("-25.50"),
            D("-14.00"),
            D("-32.00"),
            D("-28.75"),
            D("-38.50"),
        ]

        for entry, expected_amount in zip(entries, expected_amounts, strict=True):
            assert entry.postings[0].units.number == expected_amount
            assert entry.postings[0].units.currency == "CHF"
            assert entry.postings[0].account == "Expenses:Transport:SBB"

    def test_extract_with_existing_entries(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that extract works with existing entries."""
        existing = [
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
        assert len(entries) == 5

    def test_extract_nonexistent_file(self, importer: Importer) -> None:
        """Test that extract handles nonexistent files gracefully."""
        with pytest.warns(UserWarning):
            entries = importer.extract("nonexistent_file.csv")
            assert entries == []

    def test_extract_empty_csv_file(self, importer: Importer) -> None:
        """Test that extract handles empty CSV files."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            assert entries == []
        finally:
            os.unlink(temp_path)

    def test_extract_invalid_row(self, importer: Importer) -> None:
        """Test that extract handles invalid rows gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            f.write("ZVV Single Ticket,Zürich HB → Bern\n")  # Missing columns
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            # Should skip invalid row (no price, so skipped)
            assert len(entries) == 0
        finally:
            os.unlink(temp_path)

    def test_extract_invalid_date(self, importer: Importer) -> None:
        """Test that extract handles invalid dates gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            f.write(
                "ZVV Single Ticket,Zürich HB → Bern,,25.50,Person A,2024-01-20,"
                "2024-01-20 08:00 - 2024-01-20 09:30,invalid-date,12345678,"
                "Half Fare Card PLUS,person@example.com\n"
            )
            temp_path = f.name

        try:
            with pytest.warns(UserWarning):
                entries = importer.extract(temp_path)
                # Should skip invalid row
                assert len(entries) == 0
        finally:
            os.unlink(temp_path)

    def test_extract_filters_by_owner(self, importer: Importer) -> None:
        """Test that extract only includes transactions for the owner."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            f.write(
                "ZVV Single Ticket,Zürich HB → Bern,,25.50,Person A,2024-01-20,"
                "2024-01-20 08:00 - 2024-01-20 09:30,2024-01-15,12345678,"
                "Half Fare Card PLUS,person@example.com\n"
            )
            f.write(
                "ZVV Single Ticket,Zürich HB → Basel,,30.00,Person B,2024-01-21,"
                "2024-01-21 08:00 - 2024-01-21 09:30,2024-01-16,12345679,"
                "Half Fare Card PLUS,person@example.com\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            # Should only extract transaction for Person A
            assert len(entries) == 1
            assert entries[0].postings[0].units.number == D("-25.50")
        finally:
            os.unlink(temp_path)

    def test_extract_handles_missing_price(self, importer: Importer) -> None:
        """Test that extract handles missing price gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            f.write(
                "ZVV Single Ticket,Zürich HB → Bern,,,Person A,2024-01-20,"
                "2024-01-20 08:00 - 2024-01-20 09:30,2024-01-15,12345678,"
                "Half Fare Card PLUS,person@example.com\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            # Should skip row with missing price
            assert len(entries) == 0
        finally:
            os.unlink(temp_path)

    def test_extract_handles_different_date_formats(self, importer: Importer) -> None:
        """Test that extract handles different date formats."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            # Test DD.MM.YYYY format
            f.write(
                "ZVV Single Ticket,Zürich HB → Bern,,25.50,Person A,20.01.2024,"
                "20.01.2024 08:00 - 20.01.2024 09:30,15.01.2024,12345678,"
                "Half Fare Card PLUS,person@example.com\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            assert len(entries) == 1
            assert entries[0].date == date(2024, 1, 15)
        finally:
            os.unlink(temp_path)

    def test_extract_filters_non_half_fare_card_plus(self, importer: Importer) -> None:
        """Test that extract ignores non-'Half Fare Card PLUS' transactions."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Tariff,Route,Via (optional),Price,Co-passenger(s),Travel date,"
                "Validity,Order date,Order number,Payment methods,Purchaser e-mail\n"
            )
            # Transaction with Half Fare Card PLUS - should be included
            f.write(
                "ZVV Single Ticket,Zürich HB → Bern,,25.50,Person A,2024-01-20,"
                "2024-01-20 08:00 - 2024-01-20 09:30,2024-01-15,12345678,"
                "Half Fare Card PLUS,person@example.com\n"
            )
            # Transaction with Mastercard - should be ignored
            f.write(
                "ZVV Single Ticket,Zürich HB → Basel,,30.00,Person A,2024-06-10,"
                "2024-06-10 08:00 - 2024-06-10 09:30,2024-06-09,12345683,"
                "Mastercard,person@example.com\n"
            )
            # Transaction with empty payment method - should be ignored
            f.write(
                "ZVV Single Ticket,Zürich HB → Zürich Flughafen,,38.50,"
                "Person A,2024-05-25,2024-05-25 10:00 - 2024-05-25 11:00,"
                "2024-05-24,12345682,,person@example.com\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            # Should only extract the transaction with Half Fare Card PLUS
            assert len(entries) == 1
            assert entries[0].postings[0].units.number == D("-25.50")
            assert entries[0].meta.get("orderno") == "12345678"
        finally:
            os.unlink(temp_path)
