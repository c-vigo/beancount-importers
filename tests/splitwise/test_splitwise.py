"""Tests for the Splitwise importers."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import data
from beancount.core.number import D

from beancount_importers.importers.splitwise import (
    HouseHoldSplitWiseImporter,
    TripSplitWiseImporter,
)


class TestHouseHoldSplitWiseImporter:
    """Tests for the HouseHold SplitWise importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> HouseHoldSplitWiseImporter:
        """Create an importer instance."""
        return HouseHoldSplitWiseImporter(
            r"Splitwise.*HouseHold.*\.csv$",
            "Assets:Splitwise:Household",
            "Person A",
            "Person B",
            account_map={"Groceries": "Expenses:Groceries"},
            tag="splitwise",
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/splitwise/Splitwise_HouseHold_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(
        self, importer: HouseHoldSplitWiseImporter
    ) -> None:
        """Test that the importer initializes correctly."""
        assert importer._filepattern == r"Splitwise.*HouseHold.*\.csv$"
        assert importer._account == "Assets:Splitwise:Household"
        assert importer.owner == "Person A"
        assert importer.partner == "Person B"
        assert importer.account_map == {"Groceries": "Expenses:Groceries"}
        assert importer.tag == {"splitwise"}

    def test_identify_file_pattern(self, importer: HouseHoldSplitWiseImporter) -> None:
        """Test that the importer identifies files correctly."""
        assert importer.identify("Splitwise_HouseHold_Sample.csv") is True
        assert importer.identify("2024-Splitwise_HouseHold.csv") is True
        assert importer.identify("splitwise_trip.csv") is False
        assert importer.identify("other_file.txt") is False

    def test_name(self, importer: HouseHoldSplitWiseImporter) -> None:
        """Test that the importer name is correct."""
        name = importer.name()
        assert "splitwise" in name.lower()
        assert "household" in name.lower()
        assert "Assets:Splitwise:Household" in name

    def test_account(self, importer: HouseHoldSplitWiseImporter) -> None:
        """Test that the account method returns the correct account."""
        assert importer.account() == "Assets:Splitwise:Household"

    def test_extract_transactions(
        self, importer: HouseHoldSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test extracting transactions from the sample file."""
        entries = importer.extract(sample_csv_file)

        # Should have extracted transactions
        assert len(entries) > 0

        # Check that all entries are transactions or balances
        for entry in entries:
            assert isinstance(entry, data.Transaction | data.Balance)

        # Find a specific transaction
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 1, 5)
                and e.narration == "Supermarket"
            ),
            None,
        )
        assert transaction is not None
        # Person A has negative value (-49.15), so Person B paid
        assert transaction.payee == "Person B"
        assert transaction.tags == {"splitwise"}

    def test_extract_balance(
        self, importer: HouseHoldSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test extracting balance entries."""
        entries = importer.extract(sample_csv_file)

        # Find balance entry
        balance = next(
            (
                e
                for e in entries
                if isinstance(e, data.Balance) and e.date == date(2024, 1, 25)
            ),
            None,
        )
        assert balance is not None
        assert balance.account == "Assets:Splitwise:Household"
        assert balance.amount.number == D("-150.00")
        assert balance.amount.currency == "CHF"

    def test_extract_account_mapping(
        self, importer: HouseHoldSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test that account mapping works correctly."""
        entries = importer.extract(sample_csv_file)

        # Find a transaction with mapped account
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.date == date(2024, 1, 5)
            ),
            None,
        )
        assert transaction is not None
        # Should have two postings
        assert len(transaction.postings) == 2
        # Expense account should be mapped
        expense_posting = next(
            (p for p in transaction.postings if "Expenses" in p.account), None
        )
        assert expense_posting is not None
        assert expense_posting.account == "Expenses:Groceries"

    def test_extract_owner_paid(
        self, importer: HouseHoldSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test transaction where owner paid (positive value)."""
        entries = importer.extract(sample_csv_file)

        # Find transaction where owner paid (Person A has positive value on 2024-01-11)
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 1, 11)
                and e.payee == "Person A"
            ),
            None,
        )
        assert transaction is not None
        # Owner's account should have positive value
        owner_posting = next(
            (p for p in transaction.postings if p.account == importer._account), None
        )
        assert owner_posting is not None
        assert owner_posting.units.number > 0

    def test_extract_partner_paid(
        self, importer: HouseHoldSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test transaction where partner paid (negative value)."""
        entries = importer.extract(sample_csv_file)

        # Find transaction where partner paid
        # (Person A has negative value on 2024-01-05)
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 1, 5)
                and e.payee == "Person B"
            ),
            None,
        )
        assert transaction is not None
        # Owner's account should have negative value
        owner_posting = next(
            (p for p in transaction.postings if p.account == importer._account), None
        )
        assert owner_posting is not None
        assert owner_posting.units.number < 0

    def test_extract_with_existing_entries(
        self, importer: HouseHoldSplitWiseImporter, sample_csv_file: str
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
        assert len(entries) > 0

    def test_extract_nonexistent_file(
        self, importer: HouseHoldSplitWiseImporter
    ) -> None:
        """Test that extract handles nonexistent files gracefully."""
        with pytest.raises(FileNotFoundError):
            importer.extract("nonexistent_file.csv")

    def test_extract_empty_csv_file(self, importer: HouseHoldSplitWiseImporter) -> None:
        """Test that extract handles empty CSV files."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("Date,Description,Category,Cost,Currency,Person A,Person B\n")
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            assert entries == []
        finally:
            os.unlink(temp_path)

    def test_extract_wrong_number_of_people(
        self, importer: HouseHoldSplitWiseImporter
    ) -> None:
        """Test that extract handles wrong number of people."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Date,Description,Category,Cost,Currency,Person A,Person B,Person C\n"
            )
            temp_path = f.name

        try:
            with pytest.warns(UserWarning):
                entries = importer.extract(temp_path)
                assert entries == []
        finally:
            os.unlink(temp_path)


class TestTripSplitWiseImporter:
    """Tests for the Trip SplitWise importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> TripSplitWiseImporter:
        """Create an importer instance."""
        return TripSplitWiseImporter(
            r"Splitwise.*Trip.*\.csv$",
            "Assets:Splitwise:Trip",
            "Person A",
            expenses_account="Expenses:Travel",
            tag="splitwise-trip",
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/splitwise/Splitwise_Trip_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: TripSplitWiseImporter) -> None:
        """Test that the importer initializes correctly."""
        assert importer._filepattern == r"Splitwise.*Trip.*\.csv$"
        assert importer._account == "Assets:Splitwise:Trip"
        assert importer.owner == "Person A"
        assert importer.expenses_account == "Expenses:Travel"
        assert importer.tag == {"splitwise-trip"}

    def test_identify_file_pattern(self, importer: TripSplitWiseImporter) -> None:
        """Test that the importer identifies files correctly."""
        assert importer.identify("Splitwise_Trip_Sample.csv") is True
        assert importer.identify("2024-Splitwise_Trip.csv") is True
        assert importer.identify("splitwise_household.csv") is False
        assert importer.identify("other_file.txt") is False

    def test_name(self, importer: TripSplitWiseImporter) -> None:
        """Test that the importer name is correct."""
        name = importer.name()
        assert "splitwise" in name.lower()
        assert "trip" in name.lower()
        assert "Assets:Splitwise:Trip" in name

    def test_account(self, importer: TripSplitWiseImporter) -> None:
        """Test that the account method returns the correct account."""
        assert importer.account() == "Assets:Splitwise:Trip"

    def test_extract_transactions(
        self, importer: TripSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test extracting transactions from the sample file."""
        entries = importer.extract(sample_csv_file)

        # Should have extracted transactions
        assert len(entries) > 0

        # Check that all entries are transactions or balances
        for entry in entries:
            assert isinstance(entry, data.Transaction | data.Balance)

        # Find a specific transaction
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction)
                and e.date == date(2024, 1, 26)
                and e.narration == "Hotel"
            ),
            None,
        )
        assert transaction is not None
        assert transaction.tags == {"splitwise-trip"}

    def test_extract_balance(
        self, importer: TripSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test extracting balance entries."""
        entries = importer.extract(sample_csv_file)

        # Find balance entry
        balance = next(
            (
                e
                for e in entries
                if isinstance(e, data.Balance) and e.date == date(2024, 12, 8)
            ),
            None,
        )
        assert balance is not None
        assert balance.account == "Assets:Splitwise:Trip"

    def test_extract_negative_balance(
        self, importer: TripSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test transaction with negative balance for owner."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with negative balance
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.date == date(2024, 1, 26)
            ),
            None,
        )
        assert transaction is not None
        # Should have expenses account posting
        expense_posting = next(
            (p for p in transaction.postings if "Expenses" in p.account), None
        )
        assert expense_posting is not None
        assert expense_posting.account == "Expenses:Travel"

    def test_extract_positive_balance(
        self, importer: TripSplitWiseImporter, sample_csv_file: str
    ) -> None:
        """Test transaction with positive balance for owner."""
        entries = importer.extract(sample_csv_file)

        # Find transaction with positive balance (payment received)
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.date == date(2024, 12, 7)
            ),
            None,
        )
        assert transaction is not None
        # Owner's account should have positive value
        owner_posting = next(
            (p for p in transaction.postings if p.account == importer._account), None
        )
        assert owner_posting is not None
        assert owner_posting.units.number > 0

    def test_extract_without_expenses_account(self, sample_csv_file: str) -> None:
        """Test importer without expenses account."""
        importer = TripSplitWiseImporter(
            r"Splitwise.*Trip.*\.csv$",
            "Assets:Splitwise:Trip",
            "Person A",
            expenses_account=None,
        )
        entries = importer.extract(sample_csv_file)

        # Should still extract transactions
        assert len(entries) > 0

        # Transactions should only have one posting (no expenses account)
        transaction = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and e.date == date(2024, 1, 26)
            ),
            None,
        )
        assert transaction is not None
        # Should only have account posting, no expenses posting
        assert len(transaction.postings) == 1

    def test_extract_with_existing_entries(
        self, importer: TripSplitWiseImporter, sample_csv_file: str
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
        assert len(entries) > 0

    def test_extract_nonexistent_file(self, importer: TripSplitWiseImporter) -> None:
        """Test that extract handles nonexistent files gracefully."""
        with pytest.raises(FileNotFoundError):
            importer.extract("nonexistent_file.csv")

    def test_extract_empty_csv_file(self, importer: TripSplitWiseImporter) -> None:
        """Test that extract handles empty CSV files."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Date,Description,Category,Cost,Currency,Person A,Person B,Person C\n"
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            assert entries == []
        finally:
            os.unlink(temp_path)

    def test_extract_wrong_number_of_people(
        self, importer: TripSplitWiseImporter
    ) -> None:
        """Test that extract handles wrong number of people."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write("Date,Description,Category,Cost,Currency,Person A\n")
            temp_path = f.name

        try:
            with pytest.warns(UserWarning):
                entries = importer.extract(temp_path)
                assert entries == []
        finally:
            os.unlink(temp_path)
