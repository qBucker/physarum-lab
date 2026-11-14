# physarum-lab

> English top-level overview: [README.md](README.md). 本文件保留中文细节与实测记录。

黏菌活性软物质实验的**阶段 0**：先把信号链和记录管线跑通，再决定科学问题。

当前状态（2026-11-14）：**BCIkit M1（ADS1299）链路已打通；T1/T2/T6（600 s）PASS；2 h usbipd soak FAIL 但已归因到主机传输；Windows 原生 COM 30 min PASS；T3–T5 与首批 9 皿待做。**

S1/S1b 高维/非线性测试床（computed，模型内）：rho=0.9 二次耦合格，S1-L2 23/30（0.767；匹配 0.867），直接线性 D1/D2 4/30、7/30；S1-L2 线性格 0/30。**S1b 直接非线性基线 DQ-A（16 原始电极 + 8 区域几何 + 同一二次库）28/30（0.933；匹配 0.967），高于 S1-L2；DQ-A 线性格 0/30；S1 参考 p 差 0.0（120/120）。裁决修正：增益来自二次滞后特征，不是 POD/PCA 潜层表示；S1-L2 对直接线性的结果仍成立；R1 的线性潜层无增益结论不变。** 详见 `sim/results/s1_network/s1_summary.md` 与 `sim/results/s1b_direct_baseline/s1b_summary.md`。

> 本阶段只回答一件事：
> **“黏菌 → 电极 → ADS1299 → ESP32 → 笔记本”这条链路，能不能稳定地记录 24–48 小时？**

---

## 1. 路线：BCIkit M1（ADS1299）+ ESP32-DevKitC

```
黏菌 → 电极 → BCIkit M1（ADS1299，8 通道 24 位）→ ESP32-DevKitC V4 → USB → 笔记本
                                                          ↑
                                                手机延时摄影 + 启停/时钟卡同步
```

- **BCIkit M1**：ADS1299 8 通道 24 位生物电前端，250/500 SPS，需主控提供 2.048 MHz 主时钟；¥700，含 ESP32-DevKitC V4 与杜邦线。
- **主控**：ESP32-DevKitC V4；USB 串口 115200；板载固件 **v0.7.16**（本机实测；公开源码 v0.7.12，MIT）。
- **链路稳定的前提**：GND 与 CLK **拧成麻花**。单 GND 时寄存器读回偶发失败（`CONFIG1 expected 0x46 actual 0x06`），内部测试信号缺失；拧线后 20 次模式切换 0 WARN。
- **fallback（仅代码/协议，无硬件）**：ADS1256 + ESP32 路线（`firmware/ads1256_logger/`、`host/log_serial.py`、`vendor/ads1256/`）；ADS1256 模块**未购**，回退需另买模块 + 偏置件。旧协议存档在 `protocols/archive-ads1256-2026-11-12/`。
- **现有硬件清单**：BCIkit M1 + ESP32-DevKitC V4 + **11 根杜邦线** + USB 数据线；无 ADS1256、无电极、无台架耗材。

## 2. 实测状态

| 项 | 结果（measured） | 判据 | 证据 |
|---|---|---|---|
| T1 短路噪声（300 s） | **0.13 µV RMS**（σ≈6 counts，gain 24） | < 5 µV RMS | `data/bench_T1/` |
| T1 时钟/丢样 | 样本时钟 246.8 SPS；主机 244.6 SPS；UART 丢 595 样本（0.8%） | — | `data/bench_T1/` |
| T2 内部测试信号（120 s） | **3.742 mV pp**（比标称 3.750 低 0.2%） | 3.750 mV | `data/bench_T2/ANALYSIS.md` |
| T2 周期 | **干净周期 256 samples**（名义 0.9766 Hz @250 SPS） | 256 samples | 同上 |
| T2 时钟/异常 | 样本时钟 242.3 SPS → 干净周期约 0.947 Hz；部分高电平被拉长，均值周期 273 samples | — | 同上 |
| T2 通道一致性 | < 0.3% | — | 同上 |
| T2 隐藏高通 | 无（0.5 s 平台平坦） | 无 | 同上 |
| T6 600 s 短路 | 缺口 0.169%；样本钟 248.99 SPS | < 2% | `data/bench_T6/` |
| 2 h usbipd soak | 缺口 2.107%（稳态 1.566%） | < 2% | `data/bench_T6_soak2h/`（FAIL，归因 usbipd） |
| 30 min Windows COM | 缺口 0.0031%（14/445,637） | < 2% | `data/bench_win_uart_30m/` |

> 口径：T1/T2 为 measured；3.750 mV pp 为芯片规格换算（computed：±VREF/2400）。**0.9766 Hz 是名义值**（按 250 SPS）；实测样本时钟不是精确 250（T1 246.8、T2 242.3），绝对频率需按每次运行的 `fs_effective = 样本跨度 / 主机时长` 换算。周期 256 samples 是精确判据。

## 3. 接线（单板）

### 3.1 ESP32-DevKitC V4 → M1 POWER/CHAIN IN

| M1 丝印 | ESP32-DevKitC V4 | 说明 |
|---|---|---|
| GND（3 处） | GND | 至少一根可靠地线；**其中一根与 CLK 拧线** |
| 5V | 5V / VIN | 仅首板；整链只能有一个 5 V 入口 |
| SCLK | GPIO18 | SPI 时钟 |
| DIN | GPIO23 | ESP32 → M1 数据 |
| CS | GPIO22 | 片选，低有效 |
| START | GPIO26 | 采样启动 |
| RESET | GPIO27 | 复位，低有效 |
| PWDN | GPIO32 | 掉电控制，低有效 |
| CLK | GPIO25 | 2.048 MHz 主时钟；**与 GND 拧线** |
| DRDYC | GPIO34 | 采样就绪 |
| DISIN | 不接 | 首板前方没有上一块 M1 |
| RE | GPIO19 | M1 → ESP32 数据 |
| NC | 不接 | 保留位置，不接电源/GND/GPIO |

- 单板：**ROLE1=ON、ROLE2=ON**；**CHAIN OUT 空置**。
- 所有 GPIO 为 3.3 V；5 V 只接 `5V` 丝印，不得接到信号脚。
- 插拔、改 ROLE、改线束前必须断电。

### 3.2 模拟输入

- 模拟输入接口在板卡左侧，连接**通道电极、参考电极、偏置电极**；针脚以厂商配套线束/转接板和文档为准。本机 `vendor/bcikit/docs/` 未给出针脚表，不要按线色猜。
- **11 根杜邦线已全部用于数字接口**（SCLK/DIN/CS/START/RESET/PWDN/CLK/DRDYC/RE 共 9 根 + 5 V + 1 根 GND），没有余量接模拟输入；模拟输入必须另用配套线束/转接板。
- 两种接法，由固件模式选择：
  - **`diff` 全差分**：每通道一对电极（正/负输入），不依赖公共参考。阶段 0 首选。
  - **`eeg` 公共参考（SRB2）**：每通道一个测量电极 + 一个共用参考；偏置电极改善共模抑制（黏菌实验可选）。
- 电极：铜箔胶带 + 3 M KCl/琼脂盐桥；间距 10 mm；固定后不再移动；记录位置照片。
- 电极半电池电位必须落在 **±187.5 mV** 内（gain 24、VREF 4.5 V 的满量程）；超范围会饱和。

### 3.3 增益、量程与噪声

| 项 | 值 | 来源 |
|---|---:|---|
| 增益 | 24（四种模式统一） | 固件寄存器配置 |
| 基准 | 4.5 V 内部 | ADS1299 |
| 满量程 | **±187.5 mV** | computed：VREF / gain |
| LSB | **22.35 nV/count** | computed：VREF / (gain × 2^23) |
| T1 噪声 | 0.13 µV RMS（σ≈6 counts） | measured |

- 换算：`µV = counts × 0.0223517`。
- 当前主机脚本与公开固件只使用 gain 24；更低增益（1/4）需要固件支持，本机未验证。
- OpenBCI 33 字节帧**不含 ADS1299 状态字**；饱和只能从数据形态判断（贴 ±8,388,607 或长时间顶格）。

## 4. 采集模式

| `--mode` | 用途 | 配置 |
|---|---|---|
| `short` | 输入短接（T1） | 内部输入短接，BIAS 关闭 |
| `test` | 内部测试信号（T2） | 0.9765625 Hz，±1.875 mV 标称 |
| `diff` | 全差分（T3–T6、首批） | 每通道一对电极；内部 BIAS 开启 |
| `eeg` | 公共参考 SRB2 | 多通道 + 参考电极 |

## 5. 快速开始

### 5.1 固件与自检

板载固件已烧录。串口 115200 下执行 `info` 和 `status`，应看到：

```
ads_id=0x3E  register_verified=yes  clk_api=2048000
```

### 5.2 WSL 串口（usbipd-win）

Windows 管理员 PowerShell：

```
usbipd list
usbipd bind --busid <id>
usbipd attach --wsl --busid <id>
```

WSL：

```
sudo chmod 666 /dev/ttyUSB0
```

USB 线必须是数据线；充电线只显示充电，不枚举 CP2102。

### 5.3 依赖

```
pip install pyserial numpy scipy matplotlib
```

### 5.4 记录

```bash
# T1 短路噪声（300 s）
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode short \
    --duration 300 --outdir data/bench_T1

# T2 内部测试信号（120 s）
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode test \
    --duration 120 --outdir data/bench_T2

# T5 电极漂移（1 h，全差分）
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode diff \
    --duration 3600 --outdir data/bench_T5
```

- **UART 只跑 250 SPS**（OpenBCI 33 字节帧，115200 带宽约 72%）。500 SPS 需要 WiFi 原生帧，当前未实现 48 h logger。
- **串口 timeout 必须 10 ms**（脚本内置）；0.2 s 会让内核 tty 缓冲溢出，实测掉到 35 SPS。

## 6. 数据格式

```
data/<run_id>/
  raw.bin        # UART 原始字节流（OpenBCI 33 字节帧）
  samples.csv    # host_time_iso,host_unix,sample_number,ch1..ch8（ADS1299 counts）
  meta.json      # 配置、固件状态快照、通道统计
  SHA256SUMS
```

- **时基用样本号，不用主机时间戳**：T2 用主机时间算出 1.08 Hz；样本号给出干净周期 256 samples。
- 样本时钟实测 242–247 SPS（不是精确 250）；绝对频率按 `fs_effective = 样本跨度 / 主机时长` 换算（`bench_test.py` 自动计算）。
- `sample_number` 是 1 字节，每 256 样本回绕；丢样审计需按帧增量重建连续序号（T6）。
- 长时间记录存储量（computed）：raw 约 0.7 GB/24 h；raw + CSV 约 3–4 GB/24 h。
- 原始数据随仓库用 **Git LFS** 分发：`git lfs install && git lfs pull`。`data/bench-log.md` 为内部运行日志，不入库。

## 7. 分析

```bash
python3 host/bench_test.py data/bench_T1/samples.csv --label T1 --max-noise-uv 5
python3 host/bench_test.py data/bench_T2/samples.csv --label T2 --max-noise-uv 5000
```

- `bench_test.py` 自动识别 BCIKit CSV（counts）与旧 ADS1256 CSV（mV）。
- 输出 `bench_summary.json` 与 `bench_plot.png`（与 CSV 同目录）。
- T2 频率判据以样本号为准；脚本同时报告主机时钟有效采样率与序号缺口。

## 8. 协议与模板

- `protocols/bench-test.md`：T1–T6 台架测试（不碰黏菌）与判据
- `protocols/first-run.md`：首批生物实验（2 vs 4 食物源 + 对照）
- `templates/meta.json`：元数据模板
- `templates/prediction-card.md`：预注册卡模板
- 旧 ADS1256 协议与 BOM 存档：本地保留，未随公开仓发布

## 9. 安全与纪律

- 黏菌（Physarum polycephalum）为 BSL-1，正常洗手即可；培养皿污染即丢弃，不开盖处理。
- 电极不要直接接市电；所有电路共地，避免地环路。
- 记录原始数据，不覆盖；每次跑完写 `meta.json` 和 SHA256。
- 先做对照（空载 / 纯琼脂 / 死黏菌），再谈“黏菌电信号”。

## 10. 下一阶段（等台架 T3–T6）

1. T3–T6 台架通过 → 接黏菌，跑 3 皿 × 24–48 h。
2. 看三件事：信号是否高于空载对照；网络能否自动分割；两者是否有肉眼可见协变。
3. 再决定：走结构-电活动耦合（A 线）、测量管线（B 线），还是先修仪器。

## 11. 已知问题

- **T2 测试信号占空比异常**：约 1/4 的高电平被拉长（最长 492 samples），无丢帧、无重复样本；判为测试信号/固件 DRDY 处理属性，**不作时基参考**。
- **UART 丢样**：250 SPS 下有效 244.6 SPS（0.8%）；分析以样本号为准，T6 做缺口审计。
- **丢样归因（measured）**：2 h usbipd soak 的设备计数 `transport_drop=0`、`queue_overrun=0`、`spi_error=0`，主机少收 2.10% → 丢样在 usbipd/CP2102/USB/WSL 路径，不在 ADS1299/固件；Windows 原生 COM 30 min 仅 0.0031%。
- **无主机可控标记 GPIO**：厂商固件不提供标记命令；旧 ADS1256 的 GPIO32 LED 方案不适用。相机同步用启停事件 + 时钟卡（T6）。
- **模拟输入针脚未文档化**：本机厂商文档只给出数字接口针脚；模拟输入必须用配套线束/转接板。
- **BIAS 对非人体样品的影响未知**：`diff` 配置默认开启内部 BIAS（P/N 均参与），为浮动样品提供共模回路；是否引起电极极化由 T5 评估（当前无主机开关命令）。

## 12. 文档

- `docs/modeling-2026-11-14/index.html`：建模方法与工具报告（中文，含 R1/E1 图）。
- 13 页阶段 0 项目文档为内部文档，未随公开仓发布；以本 README、`protocols/` 与 `docs/modeling-2026-11-14/` 为准。
- `vendor/`：第三方固件/厂商文档，未随公开仓发布；BCIkit 公开固件为 MIT，厂商文档从厂商获取。
- `firmware/ads1256_logger/`、`host/log_serial.py`：ADS1256 代码 fallback（硬件未购）。
- `firmware/ads1115_logger/`：更早的 ADS1115 链路，legacy 参考。
