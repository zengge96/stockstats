#!/usr/bin/env python3
"""stockstats — A股区间统计工具 (PE/PB百分位分析)"""
import sys, os, argparse, json, urllib.request, statistics, tempfile
from datetime import datetime, timedelta
import pandas as pd
import openpyxl
import akshare as ak

__version__ = "0.1.0"

# ===================== 代码前缀检测 =====================
def detect_prefix(code: str) -> str:
    """
    根据股票代码判断新浪/腾讯前缀。
    6开头 → 'sh' (上证主板)
    0/3开头 → 'sz' (深证主板/创业板)
    5开头 → 'sh' (上证ETF)
    1开头 → 'sz' (深证ETF)
    """
    if code.startswith(('6', '5')):
        return 'sh'
    return 'sz'


# ===================== 财务数据提取 =====================
def get_annual_eps(code: str) -> dict:
    """
    从 stock_financial_abstract 提取年报EPS。
    返回 {年份: EPS, ...} 字典。
    """
    try:
        df = ak.stock_financial_abstract(symbol=code)
    except Exception:
        return None
    
    annual_cols = sorted(
        [c for c in df.columns
         if str(c).isdigit() and str(c)[4:8] == '1231']
    )
    eps_row = df[df['指标'] == '基本每股收益']
    if eps_row.empty:
        return None
    
    eps_map = {}
    for c in annual_cols:
        v = eps_row.iloc[0][c]
        if v is not None and not (isinstance(v, float) and (v != v or v == 0)):
            eps_map[int(str(c)[:4])] = float(v)
    return eps_map if eps_map else None


def get_annual_nav(code: str) -> dict:
    """
    提取年报每股净资产。
    返回 {年份: 每股净资产, ...} 字典。
    """
    try:
        df = ak.stock_financial_abstract(symbol=code)
    except Exception:
        return None
    
    annual_cols = sorted(
        [c for c in df.columns
         if str(c).isdigit() and str(c)[4:8] == '1231']
    )
    nav_row = df[df['指标'] == '每股净资产']
    if nav_row.empty:
        return None
    
    nav_map = {}
    for c in annual_cols:
        v = nav_row.iloc[0][c]
        if v is not None and not (isinstance(v, float) and (v != v or v == 0)):
            nav_map[int(str(c)[:4])] = float(v)
    return nav_map if nav_map else None


def get_latest_roe(code: str) -> float:
    """提取最新年报ROE(%)"""
    try:
        df = ak.stock_financial_abstract(symbol=code)
    except Exception:
        return None
    
    annual_cols = sorted(
        [c for c in df.columns
         if str(c).isdigit() and str(c)[4:8] == '1231']
    )
    # akshare的指标名是'净资产收益率(ROE)'或'加权净资产收益率'
    roe_row = df[df['指标'] == '净资产收益率(ROE)']
    if roe_row.empty:
        roe_row = df[df['指标'] == '加权净资产收益率']
    if roe_row.empty:
        return None
    
    v = roe_row.iloc[0][annual_cols[-1]]
    if v is not None and not (isinstance(v, float) and (v != v or v == 0)):
        return float(v)
    return None


def get_current_dividend_rate(code: str) -> float:
    """从腾讯实时行情获取当前TTM股息率 field[64]"""
    prefix = detect_prefix(code)
    try:
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read().decode('gbk')
        parts = raw.split('~')
        if len(parts) > 64 and parts[64]:
            return float(parts[64])
    except Exception:
        pass
    return None


# ===================== PE/PB计算 =====================
def get_price_history(code: str, prefix: str, max_days: int = 2500) -> list:
    """获取日线数据（新浪API）"""
    url = (
        f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen={max_days}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return []


def get_stock_name(code: str, prefix: str) -> str:
    """获取股票名称"""
    try:
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read().decode('gbk')
        parts = raw.split('~')
        if len(parts) > 1:
            return parts[1]
    except Exception:
        pass
    return code


def compute_pe_pb_history(daily_all: list, eps_map: dict, nav_map: dict,
                          years: int = 8, block_years: set = None):
    """
    计算PE和PB历史序列 (年报法: 前一年EPS逐年代入)。
    返回 (pe_history, pb_history, date_range)
    """
    pe_history = []
    pb_history = []
    date_range = None
    
    if block_years is None:
        block_years = set()
    
    for d in daily_all:
        day_str = d['day']
        year = int(day_str[:4])
        close = float(d['close'])
        
        # 屏蔽区间
        if year in block_years:
            continue
        
        # PE: 前一年EPS
        known_eps = eps_map.get(year - 1) or eps_map.get(year)
        if known_eps and known_eps > 0 and 5 < close / known_eps < 80:
            pe_history.append(close / known_eps)
        
        # PB: 前一年NAV
        known_nav = nav_map.get(year - 1) or nav_map.get(year)
        if known_nav and known_nav > 0 and 0.5 < close / known_nav < 20:
            pb_history.append(close / known_nav)
    
    if date_range is None and len(daily_all) >= 2:
        date_range = f"{daily_all[0]['day']} ~ {daily_all[-1]['day']}"
    
    return pe_history, pb_history, date_range


def analyze_stock(code: str, years: int = 8, block_years: set = None) -> dict:
    """
    分析单只股票，返回全部统计指标。
    
    返回:
    {
        'code': '600036',
        'name': '招商银行',
        '统计区间': '...',
        'trading_days': 2000,
        'current_pe': 6.8,
        'pe_percentile': 20.4,
        'pe_mean': 9.0,
        'pe_median': 8.5,
        'pe_high': 15.0,
        'pe_low': 5.0,
        'pe_median_price': ...,
        'pe_75_price': ...,
        'pe_25_price': ...,
        'current_pb': 0.89,
        ... (PB同理)
        'dividend_rate': 5.16,
        'roe': 13.71,
    }
    """
    if block_years is None:
        block_years = set()
    
    prefix = detect_prefix(code)
    name = get_stock_name(code, prefix)
    
    # 财务数据
    eps_map = get_annual_eps(code)
    nav_map = get_annual_nav(code)
    roe = get_latest_roe(code)
    dividend_rate = get_current_dividend_rate(code)
    
    if eps_map is None or nav_map is None:
        return {'code': code, 'name': name, 'error': '财务数据获取失败'}
    
    latest_eps = eps_map.get(max(eps_map.keys()))
    latest_nav = nav_map.get(max(nav_map.keys()))
    
    # 日线
    daily_all = get_price_history(code, prefix)
    if not daily_all:
        return {'code': code, 'name': name, 'error': '日线数据获取失败'}
    
    current_close = float(daily_all[-1]['close'])
    
    # 截取指定年数
    # 年 ≈ 250 个交易日
    n_days = min(years * 250, len(daily_all))
    daily_subset = daily_all[-n_days:]
    
    # 计算PE/PB历史
    pe_history, pb_history, date_range = compute_pe_pb_history(
        daily_subset, eps_map, nav_map, years, block_years
    )
    
    trading_days = len(pe_history)
    
    # === PE统计 ===
    current_pe = current_close / latest_eps if latest_eps and latest_eps > 0 else None
    
    pe_percentile = None
    pe_mean = None
    pe_median = None
    pe_high = None
    pe_low = None
    pe_median_price = None
    pe_75_price = None
    pe_25_price = None
    
    if pe_history and current_pe:
        pe_sorted = sorted(pe_history)
        pe_percentile = round(sum(1 for p in pe_history if p < current_pe) / len(pe_history) * 100, 1)
        pe_mean = round(statistics.mean(pe_history), 1)
        pe_median = round(statistics.median(pe_history), 1)
        pe_high = round(max(pe_history), 1)
        pe_low = round(min(pe_history), 1)
        
        # PE分位价
        def pe_quantile_price(pct):
            idx = int(len(pe_sorted) * pct / 100)
            idx = min(idx, len(pe_sorted) - 1)
            return round(pe_sorted[idx] * latest_eps, 2) if latest_eps else None
        
        pe_median_price = round(pe_median * latest_eps, 2) if latest_eps else None
        pe_75_price = pe_quantile_price(75)
        pe_25_price = pe_quantile_price(25)
    
    # === PB统计 ===
    current_pb = current_close / latest_nav if latest_nav and latest_nav > 0 else None
    
    pb_percentile = None
    pb_mean = None
    pb_median = None
    pb_high = None
    pb_low = None
    pb_median_price = None
    pb_75_price = None
    pb_25_price = None
    
    if pb_history and current_pb:
        pb_sorted = sorted(pb_history)
        pb_percentile = round(sum(1 for p in pb_history if p < current_pb) / len(pb_history) * 100, 1)
        pb_mean = round(statistics.mean(pb_history), 2)
        pb_median = round(statistics.median(pb_history), 2)
        pb_high = round(max(pb_history), 2)
        pb_low = round(min(pb_history), 2)
        
        def pb_quantile_price(pct):
            idx = int(len(pb_sorted) * pct / 100)
            idx = min(idx, len(pb_sorted) - 1)
            return round(pb_sorted[idx] * latest_nav, 2) if latest_nav else None
        
        pb_median_price = round(pb_median * latest_nav, 2) if latest_nav else None
        pb_75_price = pb_quantile_price(75)
        pb_25_price = pb_quantile_price(25)
    
    return {
        'code': code,
        'name': name,
        '统计区间': date_range or '',
        'trading_days': trading_days,
        'current_pe': round(current_pe, 2) if current_pe else None,
        'pe_percentile': pe_percentile,
        'pe_mean': pe_mean,
        'pe_median': pe_median,
        'pe_high': pe_high,
        'pe_low': pe_low,
        'pe_median_price': pe_median_price,
        'pe_75_price': pe_75_price,
        'pe_25_price': pe_25_price,
        'current_pb': round(current_pb, 2) if current_pb else None,
        'pb_percentile': pb_percentile,
        'pb_mean': pb_mean,
        'pb_median': pb_median,
        'pb_high': pb_high,
        'pb_low': pb_low,
        'pb_median_price': pb_median_price,
        'pb_75_price': pb_75_price,
        'pb_25_price': pb_25_price,
        'dividend_rate': dividend_rate,
        'roe': round(roe, 2) if roe else None,
    }


# ===================== 多股票 =====================
def analyze_multiple(codes: list, years: int = 8, block_years: set = None) -> list:
    return [analyze_stock(c, years, block_years) for c in codes]


# ===================== Excel报告 =====================
def generate_report(codes: list, years: int = 8,
                     block_years: set = None, output: str = None):
    """生成xlsx报告"""
    results = analyze_multiple(codes, years, block_years)
    
    if output is None:
        code_str = '_'.join(c[:6] for c in codes[:5])
        output = f'{code_str}.xlsx'
    
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    # Sheet 1: 统计总表
    columns = [
        '代码', '名称', '统计区间', '交易日数',
        'TTM PE', 'PE百分位', 'PE均值', 'PE中位', 'PE最高', 'PE最低',
        'PE中位数价', 'PE75%分位价', 'PE25%分位价',
        'TTM PB', 'PB百分位', 'PB均值', 'PB中位', 'PB最高', 'PB最低',
        'PB中位数价', 'PB75%分位价', 'PB25%分位价',
        'TTM股息率[TTM]', 'ROE'
    ]
    
    rows = []
    for r in results:
        if 'error' in r:
            rows.append([r.get('code'), r.get('name'), 'ERROR: ' + r['error']] +
                        [''] * (len(columns) - 3))
        else:
            rows.append([
                r['code'], r['name'], r['统计区间'], r['trading_days'],
                r['current_pe'], r['pe_percentile'], r['pe_mean'], r['pe_median'],
                r['pe_high'], r['pe_low'], r['pe_median_price'], r['pe_75_price'],
                r['pe_25_price'],
                r['current_pb'], r['pb_percentile'], r['pb_mean'], r['pb_median'],
                r['pb_high'], r['pb_low'], r['pb_median_price'], r['pb_75_price'],
                r['pb_25_price'],
                r['dividend_rate'], r['roe'],
            ])
    
    df_summary = pd.DataFrame(rows, columns=columns)
    # 代码列保存为字符串，避免pandas转为int
    df_summary['代码'] = df_summary['代码'].astype(str)
    df_summary.to_excel(writer, sheet_name='统计总表', index=False)
    
    # Sheet 2+: 每个代码原始数据(用Excel公式计算PE/PB)
    for code in codes:
        prefix = detect_prefix(code)
        daily_all = get_price_history(code, prefix)
        if not daily_all:
            continue
        
        eps_map = get_annual_eps(code)
        nav_map = get_annual_nav(code)
        if not eps_map:
            continue
        
        # 用openpyxl直接写原始数据+公式
        from openpyxl import Workbook
        sheet_name = f'原始_{code}'
        ws = writer.book.create_sheet(title=sheet_name[:31])  # Excel sheet名最长31字符
        
        headers = ['日期', '收盘价', 'EPS', '每股净资产', '成交量', 'PE', 'PB']
        for j, h in enumerate(headers):
            cell = ws.cell(row=1, column=j+1)
            cell.value = h
            cell.font = openpyxl.styles.Font(bold=True)
        
        row_num = 2
        for d in daily_all[-2500:]:
            close = float(d['close'])
            yr = int(d['day'][:4])
            known_eps = eps_map.get(yr - 1) or eps_map.get(yr)
            known_nav = nav_map.get(yr - 1) or nav_map.get(yr)
            
            if not known_eps or known_eps <= 0:
                continue
            
            # 写入原始数据
            ws.cell(row=row_num, column=1, value=d['day'])
            ws.cell(row=row_num, column=2, value=close)
            ws.cell(row=row_num, column=3, value=known_eps)
            ws.cell(row=row_num, column=4, value=known_nav if known_nav else '')
            ws.cell(row=row_num, column=5, value=float(d.get('volume', 0)))
            # PE公式 = 收盘价/EPS
            ws.cell(row=row_num, column=6).value = f'=IF(C{row_num}>0,B{row_num}/C{row_num},"")'
            # PB公式 = 收盘价/每股净资产
            ws.cell(row=row_num, column=7).value = f'=IF(D{row_num}>0,B{row_num}/D{row_num},"")'
            row_num += 1
        
        # 在原始数据页添加3个Excel图表（股价/PE/PB）
        from openpyxl.chart import LineChart, Reference
        
        # 股价图
        chart_p = LineChart()
        chart_p.title = f"{code} 股价走势"
        chart_p.style = 10
        chart_p.width = 18
        chart_p.height = 10
        data_p = Reference(ws, min_col=2, min_row=1, max_row=row_num-1)
        cats = Reference(ws, min_col=1, min_row=2, max_row=row_num-1)
        chart_p.add_data(data_p, titles_from_data=True)
        chart_p.set_categories(cats)
        chart_p.y_axis.title = "价格（元）"
        ws.add_chart(chart_p, "I1")
        
        # PE图
        chart_pe = LineChart()
        chart_pe.title = f"{code} PE走势"
        chart_pe.style = 10
        chart_pe.width = 18
        chart_pe.height = 10
        data_pe = Reference(ws, min_col=6, min_row=1, max_row=row_num-1)
        chart_pe.add_data(data_pe, titles_from_data=True)
        chart_pe.set_categories(cats)
        chart_pe.y_axis.title = "PE"
        ws.add_chart(chart_pe, "I19")
        
        # PB图
        chart_pb = LineChart()
        chart_pb.title = f"{code} PB走势"
        chart_pb.style = 10
        chart_pb.width = 18
        chart_pb.height = 10
        data_pb = Reference(ws, min_col=7, min_row=1, max_row=row_num-1)
        chart_pb.add_data(data_pb, titles_from_data=True)
        chart_pb.set_categories(cats)
        chart_pb.y_axis.title = "PB"
        ws.add_chart(chart_pb, "I37")
    
    writer.close()
    return output


# ===================== CLI入口 =====================
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='stockstats — A股区间统计工具 (PE/PB百分位分析)'
    )
    parser.add_argument('codes', nargs='+', help='股票代码，空格分隔')
    parser.add_argument('-y', '--years', type=int, default=8,
                        help='统计年数，默认8，范围1-10')
    parser.add_argument('-b', '--block', action='append', default=[],
                        help='屏蔽年份(可重复)，如 -b 2021 -b 2022')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='输出xlsx文件名')
    return parser.parse_args(argv)


def parse_block_years(block_args: list) -> set:
    """解析 -b 参数为年份集合"""
    years = set()
    for arg in block_args:
        if '-' in arg:
            parts = arg.split('-')
            start, end = int(parts[0]), int(parts[1])
            years.update(range(start, end + 1))
        else:
            years.add(int(arg))
    return years


def main():
    args = parse_args()
    block_years = parse_block_years(args.block)
    
    print(f"stockstats v{__version__}")
    print(f"代码: {' '.join(args.codes)}")
    print(f"周期: {args.years}年")
    if block_years:
        print(f"屏蔽: {sorted(block_years)}")
    print()
    
    results = analyze_multiple(args.codes, args.years, block_years)
    
    # 控制台输出统计总表
    print(f"{'代码':>6} {'名称':<10} {'PE':>6} {'P%':>6} {'均值':>6} {'PB':>6} {'ROE':>5} {'股息率':>6}")
    print("-" * 55)
    for r in results:
        if 'error' in r:
            print(f"{r.get('code','?'):>6} {r.get('name','?'):<10} ❌ {r.get('error','?')}")
        else:
            pe = f"{r.get('current_pe',0):.1f}x" if r.get('current_pe') else 'N/A'
            pp = f"P{r.get('pe_percentile',0):.0f}" if r.get('pe_percentile') is not None else 'N/A'
            pm = f"{r.get('pe_mean',0):.1f}x" if r.get('pe_mean') else 'N/A'
            pb = f"{r.get('current_pb',0):.1f}x" if r.get('current_pb') else 'N/A'
            ro = f"{r.get('roe',0):.1f}%" if r.get('roe') else 'N/A'
            dr = f"{r.get('dividend_rate',0):.1f}%" if r.get('dividend_rate') else 'N/A'
            print(f"{r['code']:>6} {r['name']:<10} {pe:>6} {pp:>6} {pm:>6} {pb:>6} {ro:>5} {dr:>6}")
    print()
    
    out_path = generate_report(args.codes, years=args.years,
        block_years=block_years, output=args.output
    )
    print(f"✅ 报告已生成: {os.path.abspath(out_path)}")


if __name__ == '__main__':
    main()
