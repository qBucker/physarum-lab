# physarum-lab / sim

阶段 0 的**可探测性数字孪生**：在买硬件之前，先回答“给定模型和噪声，能不能
看见结构–电活动耦合”。所有输出都是 **computed**，不是实验证据。

## 模块

| 文件 | 作用 |
|---|---|
| `instrument.py` | 电极/ADC 正向模型：源阻抗分压、半电池、线性漂移、1/f、热噪声、ADC 噪声、量化、工频 |
| `truth.py` | 最小物理真值：慢结构 OU + 电活动包络 + 正包络窄带振荡；驱动经 `tau_s` 低通 |
| `pipeline.py` | 带通/Hilbert 包络、互相关、相位随机化代理、周期折叠、块 bootstrap |
| `s0_detectability.py` | S0 主网格：rho × 闪烁噪声 × 时长 × 自发/驱动 |
| `s0_design_sweep.py` | 设计扫描：`tau_s` × 扰动周期 × rho |
| `instrument_budget.py` | 静态仪器预算（分压、噪声、漂移、PGA） |
| `r1_latent_recovery.py` | R1：潜空间管线回收测试（延迟嵌入 + DMDc/ARX + 代理），对照 S0 互相关检测器 |
| `e1_effective_complexity.py` | E1：有效复杂度校准（PR、CCA、非线性、平稳性、N_eff、BIC 阶梯）与真实数据协议 |
| `s1_network_testbed.py` | S1：高维/非线性网络测试床（平稳对数电导 TK、相机 POD、8–32 电极 lead-field、偏滞后线性/二次增益、匹配 FPR） |
| `s1b_direct_baseline.py` | S1b：直接非线性基线（原始电极 × 区域几何 + 同一二次库；2×2 分解；匹配 FPR） |

## 跑

```bash
cd physarum-lab/sim
python3 instrument_budget.py

# 全网格（约 5–6 min）
python3 s0_detectability.py --outdir results/s0_final \
    --n-sims 40 --n-surr 200 --drive-amp 2.0 --tau-s 2.0 --drive-period 2.0

# 自发 tau_s 扫描（约 2 min）
python3 s0_design_sweep.py --spontaneous-only \
    --tau-grid 0.5,1,2,4 --rho-grid 0.2,0.3 --duration-grid 24,48 \
    --n-sims 40 --n-surr 200 --outdir results/s0_design_spont

# 驱动设计扫描（约 3–4 min）
python3 s0_design_sweep.py --driven-only \
    --tau-grid 0.5,1,2 --period-grid 4,8 --rho-grid 0.1,0.2,0.3 \
    --duration-grid 48 --n-sims 60 --n-surr 200 --outdir results/s0_design_v4
```

## 读结果

先读 `results/S0-SUMMARY.md`。核心结论：

1. **ADC 不是瓶颈**；电极 1/f、输入阻抗、结构观测噪声才是。
2. **统计功效由独立结构状态数决定**：自发 48 h 在 `tau_s`=2 h 时只有
   ~12 个独立状态，rho=0.3 也只有 ~0.5 检出率。
3. **扰动周期 ≳ 4 × `tau_s`**；瞬时响应假设会给出错误的最优周期。
4. 驱动代理检验的块长必须长于包络相关时间、短于扰动周期；0.5 h 块在
   4 h 周期下假阳性 ~10%，已改用 1–2 h 块。

## R1（2026-11-14）

潜空间管线（延迟嵌入 + DMDc/ARX）在 S0 线性真值上的回收测试：现实耦合
（rho = 0.2/0.3）下无增益，只在近确定性耦合（rho ≈ 1）下工作；直接
max-|r| 互相关仍是正确检测器。结果 `results/r1_latent_recovery/`、
`results/r1_clean_control/`、`results/_r1_pilot_rho05_07/`；1 页笔记
`notes/physarum-r1-latent-method-2026-11-14.md`。

## E1（2026-11-14）

有效复杂度校准：POD 参与率 PR 回收已知总维数；非线性检验 0.55 功效、0 假阳性；
平稳性检验对 0→0.6 的强变化只有 0.40 功效；单电极 CCA 秩保守（K=8 只识别 3 个
耦合模态）；BIC 选 q=1 是过采样伪影，不能给物理滞后。结论：先测有效复杂度，
再按 L1–L5 阶梯加复杂度；每加一个参数必须买到预注册的样本外/干预增益。
结果 `results/e1_effective_complexity/`；笔记
`notes/physarum-e1-effective-complexity-2026-11-14.md`；方法与工具 PDF
`docs/modeling-methods-tools-2026-11-14.pdf`。

## S1 / S1b（2026-11-14）

高维/非线性测试床：平稳对数电导 TK（12 节点、约 24 边）→ 24×20 相机图像 + POD → 16 电极 lead-field → 0.03 Hz 载波与仪器噪声。预注册 `rho={0,0.5,0.7,0.9}` × `{linear, quadratic}` × 30 次；检测器 = D1/D2（扫描/固定滞后）、S1-L1（偏滞后线性增益）、S1-L2（偏滞后二次增益）；全样本 R² 由共同相位代理校准，匹配 FPR。

S1 结果（对直接线性）：rho=0.9 二次格 D1/D2 = 4/30、7/30，S1-L1/S1-L2 = 19/30、23/30；S1-L2 线性格 0/30（特异）；FPR 1/60；匹配阈值后 L2 = 0.867 vs D2 = 0.567；K=8/32 次网格同向。**（仅对直接线性检测器）非线性潜层有增益；R1 的线性结论不变。**

S1b 直接非线性基线（同日）：DQ-A = 16 原始电极 × 8 区域几何均值（4×2）+ 同一二次库/估计器；DQ-C/D 分解电极 PCA 与几何 POD。rho=0.9 二次格：DQ-A 28/30（0.933；匹配 0.967），S1-L2 23/30（0.767；0.867）；DQ-C 0.900、DQ-D 0.900；四个检测器线性格全 0；FPR DQ-A 0/60；S1 参考 p 差 0.0（120/120）。**裁决：QUADRATIC FEATURES EXPLAIN THE GAIN——增益来自二次滞后特征，POD/PCA 潜层表示无独立优势；主非线性检测器改为直接二次滞后模型。** 证据 `results/s1_network/`、`results/s1b_direct_baseline/`。

```bash
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    python3 s1_network_testbed.py --grid all --outdir results/s1_network
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 \
    python3 s1b_direct_baseline.py --grid all --outdir results/s1b_direct_baseline
```

## 纪律

- 网格/种子/判据在脚本里预注册；改网格要另开输出目录。
- 旧结果不删，移入 `results/_superseded_*/` 并写 README。
- 仪器参数在 T1–T6 前全部标 `assumed`；台架后回填 `measured`。
- 这里的 `rho` 是模型参数，不是生物学测量；S0 不能替代四类对照。
