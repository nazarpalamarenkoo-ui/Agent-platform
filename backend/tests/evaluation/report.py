import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.axes import Axes
import numpy as np

from tests.evaluation.models import BenchmarkResult, ModeResult, AgenticModeResult

REPORTS_DIR = Path(__file__).parent / "reports"


def print_report(result: BenchmarkResult) -> None:
    print("\n" + "=" * 52)
    print(f"  Benchmark Report  |  mode: {result.meta.mode.upper()}")
    print("=" * 52)
    print(f"  Dataset : {result.meta.dataset_size} queries")
    print(f"  Run at  : {result.meta.timestamp}")
    print()

    if result.hybrid:
        _print_mode("Hybrid Retrieval", result.hybrid)

    if result.agentic:
        _print_mode("Agentic RAG", result.agentic)
        print(f"  {'Avg iterations':<20} {result.agentic.avg_iterations:.2f}")
        print(f"  {'Degraded to hybrid':<20} {result.agentic.degraded_to_hybrid_pct * 100:.1f}%")
        print(f"  {'Avg coverage':<20} {result.agentic.avg_coverage:.2f}")
        print(f"  {'Avg confidence':<20} {result.agentic.avg_confidence:.2f}")

    if result.delta:
        print()
        print("  Delta (agentic − hybrid)")
        print(f"  {'Recall@5':<20} {result.delta.recall_at_5:+.4f}")
        print(f"  {'Recall@10':<20} {result.delta.recall_at_10:+.4f}")
        print(f"  {'MRR':<20} {result.delta.mrr:+.4f}")
        print(f"  {'nDCG@10':<20} {result.delta.ndcg_at_10:+.4f}")

    print("=" * 52)


def _print_mode(label: str, r: ModeResult) -> None:
    print(f"  [{label}]")
    print(f"  {'Recall@5':<20} {r.recall_at_5:.4f}")
    print(f"  {'Recall@10':<20} {r.recall_at_10:.4f}")
    print(f"  {'MRR':<20} {r.mrr:.4f}")
    print(f"  {'nDCG@10':<20} {r.ndcg_at_10:.4f}")
    print()


def save_report(result: BenchmarkResult) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = result.meta.timestamp.replace(":", "").replace(" ", "_")
    path = REPORTS_DIR / f"benchmark_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path



def save_charts(result: BenchmarkResult) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = result.meta.timestamp.replace(":", "").replace(" ", "_")
    path = REPORTS_DIR / f"benchmark_{timestamp}_charts.png"

    mode = result.meta.mode
    has_both = mode == "both"
    has_agentic = result.agentic is not None
    has_hybrid = result.hybrid is not None

    n_rows = 1
    if has_both:
        n_rows = 3
    elif has_agentic and result.per_query:
        n_rows = 2

    fig = plt.figure(figsize=(14, 5 * n_rows))
    fig.patch.set_facecolor("#1e1e2e")
    gs = gridspec.GridSpec(n_rows, 2, figure=fig, hspace=0.45, wspace=0.35)

    metric_labels = ["Recall@5", "Recall@10", "MRR", "nDCG@10"]
    metric_keys = ["recall_at_5", "recall_at_10", "mrr", "ndcg_at_10"]

    ax0 = fig.add_subplot(gs[0, :])
    _style_ax(ax0)
    x = np.arange(len(metric_labels))
    bar_width = 0.35

    if has_both and has_hybrid and has_agentic:
        hybrid_vals = [getattr(result.hybrid, k) for k in metric_keys]
        agentic_vals = [getattr(result.agentic, k) for k in metric_keys]
        bars_h = ax0.bar(x - bar_width / 2, hybrid_vals, bar_width,
                         label="Hybrid", color="#89b4fa", alpha=0.9)
        bars_a = ax0.bar(x + bar_width / 2, agentic_vals, bar_width,
                         label="Agentic", color="#a6e3a1", alpha=0.9)
        _label_bars(ax0, bars_h)
        _label_bars(ax0, bars_a)
        ax0.legend(facecolor="#313244", labelcolor="white", fontsize=10)
    elif has_hybrid:
        hybrid_vals = [getattr(result.hybrid, k) for k in metric_keys]
        bars = ax0.bar(x, hybrid_vals, bar_width * 1.5, color="#89b4fa", alpha=0.9)
        _label_bars(ax0, bars)
    elif has_agentic:
        agentic_vals = [getattr(result.agentic, k) for k in metric_keys]
        bars = ax0.bar(x, agentic_vals, bar_width * 1.5, color="#a6e3a1", alpha=0.9)
        _label_bars(ax0, bars)

    ax0.set_xticks(x)
    ax0.set_xticklabels(metric_labels, color="white", fontsize=11)
    ax0.set_ylim(0, 1.15)
    ax0.set_title("Retrieval Metrics Comparison", color="white", fontsize=13, pad=10)
    ax0.set_ylabel("Score", color="#cdd6f4")

    if has_both and n_rows >= 2 and result.per_query:
        ax1_l = fig.add_subplot(gs[1, 0])
        ax1_r = fig.add_subplot(gs[1, 1])
        _style_ax(ax1_l)
        _style_ax(ax1_r)

        h_recalls = [q.hybrid_recall_at_10 for q in result.per_query
                     if q.hybrid_recall_at_10 is not None]
        a_recalls = [q.agentic_recall_at_10 for q in result.per_query
                     if q.agentic_recall_at_10 is not None]

        ax1_l.hist(h_recalls, bins=15, color="#89b4fa", alpha=0.85, edgecolor="#1e1e2e")
        ax1_l.set_title("Hybrid — Recall@10 Distribution", color="white", fontsize=11)
        ax1_l.set_xlabel("Recall@10", color="#cdd6f4")
        ax1_l.set_ylabel("# Queries", color="#cdd6f4")

        ax1_r.hist(a_recalls, bins=15, color="#a6e3a1", alpha=0.85, edgecolor="#1e1e2e")
        ax1_r.set_title("Agentic — Recall@10 Distribution", color="white", fontsize=11)
        ax1_r.set_xlabel("Recall@10", color="#cdd6f4")
        ax1_r.set_ylabel("# Queries", color="#cdd6f4")

    if has_both and n_rows >= 3 and result.per_query:
        ax2_l = fig.add_subplot(gs[2, 0])
        ax2_r = fig.add_subplot(gs[2, 1])
        _style_ax(ax2_l)
        _style_ax(ax2_r)

        iters = [q.agentic_iterations for q in result.per_query
                 if q.agentic_iterations is not None]
        a_recalls = [q.agentic_recall_at_10 for q in result.per_query
                     if q.agentic_recall_at_10 is not None and q.agentic_iterations is not None]

        ax2_l.scatter(iters, a_recalls, color="#cba6f7", alpha=0.65, s=40)
        ax2_l.set_title("Agentic — Iterations vs Recall@10", color="white", fontsize=11)
        ax2_l.set_xlabel("Iterations", color="#cdd6f4")
        ax2_l.set_ylabel("Recall@10", color="#cdd6f4")
        ax2_l.set_ylim(-0.05, 1.1)

        h_r = [q.hybrid_recall_at_10 for q in result.per_query
               if q.hybrid_recall_at_10 is not None and q.agentic_recall_at_10 is not None]
        a_r = [q.agentic_recall_at_10 for q in result.per_query
               if q.hybrid_recall_at_10 is not None and q.agentic_recall_at_10 is not None]

        ax2_r.scatter(h_r, a_r, color="#fab387", alpha=0.65, s=40)
        lims = [0, 1.05]
        ax2_r.plot(lims, lims, "--", color="#6c7086", linewidth=1)
        ax2_r.set_title("Hybrid vs Agentic Recall@10 per Query", color="white", fontsize=11)
        ax2_r.set_xlabel("Hybrid Recall@10", color="#cdd6f4")
        ax2_r.set_ylabel("Agentic Recall@10", color="#cdd6f4")
        ax2_r.set_xlim(*lims)
        ax2_r.set_ylim(*lims)
        
    if not has_both and has_agentic and n_rows >= 2 and result.per_query:
        ax1_l = fig.add_subplot(gs[1, 0])
        ax1_r = fig.add_subplot(gs[1, 1])
        _style_ax(ax1_l)
        _style_ax(ax1_r)

        a_recalls = [q.agentic_recall_at_10 for q in result.per_query
                     if q.agentic_recall_at_10 is not None]
        iters = [q.agentic_iterations for q in result.per_query
                 if q.agentic_iterations is not None]

        ax1_l.hist(a_recalls, bins=15, color="#a6e3a1", alpha=0.85, edgecolor="#1e1e2e")
        ax1_l.set_title("Agentic — Recall@10 Distribution", color="white", fontsize=11)
        ax1_l.set_xlabel("Recall@10", color="#cdd6f4")
        ax1_l.set_ylabel("# Queries", color="#cdd6f4")

        a_r2 = [q.agentic_recall_at_10 for q in result.per_query
                if q.agentic_iterations is not None and q.agentic_recall_at_10 is not None]
        ax1_r.scatter(iters, a_r2, color="#cba6f7", alpha=0.65, s=40)
        ax1_r.set_title("Iterations vs Recall@10", color="white", fontsize=11)
        ax1_r.set_xlabel("Iterations", color="#cdd6f4")
        ax1_r.set_ylabel("Recall@10", color="#cdd6f4")

    fig.suptitle(
        f"Benchmark  |  {result.meta.timestamp}  |  {result.meta.dataset_size} queries",
        color="#cdd6f4", fontsize=12, y=0.98,
    )
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def _style_ax(ax: Axes) -> None:
    ax.set_facecolor("#313244")
    ax.tick_params(colors="#cdd6f4")
    ax.spines[:].set_color("#45475a")
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color("#cdd6f4")


def _label_bars(ax: Axes, bars) -> None:
    for bar in bars:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + 0.01,
            f"{h:.3f}",
            ha="center", va="bottom",
            color="white", fontsize=8,
        )