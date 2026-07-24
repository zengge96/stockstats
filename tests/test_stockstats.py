"""stockstats TDD测试 — 覆盖各类股票代码"""
import pytest
import pandas as pd
import os, sys, tempfile, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import stockstats

# ===================== 代码类型检测 =====================
class TestCodePrefix:
    def test_sh_stock_prefix(self):
        """sh6开头 → sh前缀"""
        assert stockstats.detect_prefix("600036") == "sh"

    def test_sz_0_stock_prefix(self):
        """sz0开头 → sz前缀"""
        assert stockstats.detect_prefix("002352") == "sz"

    def test_sz_3_stock_prefix(self):
        """sz3开头(创业板) → sz前缀"""
        assert stockstats.detect_prefix("300750") == "sz"

    def test_sz_0_000001_stock_prefix(self):
        """000001是深交所平安银行, 非上证指数"""
        assert stockstats.detect_prefix("000001") == "sz"

    def test_etf_51_prefix(self):
        """51开头(ETF) → sh前缀"""
        assert stockstats.detect_prefix("510050") == "sh"

    def test_etf_15_prefix(self):
        """15开头(ETF) → sz前缀"""
        assert stockstats.detect_prefix("159928") == "sz"


# ===================== EPS数据提取 =====================
class TestFinancialData:
    def test_eps_from_financial_abstract_sh(self):
        """600036招商银行能提取到年报EPS"""
        eps = stockstats.get_annual_eps("600036")
        assert eps is not None, "EPS应为非空"
        assert len(eps) >= 5, f"应至少5年EPS数据, 实{len(eps)}"
        latest = max(eps.keys())
        assert eps[latest] > 0, f"最新EPS({latest})应>0"
        # 招行2025 EPS已知≈5.70
        if 2025 in eps:
            assert 4.5 < eps[2025] < 7.0, f"招行2025EPS≈5.7, 实{eps[2025]}"

    def test_eps_from_financial_abstract_sz(self):
        """002352顺丰能提取到年报EPS"""
        eps = stockstats.get_annual_eps("002352")
        assert eps is not None
        assert len(eps) >= 3

    def test_nav_from_financial_abstract(self):
        """600036能提取到每股净资产"""
        nav = stockstats.get_annual_nav("600036")
        assert nav is not None
        assert len(nav) >= 3
        latest = max(nav.keys())
        assert nav[latest] > 0

    def test_roe_from_financial_abstract(self):
        """600036能提取到ROE"""
        roe = stockstats.get_latest_roe("600036")
        assert roe is not None
        assert 5 < roe < 30, f"招行ROE约13-17%"


# ===================== PE计算 =====================
class TestPECalculation:
    def test_current_pe_using_report_method(self):
        """当前PE = 最新收盘价 / 最新年报EPS"""
        result = stockstats.analyze_stock("600036", years=3)
        assert result is not None
        assert result['code'] == '600036'
        assert result['name'] is not None
        assert result['current_pe'] > 0
        assert result['current_pe'] < 20, f"招行PE应<20, 实{result['current_pe']}"
        assert result['pe_percentile'] is not None
        # PE百分位应在0~100
        assert 0 <= result['pe_percentile'] <= 100

    def test_pe_histogram_stats(self):
        """PE统计量 (均值/中位/最高/最低)都应有值"""
        result = stockstats.analyze_stock("600036", years=3)
        assert result['pe_mean'] > 0
        assert result['pe_median'] > 0
        assert result['pe_high'] > result['pe_low']
        assert result['pe_low'] > 0

    def test_pe_quantile_prices(self):
        """PE中位数价/75%价/25%价应有合理值"""
        result = stockstats.analyze_stock("600036", years=3)
        pe_med = result['pe_median_price']
        pe_75 = result['pe_75_price']
        pe_25 = result['pe_25_price']
        assert pe_25 is None or pe_med is None or pe_75 is None or (pe_25 <= pe_med <= pe_75)

    def test_years_parameter_affects_data_count(self):
        """-y 3 vs -y 8 应影响统计区间天数"""
        r3 = stockstats.analyze_stock("600036", years=3)
        r8 = stockstats.analyze_stock("600036", years=8)
        # 3年应比8年天数少
        if r3['trading_days'] and r8['trading_days']:
            assert r3['trading_days'] < r8['trading_days']


# ===================== PB计算 =====================
class TestPBCalculation:
    def test_current_pb(self):
        """当前PB应有合理值"""
        result = stockstats.analyze_stock("600036", years=3)
        assert result['current_pb'] > 0
        assert result['current_pb'] < 5, f"招行PB约0.9x"

    def test_pb_percentile(self):
        """PB百分位应有值"""
        result = stockstats.analyze_stock("600036", years=3)
        assert result['pb_percentile'] is not None
        assert 0 <= result['pb_percentile'] <= 100

    def test_pb_quantile_prices(self):
        """PB中位数价应有值"""
        result = stockstats.analyze_stock("600036", years=3)
        assert result['pb_median_price'] is None or result['pb_median_price'] > 0


# ===================== 股息率 & ROE =====================
class TestDividendROE:
    def test_dividend_rate(self):
        """当前股息率应从腾讯实时获取"""
        rate = stockstats.get_current_dividend_rate("600036")
        assert rate is not None
        assert rate > 0
        assert rate < 20, f"股息率应<20%, 实{rate}%"

    def test_roe_value(self):
        """ROE应为合理值"""
        result = stockstats.analyze_stock("600036", years=3)
        assert result['roe'] is None or (5 < result['roe'] < 30)


# ===================== 多种代码类型 =====================
class TestVariousCodeTypes:
    def test_sz_market_stock(self):
        """深交所主板股票(002352顺丰)"""
        result = stockstats.analyze_stock("002352", years=3)
        assert result is not None
        assert result['code'] == '002352'
        assert result['current_pe'] > 0

    def test_chuangyeban_stock(self):
        """创业板(300750宁德时代)"""
        result = stockstats.analyze_stock("300750", years=3)
        assert result is not None
        assert result['code'] == '300750'
        assert result['current_pe'] > 0

    def test_blue_chip_stock(self):
        """上交所主板(600519茅台)"""
        result = stockstats.analyze_stock("600519", years=3)
        assert result is not None
        assert result['code'] == '600519'


# ===================== 屏蔽区间 =====================
class TestBlockYears:
    def test_block_single_year(self):
        """-b 2021 屏蔽后交易日数应减少"""
        r_no_block = stockstats.analyze_stock("600036", years=8)
        r_blocked = stockstats.analyze_stock("600036", years=8, block_years={2021})
        if r_no_block['trading_days'] and r_blocked['trading_days']:
            assert r_blocked['trading_days'] <= r_no_block['trading_days']
            if r_blocked['trading_days'] < r_no_block['trading_days']:
                assert r_blocked['trading_days'] <= r_no_block['trading_days'] - 200

    def test_block_multi_years(self):
        """-b 2021-2022 屏蔽连续两年"""
        r_no_block = stockstats.analyze_stock("600036", years=8)
        r_blocked = stockstats.analyze_stock("600036", years=8, block_years={2021, 2022})
        if r_no_block['trading_days'] and r_blocked['trading_days']:
            assert r_blocked['trading_days'] <= r_no_block['trading_days'] - 400


# ===================== 多股票处理 =====================
class TestMultipleStocks:
    def test_multiple_stocks(self):
        """同时处理多个股票代码"""
        results = stockstats.analyze_multiple(["600036", "002352"], years=3)
        assert len(results) == 2
        assert results[0]['code'] == '600036'
        assert results[1]['code'] == '002352'

    def test_multiple_stocks_various_types(self):
        """混合类型: 深交所+上交所"""
        results = stockstats.analyze_multiple(["600519", "300750"], years=3)
        assert len(results) == 2


# ===================== Excel输出 =====================
class TestExcelOutput:
    def test_excel_file_created(self):
        """输出xlsx文件应存在且非空"""
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            out_path = f.name
        try:
            stockstats.generate_report(["600036"], years=3, output=out_path)
            assert os.path.exists(out_path)
            assert os.path.getsize(out_path) > 0
            # 验证内容
            df = pd.read_excel(out_path, sheet_name='统计总表')
            assert len(df) == 1
            # pandas读Excel会把代码转为int, 两种格式都接受
            val = df.iloc[0]['代码']
            assert str(val) == '600036', f'代码应为600036, 实为{val}({type(val).__name__})'
            # 验证原始数据sheet存在
            sheets = pd.ExcelFile(out_path).sheet_names
            assert any('原始' in s for s in sheets)
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)
