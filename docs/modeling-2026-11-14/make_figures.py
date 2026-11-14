#!/usr/bin/env python3
"""Figures for the 2026-11-14 modeling methods/tools PDF."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

BASE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FONT = FontProperties(fname="/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")

# Validated categorical slots (light surface) from the dataviz reference palette.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
VIOLET = "#7c3aed"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#d9d8d4"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "text.color": INK,
    "axes.unicode_minus": False,
    "font.size": 10,
})


def r1_figure():
    r1 = json.load(open(BASE / "sim/results/r1_latent_recovery/r1_results.json"))["summary"]
    post = json.load(open(BASE / "sim/results/_r1_pilot_rho05_07/r1_results.json"))["summary"]
    rhos_main = [0.0, 0.2, 0.3]
    rhos_post = [0.5, 0.7]
    latent_main = [r1[str(r)]["latent_power"] for r in rhos_main]
    base_main = [r1[str(r)]["baseline_power"] for r in rhos_main]
    rev_main = [r1[str(r)]["latent_reverse_power"] for r in rhos_main]
    latent_post = [post[str(r)]["latent_power"] for r in rhos_post]
    base_post = [post[str(r)]["baseline_power"] for r in rhos_post]
    rev_post = [post[str(r)]["latent_reverse_power"] for r in rhos_post]

    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
    ax.plot(rhos_main, latent_main, "o-", color=BLUE, lw=2, ms=8, label="潜空间（前向）")
    ax.plot(rhos_main, base_main, "s-", color=ORANGE, lw=2, ms=8, label="基线互相关")
    ax.plot(rhos_main, rev_main, "^:", color=AQUA, lw=2, ms=8, label="潜空间（反向）")
    ax.plot(rhos_post, latent_post, "o--", color=BLUE, lw=1.5, ms=8, mfc="white", mew=2)
    ax.plot(rhos_post, base_post, "s--", color=ORANGE, lw=1.5, ms=8, mfc="white", mew=2)
    ax.plot(rhos_post, rev_post, "^--", color=AQUA, lw=1.5, ms=8, mfc="white", mew=2)
    ax.axvline(0.4, color=GRID, lw=1, ls=(0, (4, 3)))
    ax.text(0.42, 0.93, "后验扫描\n10 次/格", color=MUTED, fontproperties=FONT, fontsize=8, va="top")
    ax.text(0.02, 0.20, "主网格 30 次/格", color=MUTED, fontproperties=FONT, fontsize=8)
    ax.annotate("11/30", (0.3, base_main[2]), xytext=(0.245, 0.48),
                color=ORANGE, fontproperties=FONT, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=ORANGE, lw=1))
    ax.annotate("2/30", (0.3, latent_main[2]), xytext=(0.31, 0.13),
                color=BLUE, fontproperties=FONT, fontsize=9)
    ax.annotate("10/10", (0.7, base_post[1]), xytext=(0.56, 1.02),
                color=ORANGE, fontproperties=FONT, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=ORANGE, lw=1))
    ax.annotate("5/10", (0.7, latent_post[1]), xytext=(0.585, 0.62),
                color=BLUE, fontproperties=FONT, fontsize=9,
                arrowprops=dict(arrowstyle="-", color=BLUE, lw=1))
    ax.set_xlabel("耦合强度 ρ（模型参数）", fontproperties=FONT)
    ax.set_ylabel("检出率（p < 0.05）", fontproperties=FONT)
    ax.set_xlim(-0.03, 0.78)
    ax.set_ylim(-0.03, 1.08)
    ax.grid(alpha=0.25, color=GRID)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(prop=FONT, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=3, fontsize=9)
    ax.set_title("R1：潜空间预测模型只在近确定性耦合下工作", fontproperties=FONT, fontsize=11, loc="left")
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.28)
    fig.savefig(OUT / "fig_r1.png")
    plt.close(fig)


def e1_figure():
    e1 = json.load(open(BASE / "sim/results/e1_effective_complexity/e1_results.json"))["summary"]
    labels = {"s0": "s0", "kmode2": "K=2", "kmode4": "K=4", "kmode8": "K=8",
              "nonlinear": "非线性", "nonstationary": "非平稳"}
    systems = ["s0", "kmode2", "kmode4", "kmode8", "nonlinear", "nonstationary"]
    x = [e1[s]["known_rank"] for s in systems]
    y = [e1[s]["pr"] for s in systems]

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.9), dpi=200)
    ax = axes[0]
    ax.plot([0, 10], [0, 10], "--", color=GRID, lw=1.5, label="恒等线")
    ax.scatter(x, y, s=70, color=BLUE, zorder=3, edgecolor="white", linewidth=1.5)
    offsets = {"kmode2": (0.15, 0.25), "kmode4": (0.15, 0.25), "kmode8": (-0.45, 0.55)}
    for s, xi, yi in zip(systems, x, y):
        if s not in offsets:
            continue
        dx, dy = offsets[s]
        ax.text(xi + dx, yi + dy, labels[s], color=MUTED, fontproperties=FONT, fontsize=9)
    ax.text(2.15, 1.35, "s0 / 非线性 / 非平稳\n（三点重合）", color=MUTED,
            fontproperties=FONT, fontsize=9, va="top")
    ax.set_xlabel("已知有效维数（结构模态 + 电噪声）", fontproperties=FONT)
    ax.set_ylabel("POD 参与率 PR", fontproperties=FONT)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.grid(alpha=0.25, color=GRID)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.set_title("PR 回收已知维数", fontproperties=FONT, fontsize=10, loc="left")

    ax = axes[1]
    cats = ["s0", "非线性", "非平稳"]
    lin_pow = [e1[s]["nonlinearity_power"] or 0.0 for s in ["s0", "nonlinear", "nonstationary"]]
    drift_pow = [e1[s]["drift_power"] or 0.0 for s in ["s0", "nonlinear", "nonstationary"]]
    xx = range(len(cats))
    w = 0.34
    b1 = ax.bar([i - w / 2 for i in xx], lin_pow, w, color=BLUE, label="非线性检验")
    b2 = ax.bar([i + w / 2 for i in xx], drift_pow, w, color=ORANGE, label="平稳性检验")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                    f"{b.get_height():.2f}", ha="center", va="bottom",
                    color=MUTED, fontproperties=FONT, fontsize=8)
    ax.set_xticks(list(xx))
    ax.set_xticklabels(cats, fontproperties=FONT)
    ax.set_ylabel("检验功效（p < 0.05 比例）", fontproperties=FONT)
    ax.set_ylim(0, 0.7)
    ax.grid(alpha=0.25, color=GRID, axis="y")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(prop=FONT, frameon=False, fontsize=9)
    ax.set_title("检验功效（20 次/系统）", fontproperties=FONT, fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_e1.png")
    plt.close(fig)


def s1_figure():
    s1 = json.load(open(BASE / "sim/results/s1_network/s1_results.json"))["primary"]["summary"]
    rhos = [0.0, 0.5, 0.7, 0.9]
    specs = [
        ("d1", "D1 直接标量", ORANGE, "s", "--"),
        ("d2", "D2 直接 CCA", AQUA, "^", ":"),
        ("l1", "S1-L1 潜层线性", BLUE, "o", "-"),
        ("l2", "S1-L2 潜层二次", VIOLET, "d", "-"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.5), dpi=200, sharey=True)
    for ax, coupling, title in ((axes[0], "linear", "线性耦合"),
                                (axes[1], "quadratic", "二次耦合")):
        for det, label, color, marker, ls in specs:
            ys = [s1[f"{coupling}|{r:.1f}"][det]["power"] for r in rhos]
            ax.plot(rhos, ys, marker=marker, ls=ls, color=color, lw=2, ms=6,
                    label=label)
        ax.set_xlabel("耦合强度 ρ（模型参数）", fontproperties=FONT)
        ax.set_xlim(-0.03, 0.93)
        ax.set_ylim(-0.03, 1.03)
        ax.grid(alpha=0.25, color=GRID)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.set_title(title, fontproperties=FONT, fontsize=10, loc="left")
    axes[0].set_ylabel("检出率（p < 0.05）", fontproperties=FONT)
    axes[1].annotate("L2 23/30", (0.9, 0.767), xytext=(0.60, 0.88),
                     color=VIOLET, fontproperties=FONT, fontsize=9,
                     arrowprops=dict(arrowstyle="-", color=VIOLET, lw=1))
    axes[1].annotate("D2 7/30", (0.9, 0.233), xytext=(0.62, 0.14),
                     color=AQUA, fontproperties=FONT, fontsize=9,
                     arrowprops=dict(arrowstyle="-", color=AQUA, lw=1))
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, frameon=False, prop=FONT, fontsize=8,
               loc="lower center", bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(OUT / "fig_s1.png", bbox_inches="tight")
    plt.close(fig)


def s1b_figure():
    data = json.load(open(
        BASE / "sim/results/s1b_direct_baseline/s1b_results.json"))
    summary = data["primary"]["summary"]
    specs = [
        ("s1l2", "S1-L2\nPC+POD", VIOLET),
        ("dqa", "DQ-A\nraw+region", ORANGE),
        ("dqc", "DQ-C\nraw+POD", BLUE),
        ("dqd", "DQ-D\nPC+region", AQUA),
    ]
    x = range(len(specs))
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.5), dpi=200, sharey=True)
    for ax, key, title in ((axes[0], "quadratic|0.9", "二次格（主检验）"),
                           (axes[1], "linear|0.9", "线性格（特异性）")):
        ys = [summary[key][det]["power"] for det, _, _ in specs]
        ax.bar(x, ys, color=[c for _, _, c in specs], width=0.65)
        for xi, y in zip(x, ys):
            ax.text(xi, y + 0.03, f"{y:.2f}", ha="center", va="bottom",
                    color=MUTED, fontproperties=FONT, fontsize=8)
        ax.set_xticks(list(x))
        ax.set_xticklabels([label for _, label, _ in specs], fontsize=8)
        ax.set_ylim(0, 1.1)
        ax.set_title(title, fontproperties=FONT, fontsize=10, loc="left")
        ax.grid(alpha=0.25, color=GRID, axis="y")
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0].set_ylabel("检出率（p < 0.05）", fontproperties=FONT)
    fig.tight_layout()
    fig.savefig(OUT / "fig_s1b.png")
    plt.close(fig)


if __name__ == "__main__":
    r1_figure()
    e1_figure()
    s1_figure()
    s1b_figure()
    print("wrote", OUT / "fig_r1.png", OUT / "fig_e1.png", OUT / "fig_s1.png",
          OUT / "fig_s1b.png")
