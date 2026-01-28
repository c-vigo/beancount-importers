"""Tests for the ZKB importer."""

import os
import tempfile
import warnings
from datetime import date

import pytest
from beancount.core import amount, data
from beancount.core.number import D

from beancount_importers.importers.zkb import ZkbCSVImporter


class TestZkbCSVImporter:
    """Tests for the ZKB CSV importer covering all transaction types."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> ZkbCSVImporter:
        """Create an importer instance."""
        return ZkbCSVImporter(r"ZKB.*\.csv$", "Assets:ZKB:Checking")

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the simplified sample CSV file."""
        csv_path = "tests/zkb/ZKB_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: ZkbCSVImporter) -> None:
        """Test importer initialization."""
        assert importer._filepattern == r"ZKB.*\.csv$"
        assert importer._account == "Assets:ZKB:Checking"

    def test_identify_file_pattern(self, importer: ZkbCSVImporter) -> None:
        """Test file identification."""
        assert importer.identify("ZKB_Transactions.csv") is True
        assert importer.identify("2024-12-31-ZKB_Transactions.csv") is True
        assert importer.identify("zkb_transactions.csv") is False
        assert importer.identify("other_bank.csv") is False
        assert importer.identify("ZKB.txt") is False

    def test_name(self, importer: ZkbCSVImporter) -> None:
        """Test importer name."""
        assert "Assets:ZKB:Checking" in importer.name()

    def test_account(self, importer: ZkbCSVImporter) -> None:
        """Test account method."""
        assert importer.account("any_file.csv") == "Assets:ZKB:Checking"

    def test_extract_all_transaction_types(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test that all transaction types are extracted correctly."""
        entries = importer.extract(sample_csv_file, [])

        # Should extract 7 transactions
        assert len(entries) == 7

        # All entries should be transactions
        assert all(isinstance(entry, data.Transaction) for entry in entries)

    def test_extract_credit_transaction(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test credit (deposit) transaction."""
        entries = importer.extract(sample_csv_file, [])

        credit_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration is not None
                and "Credit salary" in entry.narration
            ):
                credit_entry = entry
                break

        assert credit_entry is not None
        assert credit_entry.date == date(2024, 1, 1)
        assert credit_entry.payee == ""
        assert credit_entry.flag == "*"
        assert len(credit_entry.postings) == 1
        assert credit_entry.postings[0].account == "Assets:ZKB:Checking"
        assert credit_entry.postings[0].units == amount.Amount(D("5000.00"), "CHF")

    def test_extract_debit_transaction(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test debit (withdrawal) transaction."""
        entries = importer.extract(sample_csv_file, [])

        debit_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration is not None
                and "Debit TWINT" in entry.narration
                and entry.date == date(2024, 1, 5)
            ):
                debit_entry = entry
                break

        assert debit_entry is not None
        assert debit_entry.date == date(2024, 1, 5)
        assert len(debit_entry.postings) == 1
        assert debit_entry.postings[0].account == "Assets:ZKB:Checking"
        assert debit_entry.postings[0].units == amount.Amount(D("-25.50"), "CHF")

    def test_extract_transaction_types(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test various transaction types."""
        entries = importer.extract(sample_csv_file, [])

        narrations = {
            entry.narration
            for entry in entries
            if isinstance(entry, data.Transaction) and entry.narration is not None
        }

        # Check for different transaction types
        assert any("Credit salary" in n for n in narrations)
        assert any("Debit TWINT" in n for n in narrations)
        assert any("Debit eBill" in n for n in narrations)
        assert any("Debit Mobile Banking" in n for n in narrations)
        assert any("Purchase ZKB Visa" in n for n in narrations)
        assert any("Debit Standing order" in n for n in narrations)
        assert any("Credit TWINT" in n for n in narrations)

    def test_extract_zkb_reference_metadata(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test that ZKB reference is stored in metadata."""
        entries = importer.extract(sample_csv_file, [])

        # Find an entry with ZKB reference in posting metadata
        # In beancount, Posting is a namedtuple with metadata as the 6th field
        for entry in entries:
            if isinstance(entry, data.Transaction):
                for posting in entry.postings:
                    # Access metadata - 6th field of Posting
                    posting_meta = posting.meta if hasattr(posting, "meta") else None
                    if posting_meta and isinstance(posting_meta, dict):
                        if "zkb_reference" in posting_meta:
                            assert posting_meta["zkb_reference"] in [
                                "Z001",
                                "L001",
                                "Z002",
                                "Z003",
                                "L002",
                                "Z004",
                                "L003",
                            ]
                            return
        pytest.fail("No entry found with zkb_reference metadata")

    def test_extract_metadata(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test that metadata is properly set."""
        entries = importer.extract(sample_csv_file, [])

        for entry in entries:
            assert entry.meta["filename"] == sample_csv_file
            assert "lineno" in entry.meta

    def test_extract_with_existing_entries(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test extraction with existing entries."""
        existing_entries: data.Entries = [
            data.Transaction(
                data.new_metadata("existing.beancount", 1),
                date(2024, 1, 1),
                "*",
                "Existing Payee",
                "Existing transaction",
                data.EMPTY_SET,
                data.EMPTY_SET,
                [],
            )
        ]

        entries = importer.extract(sample_csv_file, existing_entries)

        # Should return only new entries, not existing ones
        assert len(entries) > 0
        assert all(
            not isinstance(entry, data.Transaction)
            or entry.narration != "Existing transaction"
            for entry in entries
        )

    def test_extract_nonexistent_file(self, importer: ZkbCSVImporter) -> None:
        """Test extraction from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            importer.extract("nonexistent.csv", [])

    def test_extract_empty_csv_file(self, importer: ZkbCSVImporter) -> None:
        """Test extraction from empty CSV file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                '"Date";"Booking text";"ZKB reference";"Reference number";'
                '"Debit CHF";"Credit CHF";"Value date";"Balance CHF"\n'
            )
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should return empty list for file with only header
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_extract_skip_rows_without_amount(self, importer: ZkbCSVImporter) -> None:
        """Test that rows without Debit or Credit are skipped."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                '"Date";"Booking text";"ZKB reference";"Reference number";'
                '"Debit CHF";"Credit CHF";"Value date";"Balance CHF"\n'
            )
            f.write('"01.01.2024";"Test";"Z001";"";"";"";"01.01.2024";"1000.00"\n')
            f.write('"02.01.2024";"Test";"Z002";"";"100.00";"";"02.01.2024";"900.00"\n')
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should only extract the row with amount
            assert len(entries) == 1
            assert entries[0].date == date(2024, 1, 2)
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_date(self, importer: ZkbCSVImporter) -> None:
        """Test extraction with invalid date."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                '"Date";"Booking text";"ZKB reference";"Reference number";'
                '"Debit CHF";"Credit CHF";"Value date";"Balance CHF"\n'
            )
            f.write(
                '"invalid-date";"Test";"Z001";"";"100.00";"";"01.01.2024";"1000.00"\n'
            )
            temp_file = f.name

        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                entries = importer.extract(temp_file, [])
                # Should handle invalid date gracefully
                assert isinstance(entries, list)
        finally:
            os.unlink(temp_file)

    def test_extract_date_format(
        self, importer: ZkbCSVImporter, sample_csv_file: str
    ) -> None:
        """Test that dates are parsed correctly from DD.MM.YYYY format."""
        entries = importer.extract(sample_csv_file, [])

        # Check all dates are parsed correctly
        for entry in entries:
            assert isinstance(entry, data.Transaction)
            assert entry.date.year == 2024
            assert entry.date.month in [1]  # All in January
            assert entry.date.day in [1, 5, 10, 15, 20, 25, 30]
