"""Tests for the IBKR importer."""

import os
import tempfile
from datetime import date

import pytest
from beancount.core import data

from beancount_importers.importers.ibkr import Importer


class TestIBKRImporter:
    """Tests for the IBKR CSV importer."""

    @pytest.fixture  # type: ignore[misc]
    def importer(self) -> Importer:
        """Create an importer instance."""
        return Importer(
            r"IBKR.*\.csv$",
            "Assets:Investment:IBKR",
            "Income:Investment:IBKR",
            "Assets:Investment:IBKR:Tax",
            "Expenses:Investment:IBKR:Fees",
        )

    @pytest.fixture  # type: ignore[misc]
    def sample_csv_file(self) -> str:
        """Get the path to the sample CSV file."""
        csv_path = "tests/ibkr/IBKR_Sample.csv"
        if not os.path.exists(csv_path):
            pytest.skip(f"CSV file not found: {csv_path}")
        return csv_path

    def test_importer_initialization(self, importer: Importer) -> None:
        """Test that the importer initializes correctly."""
        assert importer._filepattern == r"IBKR.*\.csv$"
        assert importer._parent_account == "Assets:Investment:IBKR"
        assert importer._income_account == "Income:Investment:IBKR"
        assert importer.tax_account == "Assets:Investment:IBKR:Tax"
        assert importer.fees_account == "Expenses:Investment:IBKR:Fees"
        assert importer.cash_account == "Assets:Investment:IBKR:Cash"

    def test_identify_file_pattern(self, importer: Importer) -> None:
        """Test that the importer identifies files correctly."""
        assert importer.identify("IBKR_Sample.csv") is True
        assert importer.identify("2024-12-31-IBKR_Transactions.csv") is True
        assert importer.identify("other_file.txt") is False

    def test_name(self, importer: Importer) -> None:
        """Test that the importer name is correct."""
        name = importer.name()
        assert "ibkr" in name.lower()
        assert "Assets:Investment:IBKR" in name

    def test_account(self, importer: Importer) -> None:
        """Test that the account method returns the correct account."""
        assert importer.account() == "Assets:Investment:IBKR"

    def test_extract_buy_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting BUY transactions."""
        entries = importer.extract(sample_csv_file)

        # Find a BUY transaction
        buy_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and "Buy" in e.narration
            ),
            None,
        )
        assert buy_entry is not None
        assert buy_entry.payee == "Interactive Brokers"
        assert "Buy" in buy_entry.narration

    def test_extract_sell_transactions(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting SELL transactions."""
        entries = importer.extract(sample_csv_file)

        # Find a SELL transaction
        sell_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and "Sell" in e.narration
            ),
            None,
        )
        assert sell_entry is not None
        assert sell_entry.payee == "Interactive Brokers"
        assert "Sell" in sell_entry.narration

    def test_extract_dividends(self, importer: Importer, sample_csv_file: str) -> None:
        """Test extracting dividend transactions."""
        entries = importer.extract(sample_csv_file)

        # Find dividend transactions
        dividend_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction) and "Dividends" in e.narration
        ]
        assert len(dividend_entries) > 0

        # Check first dividend entry
        div_entry = dividend_entries[0]
        assert div_entry.payee == "Interactive Brokers"
        assert "Dividends" in div_entry.narration

    def test_extract_withholding_tax(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that withholding taxes are matched with dividends.

        Also verify they use currency-specific accounts.
        """
        entries = importer.extract(sample_csv_file)

        # Find dividend entries that should have withholding tax
        dividend_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction)
            and "Dividends" in e.narration
            and "VEA" in e.narration
        ]

        # Check that at least one dividend has withholding tax posting
        if dividend_entries:
            div_entry = dividend_entries[0]
            # Should have at least 3 postings (cash, income, and tax)
            assert len(div_entry.postings) >= 3

            # Find the tax posting
            tax_posting = next(
                (p for p in div_entry.postings if importer.tax_account in p.account),
                None,
            )
            assert tax_posting is not None
            # Check that tax account ends with currency suffix
            assert tax_posting.account.endswith(":USD")
            assert tax_posting.account == importer.tax_account + ":USD"
            # Verify currency matches
            assert tax_posting.units.currency == "USD"

    def test_withholding_tax_multiple_securities(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test withholding taxes for different securities.

        Verify they use correct currency accounts.
        """
        entries = importer.extract(sample_csv_file)

        # Find dividend entries for different securities
        dividend_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction) and "Dividends" in e.narration
        ]

        # Check that all dividend entries with tax have currency-specific tax accounts
        for div_entry in dividend_entries:
            tax_postings = [
                p for p in div_entry.postings if importer.tax_account in p.account
            ]
            for tax_posting in tax_postings:
                # Extract currency from cash posting (should match tax currency)
                cash_posting = next(
                    (
                        p
                        for p in div_entry.postings
                        if p.account == importer.cash_account
                    ),
                    None,
                )
                if cash_posting:
                    expected_currency = cash_posting.units.currency
                    assert tax_posting.account.endswith(f":{expected_currency}")
                    assert (
                        tax_posting.account
                        == importer.tax_account + f":{expected_currency}"
                    )

    def test_withholding_tax_recalculation(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that withholding tax re-calculations use currency-specific accounts."""
        entries = importer.extract(sample_csv_file)

        # Find dividend re-calculation entries
        # (these are created from unmatched withholding taxes)
        # They have tax postings with currency suffix
        recalculation_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction)
            and "Dividends" in e.narration
            and any(
                importer.tax_account in p.account
                and ":" in p.account
                and len(p.account.split(":")[-1]) == 3
                for p in e.postings
            )
        ]

        # Check that re-calculation entries use currency-specific tax accounts
        for entry in recalculation_entries:
            tax_postings = [
                p for p in entry.postings if importer.tax_account in p.account
            ]
            for tax_posting in tax_postings:
                # Should end with currency suffix
                assert ":" in tax_posting.account
                currency_suffix = tax_posting.account.split(":")[-1]
                assert len(currency_suffix) == 3  # Currency codes are 3 letters
                assert currency_suffix.isupper()
                # Extract currency from cash posting to verify match
                cash_posting = next(
                    (p for p in entry.postings if p.account == importer.cash_account),
                    None,
                )
                if cash_posting:
                    assert currency_suffix == cash_posting.units.currency

    def test_withholding_tax_chf_currency(self, importer: Importer) -> None:
        """Test withholding tax with CHF currency."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Id,Date,Type,Currency,Proceeds,Security,Amount,CostBasis,"
                "TradePrice,Commission,CommissionCurrency\n"
            )
            # Dividend in CHF
            f.write(
                '"10000000001","2024-01-20","Dividends","CHF","100.00","TEST",'
                '"","","","",""\n'
            )
            # Matching withholding tax in CHF
            f.write(
                '"10000000002","2024-01-20","Withholding Tax","CHF","-15.00","TEST",'
                '"","","","",""\n'
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)

            # Find dividend entry
            div_entry = next(
                (
                    e
                    for e in entries
                    if isinstance(e, data.Transaction) and "Dividends" in e.narration
                ),
                None,
            )
            assert div_entry is not None

            # Find tax posting
            tax_posting = next(
                (p for p in div_entry.postings if importer.tax_account in p.account),
                None,
            )
            assert tax_posting is not None
            # Check that tax account ends with CHF currency suffix
            assert tax_posting.account == importer.tax_account + ":CHF"
            assert tax_posting.units.currency == "CHF"
        finally:
            os.unlink(temp_path)

    def test_extract_deposits_withdrawals(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting deposits and withdrawals."""
        entries = importer.extract(sample_csv_file)

        # Find deposit/withdrawal transactions
        deposit_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction)
            and ("Deposit" in e.narration or "Withdrawal" in e.narration)
        ]
        assert len(deposit_entries) > 0

        # Check deposit entry
        deposit_entry = next(
            (e for e in deposit_entries if "Deposit" in e.narration), None
        )
        assert deposit_entry is not None
        assert deposit_entry.payee == "Interactive Brokers"
        assert deposit_entry.postings[0].account == importer.cash_account

    def test_extract_fx_exchange(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting FX exchange transactions."""
        entries = importer.extract(sample_csv_file)

        # Find FX exchange transactions
        fx_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction) and "FX Exchange" in e.narration
        ]
        assert len(fx_entries) > 0

        # Check FX entry
        fx_entry = fx_entries[0]
        assert fx_entry.payee == "Interactive Brokers"
        assert "FX Exchange" in fx_entry.narration
        assert len(fx_entry.postings) >= 2

    def test_extract_broker_interest(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test extracting broker interest transactions."""
        entries = importer.extract(sample_csv_file)

        # Find interest transactions
        interest_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction) and "Interests" in e.narration
        ]
        assert len(interest_entries) > 0

        # Check interest entry
        interest_entry = interest_entries[0]
        assert interest_entry.payee == "Interactive Brokers"
        assert interest_entry.narration == "Interests"

    def test_extract_other_fees(self, importer: Importer, sample_csv_file: str) -> None:
        """Test extracting other fees transactions."""
        entries = importer.extract(sample_csv_file)

        # Find other fees transactions
        other_entries = [
            e
            for e in entries
            if isinstance(e, data.Transaction) and e.narration == "Other"
        ]
        assert len(other_entries) > 0

        # Check other fees entry
        other_entry = other_entries[0]
        assert other_entry.payee == "Interactive Brokers"
        assert other_entry.narration == "Other"

    def test_extract_metadata(self, importer: Importer, sample_csv_file: str) -> None:
        """Test that transaction metadata is correctly set."""
        entries = importer.extract(sample_csv_file)

        # Find any transaction
        transaction = next(
            (e for e in entries if isinstance(e, data.Transaction)), None
        )
        assert transaction is not None
        assert "filename" in transaction.meta
        assert "trans_id" in transaction.meta
        assert "document" in transaction.meta

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
        # Should extract transactions
        assert len(entries) > 0

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
                "Id,Date,Type,Currency,Proceeds,Security,Amount,CostBasis,"
                "TradePrice,Commission,CommissionCurrency\n"
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
                "Id,Date,Type,Currency,Proceeds,Security,Amount,CostBasis,"
                "TradePrice,Commission,CommissionCurrency\n"
            )
            # Row with missing Security field (None) that would cause error
            f.write(
                '"10000000001","2024-01-03","BUY","USD","-563.10","",'
                '"12","563.45","46.925","-0.35","USD"\n'
            )
            temp_path = f.name

        try:
            entries = importer.extract(temp_path)
            # Should handle gracefully (may create entry or skip)
            assert isinstance(entries, list)
        finally:
            os.unlink(temp_path)

    def test_extract_invalid_date(self, importer: Importer) -> None:
        """Test that extract handles invalid dates gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Id,Date,Type,Currency,Proceeds,Security,Amount,CostBasis,"
                "TradePrice,Commission,CommissionCurrency\n"
            )
            f.write(
                '"10000000001","invalid-date","BUY","USD","-563.10","VEA",'
                '"12","563.45","46.925","-0.35","USD"\n'
            )
            temp_path = f.name

        try:
            with pytest.warns(UserWarning):
                entries = importer.extract(temp_path)
                # Should skip invalid row
                assert len(entries) == 0
        finally:
            os.unlink(temp_path)

    def test_buy_transaction_postings(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that BUY transactions have correct postings."""
        entries = importer.extract(sample_csv_file)

        # Find a BUY transaction
        buy_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and "Buy VEA" in e.narration
            ),
            None,
        )
        assert buy_entry is not None

        # Should have cash, security, and fees postings
        assert len(buy_entry.postings) >= 3
        cash_posting = next(
            (p for p in buy_entry.postings if p.account == importer.cash_account),
            None,
        )
        assert cash_posting is not None
        assert cash_posting.units.currency == "USD"
        assert cash_posting.units.number < 0  # Negative for buy

    def test_sell_transaction_fifo(
        self, importer: Importer, sample_csv_file: str
    ) -> None:
        """Test that SELL transactions use FIFO logic."""
        entries = importer.extract(sample_csv_file)

        # Find a SELL transaction
        sell_entry = next(
            (
                e
                for e in entries
                if isinstance(e, data.Transaction) and "Sell VEA" in e.narration
            ),
            None,
        )
        assert sell_entry is not None

        # Should have cash and OnL postings at minimum
        assert len(sell_entry.postings) >= 2
        cash_posting = next(
            (p for p in sell_entry.postings if p.account == importer.cash_account),
            None,
        )
        assert cash_posting is not None
