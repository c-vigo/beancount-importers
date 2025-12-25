"""Tests for the CertoOne importer."""

import os
import tempfile
from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest
from beancount.core import amount, data
from beancount.core.number import D

from beancount_importers.importers.certo_one import Importer, parse_pdf_to_csv


class TestCertoOneImporter:
    """Test cases for the CertoOne importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create a test importer instance."""
        return Importer(r"CertoOne.*\.pdf$", "Assets:CertoOne:Main")

    @pytest.fixture  # type: ignore[misc]
    def sample_pdf_file(self) -> str:
        """Get the path to the sample PDF file."""
        pdf_path = "tests/certo_one/CertoOne_Sample.pdf"
        if not os.path.exists(pdf_path):
            pytest.skip(f"Sample PDF file not found: {pdf_path}")
        return pdf_path

    @pytest.fixture  # type: ignore[misc]
    def csv_cleanup(self, sample_pdf_file: str) -> Generator[None, None, None]:
        """Cleanup fixture for CSV files created by tests."""
        csv_file = Path(sample_pdf_file).with_suffix(".csv")

        # Clean up any existing CSV file before test
        if csv_file.exists():
            csv_file.unlink()

        yield  # Run the test

        # Clean up CSV file after test
        if csv_file.exists():
            csv_file.unlink()

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test importer initialization."""
        assert importer._filepattern == r"CertoOne.*\.pdf$"
        assert importer._account == "Assets:CertoOne:Main"
        assert importer.currency == "CHF"

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test file identification."""
        assert importer.identify("CertoOne_Statement_2024.pdf") is True
        assert importer.identify("2024-12-31-CertoOne_Statement.pdf") is True
        assert importer.identify("certo_one_statement.pdf") is False
        assert importer.identify("other_bank.pdf") is False
        assert importer.identify("CertoOne.txt") is False
        assert importer.identify("statement.pdf") is False

    def test_identify_with_filememo_object(self, importer: Importer) -> None:
        """Test file identification with _FileMemo-like objects."""

        # Mock different types of _FileMemo-like objects
        class MockFileMemo1:
            def __init__(self, filepath: str):
                self.filepath = filepath

        class MockFileMemo2:
            def __init__(self, name: str):
                self.name = name

        class MockFileMemo3:
            def __init__(self, filename: str):
                self.filename = filename

        # Test with different _FileMemo-like objects
        assert importer.identify(MockFileMemo1("CertoOne_Statement_2024.pdf")) is True
        assert (
            importer.identify(MockFileMemo2("2024-12-31-CertoOne_Statement.pdf"))
            is True
        )
        assert importer.identify(MockFileMemo3("certo_one_statement.pdf")) is False
        assert importer.identify(MockFileMemo1("other_bank.pdf")) is False

    def test_extract_with_filememo_object(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction with _FileMemo-like objects."""

        # Mock different types of _FileMemo-like objects
        class MockFileMemo1:
            def __init__(self, filepath: str):
                self.filepath = filepath

        class MockFileMemo2:
            def __init__(self, name: str):
                self.name = name

        class MockFileMemo3:
            def __init__(self, filename: str):
                self.filename = filename

        # Test extraction with different _FileMemo-like objects
        entries1 = importer.extract(MockFileMemo1(sample_pdf_file), [])
        entries2 = importer.extract(MockFileMemo2(sample_pdf_file), [])
        entries3 = importer.extract(MockFileMemo3(sample_pdf_file), [])

        # All should produce the same number of entries
        assert len(entries1) == len(entries2) == len(entries3)
        assert len(entries1) > 0  # Should have some entries

        # Test with existing_entries keyword argument
        entries4 = importer.extract(MockFileMemo1(sample_pdf_file), existing_entries=[])
        assert len(entries4) == len(entries1)

    def test_extract_with_none_existing_entries(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction with None existing_entries."""
        # Test that None existing_entries is handled correctly
        entries = importer.extract(sample_pdf_file, existing_entries=None)
        assert len(entries) > 0

    def test_name(self, importer: Importer) -> None:
        """Test importer name."""
        assert "Assets:CertoOne:Main" in importer.name()

    def test_account(self, importer: Importer) -> None:
        """Test account method."""
        assert importer.account("any_file.pdf") == "Assets:CertoOne:Main"

    def test_extract_basic_transaction(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction of a basic transaction."""
        entries = importer.extract(sample_pdf_file, [])

        assert len(entries) == 21  # 1 Balance + 20 transactions

        # Test first transaction (credit)
        first_transaction = entries[1]  # Skip balance entry
        assert isinstance(first_transaction, data.Transaction)
        assert first_transaction.date == date(2025, 10, 7)
        assert first_transaction.narration == "Ihre Zahlung"
        assert first_transaction.flag == "*"

        # Check posting
        assert len(first_transaction.postings) == 1
        posting = first_transaction.postings[0]
        assert posting.account == "Assets:CertoOne:Main"
        assert posting.units == amount.Amount(D("206.85"), "CHF")

    def test_extract_debit_transaction(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction of a debit transaction."""
        entries = importer.extract(sample_pdf_file, [])

        # Find a debit transaction (negative amount)
        debit_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration == "Interflexio AG Zürich CHE"
            ):
                debit_entry = entry
                break

        assert debit_entry is not None
        assert debit_entry.date == date(2025, 9, 24)
        assert debit_entry.narration == "Interflexio AG Zürich CHE"

        # Check posting for debit transaction
        assert len(debit_entry.postings) == 1
        posting = debit_entry.postings[0]
        assert posting.account == "Assets:CertoOne:Main"
        assert posting.units == amount.Amount(D("-121.58"), "CHF")

    def test_extract_balance_entry(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction of balance entry."""
        entries = importer.extract(sample_pdf_file, [])

        # Find the balance entry
        balance_entry = None
        for entry in entries:
            if isinstance(entry, data.Balance):
                balance_entry = entry
                break

        assert balance_entry is not None
        assert balance_entry.date == date(2025, 10, 24)
        assert balance_entry.account == "Assets:CertoOne:Main"
        assert balance_entry.amount == amount.Amount(D("-540.15"), "CHF")

    def test_extract_special_characters(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction with special characters."""
        entries = importer.extract(sample_pdf_file, [])

        # Find an entry with special characters
        special_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration is not None
                and "ETH-Hö" in entry.narration
            ):
                special_entry = entry
                break

        assert special_entry is not None
        assert special_entry.narration is not None
        assert "ETH-Hö" in special_entry.narration

    def test_extract_foreign_currency(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction of foreign currency transaction."""
        entries = importer.extract(sample_pdf_file, [])

        # Find the foreign currency entry (DNK)
        foreign_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration is not None
                and "DNK" in entry.narration
            ):
                foreign_entry = entry
                break

        assert foreign_entry is not None
        assert foreign_entry.date == date(2025, 10, 17)
        assert foreign_entry.narration is not None
        assert "DNK" in foreign_entry.narration

        # Check that amount is still in CHF
        posting = foreign_entry.postings[0]
        assert posting.units is not None
        assert posting.units.currency == "CHF"

    def test_extract_rounding_correction(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test extraction of rounding correction."""
        entries = importer.extract(sample_pdf_file, [])

        # Find the rounding correction entry
        rounding_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration is not None
                and "Rundungskorrektur" in entry.narration
            ):
                rounding_entry = entry
                break

        assert rounding_entry is not None
        assert rounding_entry.date == date(2025, 10, 23)
        assert rounding_entry.narration == "Rundungskorrektur"

        # Check posting for rounding correction
        posting = rounding_entry.postings[0]
        assert posting.units == amount.Amount(D("-0.02"), "CHF")

    def test_extract_metadata(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
    ) -> None:
        """Test that metadata is properly set."""
        entries = importer.extract(sample_pdf_file, [])

        for entry in entries:
            assert entry.meta["filename"] == sample_pdf_file
            assert entry.meta["lineno"] == 0  # All entries use lineno 0

    def test_extract_with_existing_entries(
        self, importer: Importer, sample_pdf_file: str, csv_cleanup: None
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

        entries = importer.extract(sample_pdf_file, existing_entries)

        # Should return only new entries, not existing ones
        assert len(entries) == 21
        assert all(
            not isinstance(entry, data.Transaction)
            or entry.narration != "Existing transaction"
            for entry in entries
        )


class TestCertoOnePDFParsing:
    """Test PDF parsing functionality."""

    def test_parse_pdf_to_csv(self) -> None:
        """Test PDF to CSV conversion."""
        pdf_file = "tests/certo_one/CertoOne_Sample.pdf"

        if not os.path.exists(pdf_file):
            pytest.skip(f"Sample PDF file not found: {pdf_file}")

        # Use temporary directory for CSV file
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_file = os.path.join(temp_dir, "CertoOne_Sample_Test.csv")

            # Parse PDF to CSV
            parse_pdf_to_csv(pdf_file, csv_file)

            # Check that CSV file was created
            assert os.path.exists(csv_file)

            # Read and validate CSV content
            with open(csv_file) as f:
                lines = f.readlines()

            # Should have header + balance + transactions
            assert len(lines) >= 3
            assert lines[0].strip() == "Date;Amount;Description"

            # Check balance line
            balance_line = lines[1].strip()
            assert "BALANCE" in balance_line
            assert "2025-10-24" in balance_line
            assert "540.15" in balance_line

            # Check transaction lines
            transaction_lines = lines[2:]
            assert len(transaction_lines) > 0

            # Validate format of transaction lines
            for line in transaction_lines:
                parts = line.strip().split(";")
                assert len(parts) == 3
                # Date should be in YYYY-MM-DD format
                assert len(parts[0]) == 10
                assert parts[0].count("-") == 2
                # Amount should be numeric
                try:
                    float(parts[1])
                except ValueError:
                    pytest.fail(f"Invalid amount: {parts[1]}")

    def test_parse_pdf_nonexistent_file(self) -> None:
        """Test PDF parsing with nonexistent file."""
        # Use temporary directory for CSV file
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_file = os.path.join(temp_dir, "Nonexistent_Test.csv")

            with pytest.raises(FileNotFoundError):
                parse_pdf_to_csv("nonexistent.pdf", csv_file)

    def test_parse_pdf_camelot_bbox_error(self) -> None:
        """Test PDF parsing with specific bbox unpacking TypeError."""
        # This test simulates the specific error:
        # "cannot unpack non-iterable NoneType object"
        # from camelot's bbox_from_textlines function

        # Create a PDF that might cause the bbox unpacking error
        # by mocking camelot to raise the specific TypeError
        import unittest.mock

        # Patch camelot.read_pdf in the certo_one module
        # to ensure we catch the right location
        with unittest.mock.patch(
            "beancount_importers.importers.certo_one.camelot.read_pdf"
        ) as mock_camelot:
            # Simulate the specific TypeError that occurs in bbox_from_textlines
            # All three attempts will fail, and the third should propagate the error
            mock_camelot.side_effect = TypeError(
                "cannot unpack non-iterable NoneType object"
            )

            # Use temporary directory for CSV file
            with tempfile.TemporaryDirectory() as temp_dir:
                csv_file = os.path.join(temp_dir, "BboxError_Test.csv")

                # This should raise the TypeError from camelot
                # The first two attempts catch the error, but the third propagates it
                with pytest.raises(
                    TypeError, match="cannot unpack non-iterable NoneType object"
                ):
                    parse_pdf_to_csv("tests/certo_one/CertoOne_Sample.pdf", csv_file)

    def test_parse_pdf_camelot_typeerror(self) -> None:
        """Test PDF parsing with TypeError from camelot (bbox unpacking issue)."""
        # Create a PDF that might cause the bbox unpacking error
        # This simulates a PDF with table structure that causes camelot to fail
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_pdf = os.path.join(temp_dir, "temp.pdf")

            with open(temp_pdf, "wb") as f:
                # Create a minimal PDF that might trigger the error
                f.write(b"%PDF-1.4\n")
                f.write(b"1 0 obj\n")
                f.write(b"<<\n")
                f.write(b"/Type /Catalog\n")
                f.write(b"/Pages 2 0 R\n")
                f.write(b">>\n")
                f.write(b"endobj\n")
                f.write(b"2 0 obj\n")
                f.write(b"<<\n")
                f.write(b"/Type /Pages\n")
                f.write(b"/Kids [3 0 R]\n")
                f.write(b"/Count 1\n")
                f.write(b">>\n")
                f.write(b"endobj\n")
                f.write(b"3 0 obj\n")
                f.write(b"<<\n")
                f.write(b"/Type /Page\n")
                f.write(b"/Parent 2 0 R\n")
                f.write(b"/MediaBox [0 0 612 792]\n")
                f.write(b">>\n")
                f.write(b"endobj\n")
                f.write(b"xref\n")
                f.write(b"0 4\n")
                f.write(b"0000000000 65535 f \n")
                f.write(b"0000000009 00000 n \n")
                f.write(b"0000000058 00000 n \n")
                f.write(b"0000000115 00000 n \n")
                f.write(b"trailer\n")
                f.write(b"<<\n")
                f.write(b"/Size 4\n")
                f.write(b"/Root 1 0 R\n")
                f.write(b">>\n")
                f.write(b"startxref\n")
                f.write(b"174\n")
                f.write(b"%%EOF\n")

            csv_file = os.path.join(temp_dir, "CamelotError_Test.csv")

            # This should now handle the error gracefully and succeed
            # The improved error handling catches TypeError and tries
            # alternative approaches
            parse_pdf_to_csv(temp_pdf, csv_file)

            # Verify that a CSV file was created (even if empty or minimal)
            assert os.path.exists(csv_file)

    def test_parse_pdf_invalid_file(self) -> None:
        """Test PDF parsing with invalid file."""
        # Use temporary directory for files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_pdf = os.path.join(temp_dir, "invalid.pdf")
            csv_file = os.path.join(temp_dir, "Invalid_Test.csv")

            # Create a temporary invalid PDF file
            with open(temp_pdf, "wb") as f:
                f.write(b"Not a PDF file")

            with pytest.raises(
                (FileNotFoundError, ValueError, RuntimeError, Exception)
            ):
                parse_pdf_to_csv(temp_pdf, csv_file)


class TestCertoOneImporterIntegration:
    """Integration tests for the CertoOne importer with real PDF files."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create a test importer instance."""
        return Importer(r"CertoOne.*\.pdf$", "Assets:CertoOne:Main")

    def test_extract_from_real_pdf_file(self, importer: Importer) -> None:
        """Test extraction from a real PDF file in the test data."""
        pdf_file = "tests/certo_one/CertoOne_Sample.pdf"
        csv_file = Path(pdf_file).with_suffix(".csv")

        if not os.path.exists(pdf_file):
            pytest.skip(f"Test file {pdf_file} not found")

        # Clean up any existing CSV file first
        if csv_file.exists():
            csv_file.unlink()

        try:
            entries = importer.extract(pdf_file, [])

            # Should extract all transactions from the file
            assert len(entries) > 0

            # Should have one balance entry
            balance_entries = [e for e in entries if isinstance(e, data.Balance)]
            assert len(balance_entries) == 1

            # All other entries should be transactions
            transaction_entries = [
                e for e in entries if isinstance(e, data.Transaction)
            ]
            assert len(transaction_entries) == 20

            # All entries should have the correct account
            for entry in entries:
                if isinstance(entry, data.Balance):
                    assert entry.account == "Assets:CertoOne:Main"
                elif isinstance(entry, data.Transaction):
                    assert any(
                        posting.account == "Assets:CertoOne:Main"
                        for posting in entry.postings
                    )
        finally:
            # Clean up the CSV file after test
            if csv_file.exists():
                csv_file.unlink()

    def test_csv_file_reuse(self, importer: Importer) -> None:
        """Test that CSV file is reused if it already exists."""
        pdf_file = "tests/certo_one/CertoOne_Sample.pdf"

        if not os.path.exists(pdf_file):
            pytest.skip(f"Test file {pdf_file} not found")

        # The importer creates CSV file next to the PDF file
        csv_file = Path(pdf_file).with_suffix(".csv")

        # Clean up any existing CSV file first
        if csv_file.exists():
            csv_file.unlink()

        try:
            # First extraction
            entries1 = importer.extract(pdf_file, [])
            assert len(entries1) > 0

            # Check that CSV file was created
            assert csv_file.exists()

            # Get modification time
            mtime1 = csv_file.stat().st_mtime

            # Second extraction should reuse CSV file
            entries2 = importer.extract(pdf_file, [])
            assert len(entries2) == len(entries1)

            # CSV file should not have been modified
            mtime2 = csv_file.stat().st_mtime
            assert mtime1 == mtime2
        finally:
            # Clean up the CSV file after test
            if csv_file.exists():
                csv_file.unlink()

    def test_compare_with_expected_structure(self, importer: Importer) -> None:
        """Test that extracted entries match expected structure."""
        pdf_file = "tests/certo_one/CertoOne_Sample.pdf"
        csv_file = Path(pdf_file).with_suffix(".csv")

        if not os.path.exists(pdf_file):
            pytest.skip("Test file not found")

        # Clean up any existing CSV file first
        if csv_file.exists():
            csv_file.unlink()

        try:
            # Extract entries from PDF
            entries = importer.extract(pdf_file, [])
            assert len(entries) > 0

            # Basic validation that entries have expected structure
            for entry in entries:
                assert hasattr(entry, "date")
                assert hasattr(entry, "meta")
                assert entry.meta["filename"] == pdf_file

                if isinstance(entry, data.Balance):
                    assert hasattr(entry, "account")
                    assert hasattr(entry, "amount")
                elif isinstance(entry, data.Transaction):
                    assert hasattr(entry, "postings")
                    assert len(entry.postings) >= 1
        finally:
            # Clean up the CSV file after test
            if csv_file.exists():
                csv_file.unlink()


class TestCertoOneImporterEdgeCases:
    """Test edge cases and error handling for the CertoOne importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create a test importer instance."""
        return Importer(r"CertoOne.*\.pdf$", "Assets:CertoOne:Main")

    def test_extract_nonexistent_file(self, importer: Importer) -> None:
        """Test extraction from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            importer.extract("nonexistent.pdf", [])

    def test_extract_invalid_pdf_file(self, importer: Importer) -> None:
        """Test extraction from invalid PDF file."""
        # Use temporary directory for invalid PDF file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_pdf = os.path.join(temp_dir, "invalid.pdf")

            # Create a temporary invalid PDF file
            with open(temp_pdf, "wb") as f:
                f.write(b"Not a PDF file")

            with pytest.raises(
                (FileNotFoundError, ValueError, RuntimeError, Exception)
            ):
                importer.extract(temp_pdf, [])

    def test_extract_with_different_file_patterns(self, importer: Importer) -> None:
        """Test extraction with different file patterns."""
        pdf_file = "tests/certo_one/CertoOne_Sample.pdf"
        csv_file = Path(pdf_file).with_suffix(".csv")

        if not os.path.exists(pdf_file):
            pytest.skip(f"Test file {pdf_file} not found")

        # Clean up any existing CSV file first
        if csv_file.exists():
            csv_file.unlink()

        try:
            # Test with different importer patterns
            patterns = [
                r"CertoOne.*\.pdf$",
                r".*CertoOne.*\.pdf$",
                r"CertoOne.*",
            ]

            for pattern in patterns:
                test_importer = Importer(pattern, "Assets:CertoOne:Main")
                entries = test_importer.extract(pdf_file, [])
                assert len(entries) > 0
        finally:
            # Clean up the CSV file after test
            if csv_file.exists():
                csv_file.unlink()

    def test_extract_with_different_accounts(self, importer: Importer) -> None:
        """Test extraction with different account names."""
        pdf_file = "tests/certo_one/CertoOne_Sample.pdf"
        csv_file = Path(pdf_file).with_suffix(".csv")

        if not os.path.exists(pdf_file):
            pytest.skip(f"Test file {pdf_file} not found")

        # Clean up any existing CSV file first
        if csv_file.exists():
            csv_file.unlink()

        try:
            # Test with different account names
            accounts = [
                "Assets:CertoOne:Main",
                "Assets:CertoOne:Checking",
                "Assets:CertoOne",
            ]

            for account in accounts:
                test_importer = Importer(r"CertoOne.*\.pdf$", account)
                entries = test_importer.extract(pdf_file, [])

                # Check that all entries use the correct account
                for entry in entries:
                    if isinstance(entry, data.Balance):
                        assert entry.account == account
                    elif isinstance(entry, data.Transaction):
                        assert all(
                            posting.account == account for posting in entry.postings
                        )
        finally:
            # Clean up the CSV file after test
            if csv_file.exists():
                csv_file.unlink()
