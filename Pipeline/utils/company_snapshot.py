"""Build a compact financial snapshot for a resolved ticker via yfinance."""
import time
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf


class CompanySnapshotBuilder:
    """Used by the legacy report_generator.py flow (via get_company_info) to attach market cap, P/E, revenue, etc. to a resolved ticker."""

    @staticmethod
    def cap_bucket(market_capitalization: Optional[int]) -> Optional[str]:
        """Map a company's market capitalization to a size bucket."""
        if market_capitalization is None:
            return None
        if market_capitalization < 2_000_000_000:
            return "small_cap"
        if market_capitalization < 10_000_000_000:
            return "mid_cap"
        return "large_cap"

    @staticmethod
    def safe_get_fast_info(ticker: yf.Ticker, field_name: str):
        try:
            fast_info_object = getattr(ticker, "fast_info", None) or {}
            return fast_info_object.get(field_name)
        except Exception:
            return None

    @staticmethod
    def safe_get_info(ticker: yf.Ticker, field_name: str) -> Any:
        try:
            info_dict = ticker.info or {}
            return info_dict.get(field_name)
        except Exception:
            return None

    @staticmethod
    def latest_financial_row(financials_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """
        Convert a yfinance financials DataFrame (annual or quarterly)
        into a dict for the most recent period (latest column).
        Returns {} if empty or on error.
        """
        try:
            if financials_df is None or financials_df.empty:
                return {}
            latest_period = financials_df.columns[0]
            latest_period_series = financials_df[latest_period]
            return {
                str(line_item): (
                    None if pd.isna(latest_period_series[line_item])
                    else latest_period_series[line_item]
                )
                for line_item in latest_period_series.index
            }
        except Exception:
            return {}

    def build(self, symbol: str) -> Dict[str, Any]:
        """
        Returns: symbol, market_cap, pe, enterprise_value, ebitda,
        revenue, net_income, cap_bucket, as_of (epoch seconds).
        """
        yf_ticker = yf.Ticker(symbol)

        market_capitalization = self.safe_get_fast_info(yf_ticker, "market_cap")
        if market_capitalization is None:
            market_capitalization = self.safe_get_info(yf_ticker, "marketCap")

        price_to_earnings = self.safe_get_fast_info(yf_ticker, "pe")
        if price_to_earnings is None:
            price_to_earnings = self.safe_get_info(yf_ticker, "trailingPE") or self.safe_get_info(yf_ticker, "forwardPE")

        enterprise_value = self.safe_get_info(yf_ticker, "enterpriseValue")

        # Annual financials (fallback to quarterly if annual missing)
        annual_financials_df = getattr(yf_ticker, "financials", None)
        latest_annual_financials = self.latest_financial_row(annual_financials_df)
        if not latest_annual_financials:
            quarterly_financials_df = getattr(yf_ticker, "quarterly_financials", None)
            latest_annual_financials = self.latest_financial_row(quarterly_financials_df)

        # Extract revenue and net income using common alternate labels
        total_revenue_value = None
        for revenue_key in ("Total Revenue", "TotalRevenue", "Revenue"):
            if revenue_key in latest_annual_financials:
                total_revenue_value = latest_annual_financials[revenue_key]
                break

        net_income_value = None
        for net_income_key in ("Net Income", "NetIncome", "Net Income Applicable To Common Shares"):
            if net_income_key in latest_annual_financials:
                net_income_value = latest_annual_financials[net_income_key]
                break

        # EBITDA may be present in info or as 'Ebitda' in financials
        ebitda_value = self.safe_get_info(yf_ticker, "ebitda")
        if ebitda_value is None and "Ebitda" in latest_annual_financials:
            ebitda_value = latest_annual_financials["Ebitda"]

        return {
            "symbol": symbol,
            "market_cap": market_capitalization,
            "pe": price_to_earnings,
            "enterprise_value": enterprise_value,
            "ebitda": ebitda_value,
            "revenue": total_revenue_value,
            "net_income": net_income_value,
            "cap_bucket": self.cap_bucket(market_capitalization),
            "as_of": int(time.time()),
        }
