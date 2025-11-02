"""Tests for the Revolut importer."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import amount, data
from beancount.core.number import D

from beancount_importers.importers.revolut import Importer


class TestRevolutImporter:
    """Tests for the Revolut importer covering all transaction types."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance."""
        return Importer(
            r"Revolut.*\.csv$",
            "Assets:Revolut:CHF",
            "Expenses:Revolut:Fees",
            "CHF",
        )

    @pytest.fixture  # type: ignore[misc]
    def chf_csv_file(self) -> str:
        """Get the path to the CHF sample CSV file."""
        csv_path = "tests/revolut/Revolut_CHF_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CHF CSV file not found: {csv_path}")
        return csv_path

    @pytest.fixture  # type: ignore[misc]
    def eur_importer(self) -> Importer:
        """Create an EUR importer instance."""
        return Importer(
            r"Revolut.*\.csv$",
            "Assets:Revolut:EUR",
            "Expenses:Revolut:Fees",
            "EUR",
        )

    @pytest.fixture  # type: ignore[misc]
    def eur_csv_file(self) -> str:
        """Get the path to the EUR sample CSV file."""
        csv_path = "tests/revolut/Revolut_EUR_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"EUR CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test importer initialization."""
        assert importer._filepattern == r"Revolut.*\.csv$"
        assert importer._account == "Assets:Revolut:CHF"
        assert importer._fee_account == "Expenses:Revolut:Fees"
        assert importer._currency == "CHF"

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test file identification."""
        assert importer.identify("Revolut_CHF_Transactions.csv") is True
        assert importer.identify("2024-12-31-Revolut_CHF_Transactions.csv") is True
        assert importer.identify("revolut_transactions.csv") is False
        assert importer.identify("other_bank.csv") is False
        assert importer.identify("Revolut.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test importer name."""
        assert "Assets:Revolut:CHF" in importer.name()

    def test_account(self, importer: Importer) -> None:
        """Test account method."""
        assert importer.account("any_file.csv") == "Assets:Revolut:CHF"

    def test_extract_all_transaction_types_chf(
        self, importer: Importer, chf_csv_file: str
    ) -> None:
        """Test that all transaction types are extracted correctly from CHF file."""
        entries = importer.extract(chf_csv_file, [])

        # Should extract 7 transactions (all types)
        assert len(entries) == 7

        # Verify we have all transaction types
        narrations = {
            entry.narration for entry in entries if isinstance(entry, data.Transaction)
        }

        assert any("TOPUP" in n for n in narrations)
        assert any("CARD_PAYMENT" in n for n in narrations)
        assert any("EXCHANGE" in n for n in narrations)
        assert any("ATM" in n for n in narrations)
        assert any("TRANSFER" in n for n in narrations)

    def test_extract_all_transaction_types_eur(
        self, eur_importer: Importer, eur_csv_file: str
    ) -> None:
        """Test that all transaction types are extracted correctly from EUR file."""
        entries = eur_importer.extract(eur_csv_file, [])

        # Should extract 7 transactions (all types)
        assert len(entries) == 7

        # Verify we have all transaction types
        narrations = {
            entry.narration for entry in entries if isinstance(entry, data.Transaction)
        }

        assert any("TOPUP" in n for n in narrations)
        assert any("CARD_PAYMENT" in n for n in narrations)
        assert any("EXCHANGE" in n for n in narrations)
        assert any("ATM" in n for n in narrations)
        assert any("TRANSFER" in n for n in narrations)

    def test_extract_eur_currency(
        self, eur_importer: Importer, eur_csv_file: str
    ) -> None:
        """Test that EUR currency is correctly extracted."""
        entries = eur_importer.extract(eur_csv_file, [])

        # Check that all entries use EUR currency
        for entry in entries:
            if isinstance(entry, data.Transaction):
                for posting in entry.postings:
                    assert posting.units.currency == "EUR"

    def test_extract_topup(self, importer: Importer, chf_csv_file: str) -> None:
        """Test TOPUP transaction."""
        entries = importer.extract(chf_csv_file, [])

        topup_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and "TOPUP" in entry.narration:
                topup_entry = entry
                break

        assert topup_entry is not None
        assert topup_entry.date == date(2024, 1, 1)
        assert topup_entry.payee == ""
        assert topup_entry.flag == "*"
        assert len(topup_entry.postings) == 1
        assert topup_entry.postings[0].account == "Assets:Revolut:CHF"
        assert topup_entry.postings[0].units == amount.Amount(D("500.00"), "CHF")

    def test_extract_card_payment(self, importer: Importer, chf_csv_file: str) -> None:
        """Test CARD_PAYMENT transaction."""
        entries = importer.extract(chf_csv_file, [])

        card_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and "CARD_PAYMENT" in entry.narration
                and "Test Merchant" in entry.narration
            ):
                card_entry = entry
                break

        assert card_entry is not None
        assert card_entry.date == date(2024, 1, 15)
        assert len(card_entry.postings) == 1
        assert card_entry.postings[0].account == "Assets:Revolut:CHF"
        assert card_entry.postings[0].units == amount.Amount(D("-25.50"), "CHF")

    def test_extract_card_payment_with_fee(
        self, importer: Importer, chf_csv_file: str
    ) -> None:
        """Test CARD_PAYMENT transaction with fee."""
        entries = importer.extract(chf_csv_file, [])

        card_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and "CARD_PAYMENT" in entry.narration
                and "Online Store" in entry.narration
            ):
                card_entry = entry
                break

        assert card_entry is not None
        assert card_entry.date == date(2024, 3, 1)
        # Amount should be Amount - Fee = -42.18 - 0.42 = -42.60
        assert card_entry.postings[0].units == amount.Amount(D("-42.60"), "CHF")

    def test_extract_exchange(self, importer: Importer, chf_csv_file: str) -> None:
        """Test EXCHANGE transaction."""
        entries = importer.extract(chf_csv_file, [])

        exchange_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and "EXCHANGE" in entry.narration:
                exchange_entry = entry
                break

        assert exchange_entry is not None
        assert exchange_entry.date == date(2024, 2, 1)
        assert exchange_entry.postings[0].units == amount.Amount(D("-100.00"), "CHF")

    def test_extract_atm(self, importer: Importer, chf_csv_file: str) -> None:
        """Test ATM transaction."""
        entries = importer.extract(chf_csv_file, [])

        atm_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and "ATM" in entry.narration:
                atm_entry = entry
                break

        assert atm_entry is not None
        assert atm_entry.date == date(2024, 2, 15)
        assert atm_entry.postings[0].units == amount.Amount(D("-50.00"), "CHF")

    def test_extract_transfer(self, importer: Importer, chf_csv_file: str) -> None:
        """Test TRANSFER transaction."""
        entries = importer.extract(chf_csv_file, [])

        transfer_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and "TRANSFER" in entry.narration:
                transfer_entry = entry
                break

        assert transfer_entry is not None
        assert transfer_entry.date == date(2024, 3, 15)
        assert transfer_entry.postings[0].units == amount.Amount(D("-75.00"), "CHF")

    def test_extract_metadata_chf(self, importer: Importer, chf_csv_file: str) -> None:
        """Test that metadata is properly set for CHF file."""
        entries = importer.extract(chf_csv_file, [])

        for entry in entries:
            assert entry.meta["filename"] == chf_csv_file
            assert "lineno" in entry.meta

    def test_extract_metadata_eur(
        self, eur_importer: Importer, eur_csv_file: str
    ) -> None:
        """Test that metadata is properly set for EUR file."""
        entries = eur_importer.extract(eur_csv_file, [])

        for entry in entries:
            assert entry.meta["filename"] == eur_csv_file
            assert "lineno" in entry.meta

    def test_extract_with_existing_entries(
        self, importer: Importer, chf_csv_file: str
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

        entries = importer.extract(chf_csv_file, existing_entries)

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
                "Type,Product,Started Date,Completed Date,Description,Amount,"
                "Fee,Currency,State,Balance\n"
            )
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should return empty list for file with only header
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_extract_skip_non_completed(self, importer: Importer) -> None:
        """Test that non-completed transactions are skipped."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Type,Product,Started Date,Completed Date,Description,Amount,"
                "Fee,Currency,State,Balance\n"
            )
            f.write(
                "CARD_PAYMENT,Current,2024-01-01 10:00:00,2024-01-01 10:00:01,"
                "Test Merchant,-25.50,0.00,CHF,PENDING,474.50\n"
            )
            f.write(
                "CARD_PAYMENT,Current,2024-01-02 10:00:00,2024-01-02 10:00:01,"
                "Test Merchant,-25.50,0.00,CHF,COMPLETED,449.00\n"
            )
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should only extract the COMPLETED transaction
            assert len(entries) == 1
            assert entries[0].narration == "CARD_PAYMENT Test Merchant"
            assert entries[0].date == date(2024, 1, 2)
        finally:
            os.unlink(temp_file)

    def test_extract_skip_zero_amount(self, importer: Importer) -> None:
        """Test that zero amount transactions are skipped."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Type,Product,Started Date,Completed Date,Description,Amount,"
                "Fee,Currency,State,Balance\n"
            )
            f.write(
                "CARD_PAYMENT,Current,2024-01-01 10:00:00,2024-01-01 10:00:01,"
                "Test Merchant,0.00,0.00,CHF,COMPLETED,500.00\n"
            )
            f.write(
                "CARD_PAYMENT,Current,2024-01-02 10:00:00,2024-01-02 10:00:01,"
                "Test Merchant,-25.50,0.00,CHF,COMPLETED,474.50\n"
            )
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should only extract the non-zero transaction
            assert len(entries) == 1
            assert entries[0].narration == "CARD_PAYMENT Test Merchant"
            assert entries[0].date == date(2024, 1, 2)
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_date(self, importer: Importer) -> None:
        """Test extraction with invalid date."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Type,Product,Started Date,Completed Date,Description,Amount,"
                "Fee,Currency,State,Balance\n"
            )
            f.write(
                "CARD_PAYMENT,Current,invalid-date,2024-01-01 10:00:01,"
                "Test Merchant,-25.50,0.00,CHF,COMPLETED,474.50\n"
            )
            temp_file = f.name

        try:
            # Should handle invalid date gracefully (logging warning)
            entries = importer.extract(temp_file, [])
            # Should return empty list or handle error
            assert isinstance(entries, list)
        finally:
            os.unlink(temp_file)
