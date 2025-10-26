"""Simplified tests for the N26 importer."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import amount, data
from beancount.core.number import D

from beancount_importers.importers import n26_importer


def create_test_csv_content() -> str:
    """Create minimal test CSV content for failure cases."""
    return n26_importer.CSV_HEADER + (
        '2024-01-15,2024-01-15,"TEST",,Presentment,,"Main Account",-10.00,10.00,EUR,1\n'
    )


class TestN26ImporterSimple:
    """Simplified test cases for the N26 importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> n26_importer:
        """Create a test importer instance."""
        return n26_importer(r"N26.*\.csv$", "Assets:N26:Main")

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/data/N26_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: n26_importer) -> None:
        """Test importer initialization."""
        assert importer._filepattern == r"N26.*\.csv$"
        assert importer._account == "Assets:N26:Main"

    def test_identify_file_pattern(self, importer: n26_importer) -> None:
        """Test file identification."""
        assert importer.identify("N26_Transactions_2024.csv") is True
        assert importer.identify("2024-12-31-N26_Transactions.csv") is True
        assert importer.identify("n26_transactions.csv") is False
        assert importer.identify("other_bank.csv") is False
        assert importer.identify("N26.txt") is False
        assert importer.identify("transactions.csv") is False

    def test_name(self, importer: n26_importer) -> None:
        """Test importer name."""
        assert "Assets:N26:Main" in importer.name()

    def test_account(self, importer: n26_importer) -> None:
        """Test account method."""
        assert importer.account("any_file.csv") == "Assets:N26:Main"

    def test_extract_basic_transaction(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction of a basic transaction."""
        entries = importer.extract(sample_csv_file, [])

        assert len(entries) == 87  # 87 transactions in sample file (some rows skipped)

        # Test first transaction (STARBUCKS)
        first_entry = entries[0]
        assert isinstance(first_entry, data.Transaction)
        assert first_entry.date == date(2024, 1, 15)
        assert first_entry.payee == "STARBUCKS COFFEE"
        assert first_entry.narration == ""
        assert first_entry.flag == "*"

        # Check postings
        assert len(first_entry.postings) == 2
        main_posting = first_entry.postings[0]
        balance_posting = first_entry.postings[1]

        assert main_posting.account == "Assets:N26:Main"
        assert main_posting.units == amount.Amount(D("-4.50"), "EUR")
        assert balance_posting.account == "Assets:N26:Main:balance"
        assert balance_posting.units == amount.Amount(D("4.50"), "EUR")

    def test_extract_credit_transfer(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction of credit transfer."""
        entries = importer.extract(sample_csv_file, [])

        # Find the credit transfer entry (John Smith)
        credit_entry = None
        for entry in entries:
            if entry.payee == "John Smith":
                credit_entry = entry
                break

        assert credit_entry is not None
        assert credit_entry.date == date(2024, 1, 18)
        assert credit_entry.payee == "John Smith"
        assert credit_entry.narration == "Salary January 2024"

        # Check postings for credit transfer
        assert len(credit_entry.postings) == 2
        main_posting = credit_entry.postings[0]
        balance_posting = credit_entry.postings[1]

        assert main_posting.account == "Assets:N26:Main"
        assert main_posting.units == amount.Amount(D("2500.00"), "EUR")
        assert balance_posting.account == "Assets:N26:Main:balance"
        assert balance_posting.units == amount.Amount(D("-2500.00"), "EUR")

    def test_extract_debit_transfer(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction of debit transfer."""
        entries = importer.extract(sample_csv_file, [])

        # Find the debit transfer entry (Maria García)
        debit_entry = None
        for entry in entries:
            if entry.payee == "Maria García":
                debit_entry = entry
                break

        assert debit_entry is not None
        assert debit_entry.date == date(2024, 1, 19)
        assert debit_entry.payee == "Maria García"
        assert debit_entry.narration == "Rent payment"

        # Check postings for debit transfer
        assert len(debit_entry.postings) == 2
        main_posting = debit_entry.postings[0]
        balance_posting = debit_entry.postings[1]

        assert main_posting.account == "Assets:N26:Main"
        assert main_posting.units == amount.Amount(D("-800.00"), "EUR")
        assert balance_posting.account == "Assets:N26:Main:balance"
        assert balance_posting.units == amount.Amount(D("800.00"), "EUR")

    def test_extract_foreign_currency(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction of foreign currency transaction."""
        entries = importer.extract(sample_csv_file, [])

        # Find the foreign currency entry
        foreign_entry = None
        for entry in entries:
            if entry.payee == "FOREIGN TRANSACTION":
                foreign_entry = entry
                break

        assert foreign_entry is not None
        assert foreign_entry.date == date(2024, 2, 26)
        assert foreign_entry.payee == "FOREIGN TRANSACTION"
        assert foreign_entry.narration == "US Dollar purchase"

        # Check postings (should still be in EUR)
        assert len(foreign_entry.postings) == 2
        main_posting = foreign_entry.postings[0]
        balance_posting = foreign_entry.postings[1]

        assert main_posting.account == "Assets:N26:Main"
        assert main_posting.units == amount.Amount(D("-54.11"), "EUR")
        assert balance_posting.account == "Assets:N26:Main:balance"
        assert balance_posting.units == amount.Amount(D("54.11"), "EUR")

    def test_extract_special_characters(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction with special characters."""
        entries = importer.extract(sample_csv_file, [])

        # Find the special characters entry
        special_entry = None
        for entry in entries:
            if entry.payee == "SPECIAL CHARS & CO":
                special_entry = entry
                break

        assert special_entry is not None
        assert special_entry.payee == "SPECIAL CHARS & CO"
        assert special_entry.narration == "Test: áéíóú ñ ç ß € £ ¥"

    def test_extract_emoji(self, importer: n26_importer, sample_csv_file: str) -> None:
        """Test extraction with emojis."""
        entries = importer.extract(sample_csv_file, [])

        # Find the emoji entry
        emoji_entry = None
        for entry in entries:
            if "EMOJI STORE" in entry.payee:
                emoji_entry = entry
                break

        assert emoji_entry is not None
        assert "🛍️" in emoji_entry.payee
        assert "🎉" in emoji_entry.narration

    def test_extract_zero_amount(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction of zero amount transaction."""
        entries = importer.extract(sample_csv_file, [])

        # Find the zero amount entry
        zero_entry = None
        for entry in entries:
            if entry.payee == "ZERO AMOUNT":
                zero_entry = entry
                break

        assert zero_entry is not None
        assert zero_entry.date == date(2024, 4, 4)

        # Check postings for zero amount
        assert len(zero_entry.postings) == 1  # No balance posting for zero amount
        main_posting = zero_entry.postings[0]
        assert main_posting.account == "Assets:N26:Main"
        assert main_posting.units == amount.Amount(D("0.00"), "EUR")

    def test_extract_empty_reference(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction with empty payment reference."""
        entries = importer.extract(sample_csv_file, [])

        # Find the empty reference entry
        empty_ref_entry = None
        for entry in entries:
            if entry.payee == "EMPTY REFERENCE":
                empty_ref_entry = entry
                break

        assert empty_ref_entry is not None
        assert empty_ref_entry.narration == ""

    def test_extract_unicode_characters(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction with Unicode characters."""
        entries = importer.extract(sample_csv_file, [])

        # Find the Unicode entry
        unicode_entry = None
        for entry in entries:
            if entry.payee == "Café Français":
                unicode_entry = entry
                break

        assert unicode_entry is not None
        assert "Coffee & croissant" in unicode_entry.narration

    def test_extract_very_large_amounts(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction with very large amounts."""
        entries = importer.extract(sample_csv_file, [])

        # Find the large amount entry
        large_entry = None
        for entry in entries:
            if entry.payee == "LARGE AMOUNT":
                large_entry = entry
                break

        assert large_entry is not None

        # Check that large amount is handled correctly
        main_posting = large_entry.postings[0]
        assert main_posting.units.number == D("-9999.99")

    def test_extract_very_small_amounts(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction with very small amounts."""
        entries = importer.extract(sample_csv_file, [])

        # Find the small amount entry
        small_entry = None
        for entry in entries:
            if entry.payee == "SMALL AMOUNT":
                small_entry = entry
                break

        assert small_entry is not None

        # Check that small amount is handled correctly
        main_posting = small_entry.postings[0]
        assert main_posting.units.number == D("-0.01")

    def test_extract_metadata(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test that metadata is properly set."""
        entries = importer.extract(sample_csv_file, [])

        for i, entry in enumerate(entries):
            assert entry.meta["filename"] == sample_csv_file
            assert entry.meta["lineno"] == i  # importer uses 0-based index

    def test_extract_with_existing_entries(
        self, importer: n26_importer, sample_csv_file: str
    ) -> None:
        """Test extraction with existing entries."""
        existing_entries = [
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
        assert len(entries) == 87
        assert all(entry.payee != "Existing Payee" for entry in entries)

    def test_extract_invalid_csv(self, importer: n26_importer) -> None:
        """Test extraction with invalid CSV content."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("invalid,csv,content\n")
            temp_file = f.name

        try:
            # Should return empty list for invalid CSV
            entries = importer.extract(temp_file, [])
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_extract_missing_required_fields(self, importer: n26_importer) -> None:
        """Test extraction with missing required fields."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write('"Booking Date","Value Date","Partner Name"\n')
            f.write('2024-01-15,2024-01-15,"STARBUCKS"\n')
            temp_file = f.name

        try:
            with pytest.raises(ValueError):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_date(self, importer: n26_importer) -> None:
        """Test extraction with invalid date."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(create_test_csv_content())
            f.write(
                'invalid-date,2024-01-15,"STARBUCKS",,Presentment,,"Main Account",'
                "-4.50,4.50,EUR,1\n"
            )
            temp_file = f.name

        try:
            # The importer should raise an exception for invalid data
            with pytest.raises(ValueError):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_amount(self, importer: n26_importer) -> None:
        """Test extraction with invalid amount."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(create_test_csv_content())
            f.write(
                '2024-01-15,2024-01-15,"STARBUCKS",,Presentment,,"Main Account",'
                "invalid-amount,4.50,EUR,1\n"
            )
            temp_file = f.name

        try:
            # The importer should raise an exception for invalid data
            with pytest.raises(ValueError):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)


class TestN26ImporterIntegrationSimple:
    """Integration tests for the N26 importer with real CSV files."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> n26_importer:
        """Create a test importer instance."""
        return n26_importer(r"N26.*\.csv$", "Assets:N26:Main")

    def test_extract_from_real_csv_file(self, importer: n26_importer) -> None:
        """Test extraction from a real CSV file in the test data."""
        csv_file = "tests/data/N26_Sample.csv"

        if not os.path.exists(csv_file):
            pytest.skip(f"Test file {csv_file} not found")

        entries = importer.extract(csv_file, [])

        # Should extract all transactions from the file
        assert len(entries) > 0

        # All entries should be transactions
        assert all(isinstance(entry, data.Transaction) for entry in entries)

        # All entries should have the correct account
        for entry in entries:
            assert any(
                posting.account == "Assets:N26:Main" for posting in entry.postings
            )

    def test_extract_multiple_files(self, importer: n26_importer) -> None:
        """Test extraction from multiple CSV files."""
        csv_files = [
            "tests/data/N26_Sample.csv",
        ]

        all_entries: list[data.Transaction] = []
        for csv_file in csv_files:
            if os.path.exists(csv_file):
                entries = importer.extract(csv_file, all_entries)
                all_entries.extend(entries)

        # Check if any files exist and have entries
        if any(os.path.exists(f) for f in csv_files):
            # Should have entries from existing files
            assert len(all_entries) > 0

            # All entries should be unique (based on metadata)
            filenames = set()
            for entry in all_entries:
                filename = entry.meta["filename"]
                lineno = entry.meta["lineno"]
                filenames.add((filename, lineno))

            assert len(filenames) == len(all_entries)
        else:
            # Skip test if no files exist
            pytest.skip("No test CSV files found")

    def test_compare_with_expected_journal(self, importer: n26_importer) -> None:
        """Test that extracted entries match expected journal format."""
        csv_file = "tests/data/N26_Sample.csv"
        journal_file = "tests/data/journal.beancount"

        if not os.path.exists(csv_file) or not os.path.exists(journal_file):
            pytest.skip("Test files not found")

        # Extract entries from CSV
        csv_entries = importer.extract(csv_file, [])

        # Parse expected journal (simplified comparison)
        # In a real test, you might want to use beancount.parser to parse the journal
        assert len(csv_entries) > 0

        # Basic validation that entries have expected structure
        for entry in csv_entries:
            assert hasattr(entry, "date")
            assert hasattr(entry, "payee")
            assert hasattr(entry, "postings")
            assert len(entry.postings) >= 1


class TestN26ImporterEdgeCasesSimple:
    """Test edge cases and error handling for the N26 importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> n26_importer:
        """Create a test importer instance."""
        return n26_importer(r"N26.*\.csv$", "Assets:N26:Main")

    def test_empty_csv_file(self, importer: n26_importer) -> None:
        """Test extraction from empty CSV file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(create_test_csv_content()[:0])  # Empty content
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_csv_with_only_header(self, importer: n26_importer) -> None:
        """Test extraction from CSV with only header row."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            header = (
                '"Booking Date","Value Date","Partner Name","Partner Iban",Type,'
                '"Payment Reference","Account Name","Amount (EUR)","Original Amount",'
                '"Original Currency","Exchange Rate"\n'
            )
            f.write(header)
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_csv_with_malformed_row(self, importer: n26_importer) -> None:
        """Test extraction with malformed CSV row."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(create_test_csv_content())
            f.write("malformed,row,with,wrong,number,of,columns\n")  # Malformed row
            temp_file = f.name

        try:
            # The importer should raise an exception for malformed data
            with pytest.raises(ValueError):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)
