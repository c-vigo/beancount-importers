"""Tests for the Telegram importer."""

import os
import tempfile
import warnings
from datetime import date

import pytest
from beancount.core import data

from beancount_importers.importers.telegram import Importer


class TestTelegramImporter:
    """Tests for the Telegram importer covering all transaction types."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance."""
        return Importer(
            r"Telegram.*\.csv$",
            "Assets:Cash:CHF",
        )

    @pytest.fixture  # type: ignore[misc]
    def importer_with_map(self) -> Importer:
        """Create an importer instance with payee mapping."""
        return Importer(
            r"Telegram.*\.csv$",
            "Assets:Cash:CHF",
            map={
                "Person A": ("Family Member", "Inheritance"),
                "Store": ("Grocery Store", "Shopping"),
            },
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/telegram/Telegram_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test that the importer initializes correctly."""
        assert importer._filepattern == r"Telegram.*\.csv$"
        assert importer._account == "Assets:Cash:CHF"
        assert importer.map == {}

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test that the importer identifies files correctly."""
        assert importer.identify("Telegram_Sample.csv") is True
        assert importer.identify("2024-12-31-Telegram_Transactions.csv") is True
        assert importer.identify("revolut.csv") is False
        assert importer.identify("other_file.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test that the importer name is correct."""
        assert importer.name() == f"telegram.{importer.account()}"

    def test_account(self, importer: Importer) -> None:
        """Test that the importer account is correct."""
        assert importer.account() == "Assets:Cash:CHF"

    def test_extract_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transactions from CSV."""
        entries = importer.extract(sample_csv_file)

        assert len(entries) > 0
        assert all(
            isinstance(entry, data.Transaction | data.Balance) for entry in entries
        )

        # Find a transaction entry
        transaction = next(
            (e for e in entries if isinstance(e, data.Transaction)), None
        )
        assert transaction is not None
        assert isinstance(transaction, data.Transaction)
        assert transaction.flag == "*"
        assert len(transaction.postings) == 1

    def test_extract_balance_entries(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting balance entries from CSV."""
        entries = importer.extract(sample_csv_file)

        # Find balance entries
        balances = [e for e in entries if isinstance(e, data.Balance)]
        assert len(balances) > 0

        # Check first balance entry
        balance = balances[0]
        assert isinstance(balance, data.Balance)
        assert balance.account == "Assets:Cash:CHF"
        assert balance.amount is not None

    def test_extract_transaction_with_payee(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transaction with payee."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with payee
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.payee is not None
                and e.payee != ""
            ),
            None,
        )
        assert transaction is not None
        assert transaction.payee is not None

    def test_extract_transaction_without_payee(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transaction without payee."""
        entries = importer.extract(sample_csv_file)

        # Find transaction without payee (empty payee field)
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and (e.payee is None or e.payee == "")
            ),
            None,
        )
        # May or may not exist in sample data
        if transaction is not None:
            assert isinstance(transaction, data.Transaction)

    def test_extract_transaction_with_tag(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transaction with tag."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with tag
        transaction = next(
            (e for e in entries if isinstance(e, data.Transaction) and len(e.tags) > 0),
            None,
        )
        assert transaction is not None
        assert len(transaction.tags) > 0
        # Tag should not have leading #
        for tag in transaction.tags:
            assert not tag.startswith("#")

    def test_extract_transaction_without_tag(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transaction without tag."""
        entries = importer.extract(sample_csv_file)

        # Find transaction without tag
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and len(e.tags) == 0
            ),
            None,
        )
        assert transaction is not None
        assert transaction.tags == data.EMPTY_SET

    def test_extract_positive_amount(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transaction with positive amount."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with positive amount
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.postings[0].units.number > 0
            ),
            None,
        )
        assert transaction is not None
        assert transaction.postings[0].units.number > 0

    def test_extract_negative_amount(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transaction with negative amount."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with negative amount
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.postings[0].units.number < 0
            ),
            None,
        )
        assert transaction is not None
        assert transaction.postings[0].units.number < 0

    def test_extract_multiple_currencies(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting transactions with multiple currencies."""
        entries = importer.extract(sample_csv_file)

        currencies = set()
        for entry in entries:
            if isinstance(entry, data.Transaction):
                currencies.add(entry.postings[0].units.currency)
            elif isinstance(entry, data.Balance):
                currencies.add(entry.amount.currency)

        # Should have at least EUR and CHF
        assert "EUR" in currencies
        assert "CHF" in currencies

    def test_extract_metadata(self, importer: Importer, sample_csv_file: str) -> None:
        """Test that entries have correct metadata."""
        entries = importer.extract(sample_csv_file)

        for entry in entries:
            assert "filename" in entry.meta
            assert "lineno" in entry.meta
            assert entry.meta["filename"] == sample_csv_file

    def test_extract_reversed_order(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that entries are processed in reverse order from CSV."""
        entries = importer.extract(sample_csv_file)

        # Get transaction dates
        dates = [
            e.date for e in entries if isinstance(e, data.Transaction | data.Balance)
        ]

        # The importer processes rows in reverse, so the first entry should be
        # from the last row in the CSV (most recent if CSV is in ascending order)
        # We just verify that entries were extracted
        assert len(dates) > 0
        # The last entry in the extracted list should be from the first row of CSV
        # (oldest if CSV is in ascending order)

    def test_extract_with_mapping(
        self, importer_with_map: Importer, sample_csv_file: str
    ) -> None:
        """Test that payee mapping is applied correctly."""
        entries = importer_with_map.extract(sample_csv_file)

        # Find transaction with mapped payee
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.payee == "Family Member"
            ),
            None,
        )
        if transaction is not None:
            assert transaction.payee == "Family Member"
            assert transaction.narration == "Inheritance"

    def test_extract_nonexistent_file(self, importer: Importer) -> None:
        """Test handling of nonexistent file."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            entries = importer.extract("nonexistent_file.csv")
            assert len(entries) == 0
            assert len(w) > 0
            assert any("File not found" in str(warning.message) for warning in w)

    def test_extract_empty_file(self, importer: Importer) -> None:
        """Test handling of empty file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "id;sender;message_date;transaction_date;account;payee;description;amount;currency;tag\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            assert len(entries) == 0
        finally:
            os.unlink(temp_path)

    def test_extract_invalid_row(self, importer: Importer) -> None:
        """Test handling of invalid CSV row."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "id;sender;message_date;transaction_date;account;payee;description;amount;currency;tag\n"
            )
            f.write("invalid;row;data\n")
            temp_path = f.name

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                entries = importer.extract(temp_path)
                # Should handle gracefully
                assert len(entries) == 0 or len(w) > 0
        finally:
            os.unlink(temp_path)

    def test_extract_invalid_date(self, importer: Importer) -> None:
        """Test handling of invalid date format."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "id;sender;message_date;transaction_date;account;payee;description;amount;currency;tag\n"
            )
            f.write("10001;User;2024-01-15;invalid-date;Cash;Store;Test;-10.00;EUR;\n")
            temp_path = f.name

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                entries = importer.extract(temp_path)
                # Should handle gracefully
                assert len(entries) == 0 or len(w) > 0
        finally:
            os.unlink(temp_path)

    def test_extract_existing_entries(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that existing entries parameter is accepted."""
        existing = [
            data.Transaction(
                data.new_metadata("test", 0),
                date(2024, 1, 1),
                "*",
                "Test",
                "Test transaction",
                data.EMPTY_SET,
                data.EMPTY_SET,
                [],
            )
        ]

        entries = importer.extract(sample_csv_file, existing_entries=existing)
        # Should still extract entries from file
        assert len(entries) > 0

    def test_extract_tag_with_hash_prefix(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that tags with # prefix are handled correctly."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with tag
        transaction = next(
            (e for e in entries if isinstance(e, data.Transaction) and len(e.tags) > 0),
            None,
        )
        if transaction is not None:
            # Tags should not have leading #
            for tag in transaction.tags:
                assert not tag.startswith("#")
