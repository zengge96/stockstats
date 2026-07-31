# stockstats — A股区间统计工具

基于 akshare + 新浪日线 + 腾讯行情的 A 股区间统计工具。
从命令行输入股票代码/指数/ETF，自动计算 PE/PB 历史百分位、均值、分位价等指标，
输出 Excel 统计报告（统计总表 + 每标的独立原始数据 Sheet + 走势图表）。

支持 **个股**、**中证指数 (.CSI)**、**ETF基金 (.ETF)** 三类标的。

## 功能特性

- **个股分析**：PE/PB 历史百分位、均值、中位数、最高/最低、25%/75% 分位价、TTM 股息率、ROE
- **指数分析**：`.CSI` 后缀识别中证指数（如 `000300.CSI`），用 CSIndex 官方历史 PE 数据
- **ETF 分析**：`.ETF` 后缀自动解析跟踪指数（如 `159928.ETF` → 中证主要消费 000932）
- **Excel 报告**：
  - `统计总表` Sheet — 所有标的一行一个，全部统计指标
  - `原始_代码` Sheet — 每个标的独立原始数据页（日期/收盘价/EPS/每股净资产/成交量）
  - PE/PB 用 **Excel 公式** 实时计算（`=IF(C>0,B/C,NA())`），日期存为 datetime 对象，图表坐标轴干净
  - 每页内置 3 个 Excel 图表：股价走势 / PE 走势 / PB 走势（指数/ETF 为 PE 趋势图）
- **控制台统计表**：运行结束直接输出代码/名称/PE/百分位/均值/PB/ROE/股息率
- **屏蔽年份**：`-b` 参数剔除异常年份数据，避免污染百分位
- **PE/PB 过滤**：EPS/NAV>0 前提下 PE/PB≥0 即纳入，**无上限截断**，银行股低 PE（3~5x）与高 PE 成长股历史均完整保留

## 安装

```bash
pip install -r requirements.txt
# 即: akshare>=1.16.0 openpyxl>=3.1.0 pandas>=2.0.0
```

## 用法

```bash
# 单只股票 (默认8年)
python stockstats.py 600036

# 多只股票
python stockstats.py 600036 002352 300750 -y 8

# 指定统计年数 (1-10年)
python stockstats.py 600036 -y 5

# 屏蔽异常年份 (可重复, 支持区间)
python stockstats.py 600036 -y 8 -b 2021 -b 2018-2019

# 指定输出文件名
python stockstats.py 600036 -o 招商银行

# 指数分析 (.CSI 后缀)
python stockstats.py 000300.CSI 000922.CSI -y 8

# ETF 分析 (.ETF 后缀, 自动解析跟踪指数)
python stockstats.py 159928.ETF 510050.ETF -y 8

# 混合: 个股 + 指数 + ETF
python stockstats.py 600036 000300.CSI 159928.ETF -o 组合统计
```

## 参数

| 参数 | 说明 |
|------|------|
| `codes` | 股票代码 / 指数(带`.CSI`) / ETF(带`.ETF`)，空格分隔 |
| `-y N` | 统计年数，默认 8，范围 1-10 |
| `-b YYYY` 或 `-b YYYY-YYYY` | 屏蔽年份（可重复、可区间） |
| `-o FILE` | 输出 xlsx 文件名 |

## 输出

Excel 工作簿结构：

- **统计总表** — 每标的一行：
  `代码 / 名称 / 统计区间 / 交易日数 / TTM PE / PE百分位 / PE均值 / PE中位 / PE最高 / PE最低 / PE中位数价 / PE75%分位价 / PE25%分位价 / TTM PB / PB百分位 / ... / TTM股息率 / ROE`
- **原始_代码** — 每标的独立 Sheet：
  - 个股：日期(datetime) / 收盘价 / EPS / 每股净资产 / 成交量 / PE(公式) / PB(公式)
  - 指数/ETF：日期 / 指数收盘 / 滚动市盈率
  - 3 个 Excel 图表：股价走势、PE 走势、PB 走势

控制台同时输出简表：`代码 名称 PE P% 均值 PB ROE 股息率`。

## 数据源与方法论

| 指标 | 来源 | 方法 |
|------|------|------|
| 日线价格 | 新浪日线 API (`vip.stock.finance.sina.com.cn`) | 最多 2500 条，按 `-y` 截取 |
| EPS | akshare `stock_financial_abstract` 年报 | **前一年年报 EPS 逐年代入**（报告口径） |
| 每股净资产 | akshare `stock_financial_abstract` 年报 | 前一年 NAV 逐年代入 |
| PE 百分位 | 历史排序 | 当前 PE 在历史样本中的位置 |
| 指数/ETF PE | CSIndex 官方 (`stock_zh_index_hist_csindex`) | 滚动市盈率历史 |
| 股息率 | 腾讯实时行情 `qt.gtimg.cn` field[64] | TTM 口径 |
| ROE | akshare `stock_financial_abstract` | 最新年报值 |

**代码前缀自动检测**：`6/5` 开头 → `sh`；`0/3/1` 开头 → `sz`（含 000001=平安银行，非上证指数）。

**PE/PB 计算口径**：`PE = 收盘价 / 前一年年报EPS`，`PB = 收盘价 / 前一年每股净资产`。
过滤条件：EPS/NAV > 0 且 PE/PB ≥ 0，**无上限** —— 低 PE（银行股 3~5x）与高 PE（成长股早期）历史均完整保留，百分位不失真。

## 构建（GitHub Action）

仓库内置 CI 工作流 `.github/workflows/build.yml`，手动触发可构建：

- **Windows x64**：PyInstaller 单文件 EXE
- **Linux ARM64**：QEMU + ARM64 容器内 PyInstaller 交叉构建

构建时需 `--collect-data akshare` 收集 akshare 的 calendar.json 等数据文件。

## 开发

TDD 开发，27 个测试覆盖：

- 代码前缀检测（sh/sz/ETF/000001 边界）
- EPS/NAV/ROE 提取（上证/深证/创业板）
- 指数名称 → CSI 代码映射
- ETF 跟踪指数解析
- PE/PB 历史计算与百分位

```bash
python -m pytest tests/ -q
```

## 版本历史

| 版本 | 说明 |
|------|------|
| v0.2.1 | PE/PB 过滤放宽为下限 0 / 无上限，修复银行股低 PE 历史截断 |
| v0.2.0 | 控制台输出统计表；原始数据页改用 Excel 公式 + datetime 日期对象 |
| v0.1.x | 新增指数/ETF 分析（CSIndex 数据源）；原始数据页增加 Excel 图表；GitHub Action 打包；TDD 测试体系 |
| v0.1.0 | 初始版本（新浪日线 + akshare 财报） |
