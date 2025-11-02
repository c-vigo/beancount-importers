"""Tests for the FinPension importer."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import amount, data, position
from beancount.core.number import D

from beancount_importers.importers.finpension import Importer


def get_simplified_securities() -> dict[str, list[str]]:
    """Get simplified securities mapping: one CHF and one USD."""
    return {
        "CH0012345678": ["TestFundCHF", "CHF"],
        "CH0098765432": ["TestFundUSD", "USD"],
    }


class TestFinPensionImporter:
    """Simplified test covering all transaction types with minimal securities."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance with simplified securities."""
        return Importer(
            r"FinPension.*\.csv$",
            "Assets:FinPension:P5",
            "Income:FinPension",
            "Expenses:FinPension:Fees",
            get_simplified_securities(),
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the simplified sample CSV file."""
        csv_path = "tests/finpension/FinPension_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"Sample CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test importer initialization."""
        assert importer._filepattern == r"FinPension.*\.csv$"
        assert importer._parent_account == "Assets:FinPension:P5"
        assert importer._income_account == "Income:FinPension"
        assert importer._fees_account == "Expenses:FinPension:Fees"
        assert len(importer._securities) == 2

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test file identification."""
        assert importer.identify("FinPension_Transactions_P5.csv") is True
        assert importer.identify("2023-01-01-FinPension_Transactions_P5.csv") is True
        assert importer.identify("finpension_transactions.csv") is False
        assert importer.identify("other_bank.csv") is False
        assert importer.identify("FinPension.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test importer name."""
        assert "Assets:FinPension:P5" in importer.name()

    def test_account(self, importer: Importer) -> None:
        """Test account method."""
        assert importer.account("any_file.csv") == "Assets:FinPension:P5"

    def test_extract_all_transaction_types(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that all transaction types are extracted correctly."""
        entries = importer.extract(sample_csv_file, [])

        # Should extract 8 transactions (all types)
        assert len(entries) == 8

        # Verify we have all transaction types
        narrations = {
            entry.narration for entry in entries if isinstance(entry, data.Transaction)
        }

        assert "Deposit" in narrations
        assert any("Buy" in n for n in narrations)
        assert any("Sell" in n for n in narrations)
        assert any("Dividends" in n for n in narrations)
        assert "Flat-rate administrative fee" in narrations
        assert "Interests" in narrations
        assert "Transfer" in narrations

    def test_extract_deposit(self, importer: Importer, sample_csv_file: str) -> None:
        """Test deposit transaction."""
        entries = importer.extract(sample_csv_file, [])

        deposit_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry.narration == "Deposit":
                deposit_entry = entry
                break

        assert deposit_entry is not None
        assert deposit_entry.date == date(2023, 1, 1)
        assert deposit_entry.payee == "FinPension"
        assert deposit_entry.flag == "*"
        assert len(deposit_entry.postings) == 1
        assert deposit_entry.postings[0].account == "Assets:FinPension:P5:Cash"
        assert deposit_entry.postings[0].units == amount.Amount(D("1000.000000"), "CHF")

    def test_extract_buy_chf_security(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test buying a CHF security."""
        entries = importer.extract(sample_csv_file, [])

        buy_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and "Buy" in entry.narration
                and "TestFundCHF" in entry.narration
            ):
                buy_entry = entry
                break

        assert buy_entry is not None
        assert buy_entry.date == date(2023, 1, 15)
        assert len(buy_entry.postings) == 2

        cash_posting = buy_entry.postings[0]
        sec_posting = buy_entry.postings[1]

        assert cash_posting.account == "Assets:FinPension:P5:Cash"
        assert cash_posting.units == amount.Amount(D("-500.000000"), "CHF")
        assert sec_posting.account == "Assets:FinPension:P5:TestFundCHF"
        assert sec_posting.units == amount.Amount(D("5.000000"), "TestFundCHF")
        assert isinstance(sec_posting.cost, position.CostSpec)

    def test_extract_buy_usd_security(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test buying a USD security."""
        entries = importer.extract(sample_csv_file, [])

        buy_entry = None
        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and "Buy" in entry.narration
                and "TestFundUSD" in entry.narration
            ):
                buy_entry = entry
                break

        assert buy_entry is not None
        assert buy_entry.date == date(2023, 2, 1)
        assert len(buy_entry.postings) == 2

        sec_posting = buy_entry.postings[1]
        assert sec_posting.account == "Assets:FinPension:P5:TestFundUSD"
        assert sec_posting.units == amount.Amount(D("10.000000"), "TestFundUSD")

    def test_extract_sell_transaction(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test selling a security."""
        entries = importer.extract(sample_csv_file, [])

        sell_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and "Sell" in entry.narration:
                sell_entry = entry
                break

        assert sell_entry is not None
        assert sell_entry.date == date(2023, 4, 1)
        assert len(sell_entry.postings) == 2

        cash_posting = sell_entry.postings[0]
        sec_posting = sell_entry.postings[1]

        assert cash_posting.units == amount.Amount(D("220.000000"), "CHF")
        assert sec_posting.units == amount.Amount(D("-2.000000"), "TestFundCHF")

    def test_extract_dividend(self, importer: Importer, sample_csv_file: str) -> None:
        """Test dividend transaction."""
        entries = importer.extract(sample_csv_file, [])

        dividend_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and "Dividends" in entry.narration:
                dividend_entry = entry
                break

        assert dividend_entry is not None
        assert dividend_entry.date == date(2023, 3, 15)
        assert len(dividend_entry.postings) == 2

        cash_posting = dividend_entry.postings[0]
        income_posting = dividend_entry.postings[1]

        assert cash_posting.units == amount.Amount(D("10.000000"), "CHF")
        assert income_posting.account == "Income:FinPension:TestFundCHF:Dividends"

    def test_extract_fees_and_interests(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test administrative fee and interests transactions."""
        entries = importer.extract(sample_csv_file, [])

        fee_entry = None
        interests_entry = None

        for entry in entries:
            if (
                isinstance(entry, data.Transaction)
                and entry.narration == "Flat-rate administrative fee"
            ):
                fee_entry = entry
            if isinstance(entry, data.Transaction) and entry.narration == "Interests":
                interests_entry = entry

        assert fee_entry is not None
        assert fee_entry.date == date(2023, 5, 1)
        assert fee_entry.postings[1].account == "Expenses:FinPension:Fees"

        assert interests_entry is not None
        assert interests_entry.date == date(2023, 6, 1)
        assert interests_entry.postings[1].account == "Income:FinPension:Interests"

    def test_extract_transfer(self, importer: Importer, sample_csv_file: str) -> None:
        """Test transfer transaction."""
        entries = importer.extract(sample_csv_file, [])

        transfer_entry = None
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry.narration == "Transfer":
                transfer_entry = entry
                break

        assert transfer_entry is not None
        assert transfer_entry.date == date(2023, 7, 1)
        assert len(transfer_entry.postings) == 1

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
                'Date;Category;"Asset Name";ISIN;"Number of Shares";'
                '"Asset Currency";"Currency Rate";"Asset Price in CHF";'
                '"Cash Flow";Balance\n'
            )
            temp_file = f.name

        try:
            entries = importer.extract(temp_file, [])
            # Should return empty list for file with only header
            assert len(entries) == 0
        finally:
            os.unlink(temp_file)

    def test_extract_unknown_category(self, importer: Importer) -> None:
        """Test extraction with unknown category."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                'Date;Category;"Asset Name";ISIN;"Number of Shares";'
                '"Asset Currency";"Currency Rate";"Asset Price in CHF";'
                '"Cash Flow";Balance\n'
            )
            f.write(
                "2023-01-13;Unknown Category;;;;CHF;"
                "1.0000000000;;588.000000;588.000000\n"
            )
            temp_file = f.name

        try:
            with pytest.raises(Warning, match="Unknown category"):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)

    def test_extract_missing_isin_for_buy_sell(self, importer: Importer) -> None:
        """Test extraction with missing ISIN for buy/sell transaction."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                'Date;Category;"Asset Name";ISIN;"Number of Shares";'
                '"Asset Currency";"Currency Rate";"Asset Price in CHF";'
                '"Cash Flow";Balance\n'
            )
            f.write(
                '2023-01-17;Buy;"Test Fund";;;1.000000;CHF;1.0000000000;'
                "100.000000;-100.000000;0.000000\n"
            )
            temp_file = f.name

        try:
            # Should raise KeyError for missing ISIN in securities dict
            with pytest.raises(KeyError):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)

    def test_extract_invalid_date(self, importer: Importer) -> None:
        """Test extraction with invalid date."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                'Date;Category;"Asset Name";ISIN;"Number of Shares";'
                '"Asset Currency";"Currency Rate";"Asset Price in CHF";'
                '"Cash Flow";Balance\n'
            )
            f.write("invalid-date;Deposit;;;;CHF;1.0000000000;;588.000000;588.000000\n")
            temp_file = f.name

        try:
            # Should raise ValueError for invalid date
            with pytest.raises((ValueError, TypeError)):
                importer.extract(temp_file, [])
        finally:
            os.unlink(temp_file)
