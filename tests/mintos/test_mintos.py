"""Tests for the Mintos importer."""

import os
import tempfile
import warnings
from datetime import date

import pytest
from beancount.core import amount, data
from beancount.core.number import D

from beancount_importers.importers.mintos import Importer


class TestMintosImporter:
    """Tests for the Mintos importer covering all transaction types."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance."""
        return Importer(
            r"Mintos.*\.csv$",
            "Assets:Mintos:Cash",
            "Assets:Mintos:Loans",
            "Expenses:Mintos:Fees",
            "Income:Mintos:Interest",
            None,
        )

    @pytest.fixture  # type: ignore[misc]
    def importer_with_external(self) -> Importer:
        """Create an importer instance with external account."""
        return Importer(
            r"Mintos.*\.csv$",
            "Assets:Mintos:Cash",
            "Assets:Mintos:Loans",
            "Expenses:Mintos:Fees",
            "Income:Mintos:Interest",
            "Assets:Bank:Checking",
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the simplified sample CSV file."""
        csv_path = "tests/mintos/Mintos_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test importer initialization."""
        assert importer._filepattern == r"Mintos.*\.csv$"
        assert importer._cash_account == "Assets:Mintos:Cash"
        assert importer._loan_account == "Assets:Mintos:Loans"
        assert importer._fees_account == "Expenses:Mintos:Fees"
        assert importer._pnl_account == "Income:Mintos:Interest"
        assert importer._external_account is None

    def test_importer_with_external_account(
        self, importer_with_external: Importer
    ) -> None:
        """Test importer initialization with external account."""
        assert importer_with_external._external_account == "Assets:Bank:Checking"

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test file identification."""
        assert importer.identify("Mintos_Transactions.csv") is True
        assert importer.identify("2024-12-31-Mintos_Transactions.csv") is True
        assert importer.identify("mintos_transactions.csv") is False
        assert importer.identify("other_platform.csv") is False
        assert importer.identify("Mintos.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test importer name."""
        assert "Assets:Mintos:Cash" in importer.name()

    def test_account(self, importer: Importer) -> None:
        """Test account method."""
        assert importer.account("any_file.csv") == "Assets:Mintos:Cash"

    def test_extract_all_transaction_types(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that all transaction types are extracted correctly."""
        entries = importer.extract(sample_csv_file, [])

        # Should have entries (deposits create summary entries)
        assert len(entries) > 0

        # Verify we have different transaction types
        narrations = {
            entry.narration for entry in entries if isinstance(entry, data.Transaction)
        }

        assert "Deposit" in narrations
        assert "Withdrawal" in narrations
        assert "Summary" in narrations

    def test_extract_deposit(self, importer: Importer, sample_csv_file: str) -> None:
        """Test deposit transaction."""
        entries = importer.extract(sample_csv_file, [])

        deposit_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry.narration == "Deposit":
                deposit_entry = entry
                break

        assert deposit_entry is not None
        assert deposit_entry.date == date(2024, 1, 1)
        assert deposit_entry.payee == "Mintos"
        assert deposit_entry.flag == "*"
        assert len(deposit_entry.postings) == 1
        assert deposit_entry.postings[0].account == "Assets:Mintos:Cash"
        assert deposit_entry.postings[0].units == amount.Amount(D("500.00"), "EUR")

    def test_extract_deposit_with_external_account(
        self, importer_with_external: Importer, sample_csv_file: str
    ) -> None:
        """Test deposit transaction with external account."""
        entries = importer_with_external.extract(sample_csv_file, [])

        deposit_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry.narration == "Deposit":
                deposit_entry = entry
                break

        assert deposit_entry is not None
        assert len(deposit_entry.postings) == 2
        assert deposit_entry.postings[0].account == "Assets:Mintos:Cash"
        assert deposit_entry.postings[1].account == "Assets:Bank:Checking"
        assert deposit_entry.postings[1].units == amount.Amount(D("-500.00"), "EUR")

    def test_extract_withdrawal(self, importer: Importer, sample_csv_file: str) -> None:
        """Test withdrawal transaction."""
        entries = importer.extract(sample_csv_file, [])

        withdrawal_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry.narration == "Withdrawal":
                withdrawal_entry = entry
                break

        assert withdrawal_entry is not None
        assert withdrawal_entry.date == date(2024, 8, 1)
        assert withdrawal_entry.postings[0].account == "Assets:Mintos:Cash"
        assert withdrawal_entry.postings[0].units == amount.Amount(D("-200.00"), "EUR")

    def test_extract_summary_entries(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that summary entries are created correctly."""
        entries = importer.extract(sample_csv_file, [])

        summary_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction) and e.narration == "Summary"
        ]

        # Should have summary entries (before deposits/withdrawals)
        assert len(summary_entries) > 0

        # Check that summary entries have multiple postings
        for summary in summary_entries:
            assert len(summary.postings) > 0
            # Should have cash account posting
            assert any(p.account == "Assets:Mintos:Cash" for p in summary.postings)

    def test_extract_accumulates_interests_and_fees(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that interests, dividends, and fees are accumulated."""
        entries = importer.extract(sample_csv_file, [])

        # Find the first summary entry after the deposit
        deposit_found = False
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry.narration == "Deposit":
                deposit_found = True
                continue
            if deposit_found and isinstance(entry, data.Transaction):
                if entry.narration == "Summary":
                    # Should have accumulated some interest/dividend
                    # Check that summary entry has postings
                    assert len(entry.postings) > 0
                    break

    def test_extract_metadata(self, importer: Importer, sample_csv_file: str) -> None:
        """Test that metadata is properly set."""
        entries = importer.extract(sample_csv_file, [])

        for entry in entries:
            assert entry.meta["filename"] == sample_csv_file
            assert "lineno" in entry.meta

    def test_extract_with_existing_entries(
        self, importer: Importer, sample_csv_file: str
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
        assert len(entries) > 0
        assert all(
            not isinstance(entry, data.Transaction)
            or entry.narration != "Existing transaction"
            for entry in entries
        )

    def test_extract_nonexistent_file(self, importer: Importer) -> None:
        """Test extraction from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            importer.extract("nonexistent.csv", [])

    def test_extract_empty_csv_file(self, importer: Importer) -> None:
        """Test extraction from empty CSV file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "TransactionID,DateInput,Details,Turnover,Balance,Date,Value,Type,Note\n"
            )
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should return empty list for file with only header
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_description(self, importer: Importer) -> None:
        """Test extraction with invalid transaction description."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "TransactionID,DateInput,Details,Turnover,Balance,Date,Value,Type,Note\n"
            )
            f.write(
                "1,2024-01-01,invalid transaction type,100.00,100.00,"
                "2024-01-01,100.00,Unknown,Test\n"
            )
            temp_file = f.name

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                entries = importer.extract(temp_file, [])
                # Should log warning and skip invalid transaction
                assert len(w) > 0
                # Should return empty list (no valid transactions)
                assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_date(self, importer: Importer) -> None:
        """Test extraction with invalid date."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "TransactionID,DateInput,Details,Turnover,Balance,Date,Value,Type,Note\n"
            )
            f.write(
                "1,2024-01-01,deposits,100.00,100.00,invalid-date,100.00,Deposit,Test\n"
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

    def test_build_postings(self, importer: Importer) -> None:
        """Test build_postings method directly."""
        postings = importer.build_postings(D("5.00"), D("10.00"), D("-50.00"))

        assert len(postings) == 4

        # Check accounts
        accounts = {p.account for p in postings}
        assert "Assets:Mintos:Cash" in accounts
        assert "Assets:Mintos:Loans" in accounts
        assert "Expenses:Mintos:Fees" in accounts
        assert "Income:Mintos:Interest" in accounts

    def test_build_postings_zero_values(self, importer: Importer) -> None:
        """Test build_postings with zero values."""
        postings = importer.build_postings(D("0"), D("0"), D("0"))

        # Should return empty list when all values are zero
        assert len(postings) == 0
