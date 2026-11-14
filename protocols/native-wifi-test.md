# N1 — 原生帧 WiFi 链路验证（48 h 传输候选）

> 目的：在上板实测中验证 `host/bcikit_native.py` 的完整链路——WiFi 会话、命令 ACK、55 B 原生帧、32 位序号、64 位 DRDY 时间戳、CRC。
> 这不是 T1–T6 模拟链门禁的一部分；它是 48 h 记录的**传输层**验证。
> 通过标准：序号缺口 < 2%、CRC 错误 0、`TIME_VALID` 覆盖几乎全部帧、设备速率 240–255 SPS。

## 0. 前置条件

- UART soak 已结束（`host/bcikit_openbci.py` 不再运行，`/dev/ttyUSB0` 空闲；板子已发 `s`/`stop`）。
- **Studio 已关闭或 BLE 已断开**（否则设备以 `BUSY` 拒绝 WiFi 会话）。
- Windows 侧有 Python：本机 `D:\phy\python.exe`（3.14）。
- 接收器脚本：`host/bcikit_native.py`（纯标准库）；Windows 启动器 `host/run_native_windows.bat`。

## 1. 网络与防火墙（一次性）

1. Windows 连接 WiFi **`OpenBCI-0D2D`**（开放网络，无密码）。
2. `ipconfig` 确认无线网卡拿到 **192.168.4.x**。
3. 把该网络配置为**专用网络**（设置 → 网络和 Internet → 属性 → 专用），否则 Windows 按"公用"拦截入站。
4. （管理员 PowerShell，一次性）放行监听端口：
   ```powershell
   netsh advfirewall firewall add rule name="BCIKit native" dir=in action=allow protocol=TCP localport=12345 profile=any
   ```
5. 建议：手机 USB 共享网络给笔记本，保持互联网（Windows 会把无 Internet 的 AP 判为低优先级，默认路由走 USB）。

> 注意：连上板子 AP 后，若没有 USB 共享/有线网络，这个 Claude 会话会断；接收器在 Windows 侧继续运行，跑完切回家里 WiFi 再分析。

## 2. 运行（10 分钟首测）

在 Windows 的普通 cmd（不要管理员）里：

```bat
\\wsl.localhost\Ubuntu\path\to\physarum-lab\host\run_native_windows.bat D:\physarum-data\native_N1_test --duration 600 --profile short --rate 250
```

首次监听时如果弹出防火墙提示，勾选**专用网络**并允许。

预期输出顺序：

```
listening on 0.0.0.0:12345; advertising 192.168.4.x
POST /tcp -> 200 {"connected":true,...}
device connected from 192.168.4.1:xxxxx
started: 0.7.16, boards=1, rate=250, profile=short
t= 10.0s frames=... host=... sps dev=... gaps=... crc=0
...
wrote D:\physarum-data\native_N1_test
```

## 3. 判据

| 项 | 判据 | 依据 |
|---|---|---|
| 会话建立 | `POST /tcp` 200 且 `connected:true` | 命令输出 |
| 设备信息 | firmware `0.7.16`，capabilities 含 raw/control 位 | `meta.json` |
| 命令 | 全部 `status=0`（Stop/SetOutput/SetBoards/SetRate/SetProfile/SetMask/GetInfo/GetStatus/Start） | `meta.json` commands |
| CRC | **0 错误** | `meta.json` statistics |
| 时序 | 帧 flag `TIME_VALID` 置位（`frames_time_invalid` ≈ 0） | `meta.json` |
| 缺口 | `gap_fraction` < **2%**（目标接近 UART T6 的 0.17%） | `meta.json` |
| 速率 | `device_rate_sps` 240–255 | `meta.json` |
| 落盘 | `raw_frames.bin` 大小 ≈ 55 B × frames；CSV 行数 = frames | 文件检查 |
| 审计 | `SHA256SUMS` 三件套校验 OK | `sha256sum -c` |

## 4. 失败排查

| 现象 | 原因 | 处置 |
|---|---|---|
| `POST /tcp -> 409 BUSY` | Studio/BLE 会话仍占用 | 关闭 Studio 或断开 BLE |
| `POST /tcp -> 504` | 设备连不到监听端口 | 检查 advertise IP、AP 网络是否为专用、防火墙规则 |
| 没有 `device connected` | 监听没被设备回连 | 同上；确认 192.168.4.x |
| 连上但命令超时 | 会话协议不匹配 | 确认输出 `bcikit`、固件 0.7.16 |
| `TIME_VALID` 大面积缺失 | 设备时间戳未就绪 | 记录 flag 直方图；若持续，退回 UART |
| 缺口 > 2% | WiFi/TCP 拥塞 | 记录；对比 2 h soak 是否饱和 |

## 5. 测后

1. 把 `D:\physarum-data\native_N1_test` 拷到 `physarum-lab/data/bench_N1_test/`。
2. `sha256sum -c SHA256SUMS` 校验。
3. 若改走 2 h：`--duration 7200 --outdir D:\physarum-data\native_N1_2h`。
4. 结果与 UART T6 对比后，再决定 48 h 走原生帧还是 UART。
