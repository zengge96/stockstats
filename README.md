# stockstats — A股区间统计工具

基于 akshare 的 A 股区间统计工具。从命令行输入股票代码，输出 Excel 统计报告。

## 安装

```bash
pip install akshare openpyxl
```

## 用法

```bash
# 单只股票
python stockstats.py 600036 -y 8

# 多只股票
python stockstats.py 600036 002352 300750 -y 8

# 屏蔽异常年份
python stockstats.py 600036 -y 8 -b 2021

# 指定输出文件名
python stockstats.py 600036 -o 招商银行
```

## 参数

- `codes` — 股票代码（空格分隔）
- `-y N` — 统计年数，默认8，范围1-10
- `-b YYYY` or `-b YYYY-YYYY` — 屏蔽年份（可重复）
- `-o FILE` — 输出 xlsx 文件名

## 输出

Excel 工作簿包含：
- **统计总表** — 每个代码一行，PE/PB 百分位、均值、分位价等
- **原始_代码** — 每个代码独立 Sheet，含每日价格与 PE/PB

## 数据源

| 指标 | 来源 | 方法 |
|------|------|------|
| EPS | stock_financial_abstract 年报 | 前一年 EPS 逐年代入 |
| 价格 | Sina 日线 | — |
| PE/PB 百分位 | 历史排序 | 当前值在历史中的位置 |
| 股息率 | 腾讯实时 field[64] | TTM 口径 |
| ROE | stock_financial_abstract | 最新年报值 |
