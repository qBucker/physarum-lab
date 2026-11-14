# 台架测试协议（BCIkit M1 / ADS1299，不碰黏菌）

> 目的：在接生物材料之前，先证明“电极 → ADS1299 → ESP32 → 笔记本”这条链路能测到 µV 级慢信号，并且漂移、50 Hz 可控。
> 通过标准：T1–T6 全部 PASS，才允许接黏菌。
> 进度：**T1/T2 PASS（2026-11-11）**；**T6 PASS（2026-11-12）**；T3–T5 待做。

## 0. 准备

### 0.1 硬件

- **BCIkit M1**（ADS1299，8 通道 24 位）+ **ESP32-DevKitC V4**；单板 ROLE1=ON、ROLE2=ON，CHAIN OUT 空置。
- 数字接线见 README §3.1；**GND 与 CLK 拧成麻花**（单 GND 时寄存器读回偶发失败）。
- 模拟输入用厂商配套线束/转接板接通道、参考、偏置电极；针脚以厂商文档为准。
- 整链只有一个 5 V 入口；插拔、改 ROLE、改线束前断电。
- 自检：串口 115200 执行 `info` / `status`，应看到 `ads_id=0x3E`、`register_verified=yes`、`clk_api=2048000`。

### 0.2 软件

- 记录脚本：`host/bcikit_openbci.py`。
- 依赖：`pip install pyserial numpy scipy matplotlib`。
- WSL 串口：`usbipd list` → `usbipd bind --busid <id>` → `usbipd attach --wsl --busid <id>`；然后 `sudo chmod 666 /dev/ttyUSB0`。
- **串口 timeout 10 ms**（脚本内置）；改成 0.2 s 会让内核 tty 缓冲溢出，实测掉到 35 SPS。

### 0.3 关键配置

- gain **24**；VREF **4.5 V**；满量程 **±187.5 mV**；LSB **22.35 nV/count**。
- 采样率标称 **250 SPS**（UART OpenBCI 帧）；**实测样本时钟 242–247 SPS**（T1 246.8、T2 242.3），绝对时基按 `fs_effective = 样本跨度 / 主机时长` 标定。500 SPS 需要 WiFi 原生帧，当前未实现。
- **时基用样本号**：OpenBCI 帧的 `sample_number` 为 1 字节，每 256 样本回绕。
- OpenBCI 帧不含 ADS1299 状态字；饱和从数据形态判断（贴 ±8,388,607 或长时间顶格）。

| `--mode` | 用途 |
|---|---|
| `short` | 输入短接（T1） |
| `test` | 内部测试信号（T2） |
| `diff` | 全差分（T3–T6、首批） |
| `eeg` | 公共参考 SRB2（多通道 + 参考电极） |

## T1 静态噪声（输入短接）— PASS 2026-11-11

**接线**：`short` 模式，内部输入短接；不接电极。

**采集**：

```bash
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode short \
    --duration 300 --outdir data/bench_T1
python3 host/bench_test.py data/bench_T1/samples.csv --label T1 --max-noise-uv 5
```

**判据**：

- 0.01–5 Hz 频带 RMS **< 5 µV**
- 漂移 **< 1 mV/h**（300 s 只作参考；真正的漂移判据在 T5）
- 无饱和、无通道固定值

**实测**：0.13 µV RMS（σ≈6 counts）；73,455 帧；样本时钟 246.8 SPS、主机 244.6 SPS；8 帧多通道异常（0.011%）。证据 `data/bench_T1/`。

## T2 内部测试信号 — PASS 2026-11-11

**接线**：`test` 模式，内部测试信号；不接电极。

**采集**：

```bash
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode test \
    --duration 120 --outdir data/bench_T2
```

**判据**：

- 峰峰值 **3.750 mV ± 1%**（标称 ±VREF/2400 = ±1.875 mV）
- **干净周期 256 samples**（名义 0.9765625 Hz @ 250 SPS；按实测样本时钟 242.3 SPS 约 0.947 Hz）
- 8 通道幅度一致（< 1%）
- 平台平坦（无隐藏高通）

**实测**：3.742 mV pp（低 0.2%）；干净周期 256 samples；样本时钟 242.3 SPS；8 通道差 < 0.3%；平台平坦。证据 `data/bench_T2/ANALYSIS.md`。

**占空比异常**：部分高电平被拉长（见 ANALYSIS.md），均值周期 273 samples；周期判据以**干净周期**为准，异常周期不计入频率统计。

> 异常记录：约 1/4 的高电平被拉长（最长 492 samples），无丢帧、无重复样本。判为测试信号/固件 DRDY 处理属性，**不得把内部测试信号当时基参考**。

## T3 慢波形（阶跃/方波）

**信号源**：电池（1.5 V）经分压 + 手动开关产生 1–10 mV 阶跃；或用函数发生器 + RC 低通（截止 ~1 Hz）。信号源的共模必须按厂商线束的参考/偏置接法建立，不能悬空。

**接线**：信号源跨接 CH1 的 INP/INN（`diff` 模式）；先确认输出在 ±187.5 mV 内。

**采集**：

```bash
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode diff \
    --duration 120 --outdir data/bench_T3
```

**判据**：

- 波形无明显削顶
- 阶跃幅度误差 **< 10%**
- 建立时间/相位延迟可由 RC 或数字滤波器解释
- 重复 3 次，幅度一致（< 5%）

## T4 50 Hz 抑制

**做法**：手指靠近电极线的绝缘外皮，或把电极线靠近电源线，制造 50 Hz 干扰；`diff` 模式记录 60 s。

**采集**：

```bash
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode diff \
    --duration 60 --outdir data/bench_T4
python3 host/bench_test.py data/bench_T4/samples.csv --label T4 \
    --max-noise-uv 1000 --max-drift-mv-h 1000 --max-mains-ratio 0.5
```

**判据**：

- 软件 notch（50 Hz）后，49–51 Hz 功率占比 **< 0.5**
- 同时记录 raw 占比，作为后续分析依据

**说明**：250 SPS 下 50 Hz 在带内（Nyquist 125 Hz），可直接看到；不要套用 ADS1256 10 SPS 的“50 Hz 不可见”经验。ADS1299 的数字滤波在 250 SPS 下不对 50 Hz 形成零点。

## T5 电极漂移（纯琼脂）

**接线**：两根铜箔电极插入 1.5% 琼脂（含少量 KCl），间距 10 mm；接 CH1 的 INP/INN（`diff`）；培养皿用 Parafilm 封边，暗盒内放湿纸巾。

**采集**：1 h，250 SPS。

```bash
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode diff \
    --duration 3600 --outdir data/bench_T5
```

**判据**：

- 漂移 **< 1 mV/h**
- 无饱和（不贴 ±8,388,607）
- 基线在 ±187.5 mV 内

**失败处理**：

- 漂移 > 1 mV/h：改用 3 M KCl + 琼脂盐桥（1 mL 枪头/细玻璃管，两端露出）；仍不行则换 Ag/AgCl 电极。
- 饱和：检查电极半电池电位；当前固件 gain 24 固定，不能用降增益掩盖。
- `diff` 配置默认开启内部 BIAS（P/N 均参与），为浮动样品提供共模回路；若 T5 显示偏置电流导致极化，需固件关闭 BIAS 后复测（当前无主机命令）。

## T6 时基与丢样审计 — PASS 2026-11-12

**做法**：250 SPS 连续记录 ≥ 10 min（`diff` 或 `short`）；记录开始/结束的主机时间；相机 1 帧/10 s 拍时钟卡。

**采集**：

```bash
python3 host/bcikit_openbci.py --port /dev/ttyUSB0 --mode short \
    --duration 600 --outdir data/bench_T6
```

**判据**：

- `sample_number` 按帧增量重建后单调
- 缺口率 **< 2%**（T1 基线 0.8%、T2 1.0%）
- `fs_effective = 样本跨度 / 主机时长` 记录在案（T1 246.8、T2 242.3，不要求等于 250）
- 样本时钟与主机时钟的差约等于缺口率（T1 0.8%、T2 1.0%），记录在案
- 主机时钟漂移记录在案；绝对频率按 `fs_effective` 换算

**实测（2026-11-12，600 s）**：149,144 帧；样本号跨度 149,395；缺口 65 次 / 252 样本 = **0.168%**（< 2% PASS）；零步进 0；最大步进 13；`fs_effective` **248.993 SPS**（样本钟）/ 248.574 SPS（主机钟），差 0.419 SPS = 0.168%，与缺口率一致；0.01–5 Hz 带内 RMS 0.05–0.51 µV；漂移 ≤ 1.0e-3 mV/h。证据 `data/bench_T6/` + `ANALYSIS.md`。

**已记录异常**：①启动时 `mode short` 首次读回失败（`CONFIG1 0x46 → 0x06`），固件重试后 `register_verified=yes`——11-11 的 GND/CLK 灵敏性再现；②缺口率随时间上升（每 100 s：0.048→0.028→0.016→0.104→0.277→**0.538%**，531 s 附近 10 连缺口），10 min 总判据仍 PASS，但属 48 h 风险，需 2 h soak 复核；③t≈526.4 s 八通道同时瞬变（ch1 ≈ 227 µV，~0.2 s，短接模式无电极 → 板/USB 事件）；④相机只取到两张锚点（20:07:45 / 20:14:30，time.is），未按 1 帧/10 s。

**2 h soak（2026-11-12）**：1,745,347 帧 / 7200 s；缺口 11,347 次 / 37,557 样本 = **2.107%**（整体超 2% → FAIL；稳态 40–120 min **1.57%**）；`fs_effective` 247.626 SPS / 主机 242.410 SPS，差 2.11% = 缺口率。设备侧计数（起止对比，证据 `data/bench_T6_soak2h/device_status_end.txt`）：drdy +1,782,787、frames +1,782,780、**transport_drop +0**、queue_overrun 0、spi_error 0 → **丢样发生在 ESP32 UART 之后的主机/USB/IP 路径，不是板子**。前 40 min 3.19%，之后 1.3–1.8%；最大缺口 182 样本（0.73 s）。下一步：Windows 侧 UART（绕开 usbipd）与 WiFi 原生帧对照。

**工具修正（2026-11-12）**：`bench_test.py` 的 `gap_fraction` 分母改为样本号跨度（原先 `seq_span + gap_samples` 把缺口重复计入分母，低估缺口率）。T6 600 s：0.168% → **0.1687%**（结论不变）；2 h soak：2.063% → **2.107%**（结论仍为 FAIL）。

**传输 A/B（2026-11-12）**：Windows 原生 COM6（pyserial 3.5，**主机在用**）30 min：445,637 帧，缺口 **14 样本 = 0.0031%**（全为单样本，max step 2），host 247.58 SPS；对比 usbipd soak 整体 2.107% / 稳态 1.566% → **丢样在 usbipd/WSL 路径**，板子与 ESP32 UART 输出无罪。注意：**打开 COM6 会触发 DTR/RTS 复位 ESP32**（起始计数全 0；结束后再开端口又复位，结束计数不可读）→ 记录器需补"结束 status"与开端口后 1–2 s 延时。证据 `data/bench_win_uart_30m/`。

**相机同步**：当前厂商固件没有主机可控的标记 GPIO；旧 ADS1256 的 GPIO32 LED 方案不适用。用启停事件 + 时钟卡，时间轴以样本号为准。若后续需要硬件标记，需改固件（未实现）。

**后续方案**：BCIKit 原生帧（WiFi TCP）带 32 位序号、64 位 DRDY 时间戳和 CRC-16，是 48 h 记录的候选；当前 UART 记录器只解析 OpenBCI 帧。

## 结果记录

每次测试保存：

```
data/bench_T?/
  raw.bin
  samples.csv
  meta.json
  bench_summary.json
  bench_plot.png
  SHA256SUMS
```

并在 `data/bench-log.md` 记录：日期、测试项、PASS/FAIL、异常、下一步。

## 失败排查

1. **完全无数据**：USB 是否为数据线；CP2102 是否枚举；usbipd 是否 attach；`/dev/ttyUSB0` 权限；波特率 115200。
2. **寄存器读回失败 / 测试信号缺失**：GND 与 CLK 是否拧线；5 V 是否稳定；ROLE 设置；必要时用 1 MHz SPI 补丁固件（已编译，未烧录）。
3. **噪声巨大**：USB 供电、地环路、电极线成天线、50 Hz；拔掉充电器再测；电极线双绞/屏蔽。
4. **饱和**：电极半电池电位超出 ±187.5 mV；换盐桥/AgCl，不要用增益调整掩盖。
5. **读数比例差 2 倍**：误用了 ADS1256 的 2.5 V 换算；本链路 LSB 为 22.35 nV/count（4.5 V / gain 24）。
6. **采样率不对 / 丢样多**：UART 只能 250 SPS；检查 USB 线和主机负载；用样本号而非主机时间。
7. **T2 占空比异常**：已知测试信号/固件属性；不影响增益标定，不作时基。
