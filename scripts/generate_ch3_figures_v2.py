#!/usr/bin/env python3
"""Generate Chapter 3 figures with real experimental data."""
import json
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

# Font config for Chinese
rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False
rcParams['figure.dpi'] = 300

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'figures', 'ch3')
os.makedirs(OUT_DIR, exist_ok=True)

# === PrimeVul depth distribution data ===
PRIMEVUL_DIST = {1: 4057, 2: 489, 3: 135, 4: 50, 5: 13, 6: 16, 7: 6, 8: 2, 10: 1, 11: 1, 12: 2, 13: 1, 14: 3, 25: 1}
PRIMEVUL_TOTAL = sum(PRIMEVUL_DIST.values())


def fig3_1_depth_distribution():
    """PrimeVul原始调用链深度分布 vs SliceFusion扩展."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Left: PrimeVul original
    labels = ['1', '2', '3', '4', '≥5']
    orig_counts = [4057, 489, 135, 50, sum(v for k, v in PRIMEVUL_DIST.items() if k >= 5)]
    orig_pcts = [c / PRIMEVUL_TOTAL * 100 for c in orig_counts]
    
    colors_orig = ['#4472C4', '#4472C4', '#ED7D31', '#ED7D31', '#ED7D31']
    bars1 = ax1.bar(labels, orig_pcts, color=colors_orig, edgecolor='white', width=0.6)
    ax1.set_xlabel('调用链深度', fontsize=12)
    ax1.set_ylabel('样本占比 (%)', fontsize=12)
    ax1.set_title('PrimeVul 原始分布', fontsize=13, fontweight='bold')
    ax1.set_ylim(0, 100)
    for bar, pct in zip(bars1, orig_pcts):
        if pct > 3:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{pct:.1f}%', ha='center', va='bottom', fontsize=10)
    
    # Annotation: highlight the problem
    ax1.annotate('84.9% 集中在\n单函数层级', xy=(0, 84.9), xytext=(2.5, 75),
                fontsize=10, color='red', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
    
    # Right: SliceFusion augmented (our dataset)
    # We generate equal samples per depth
    aug_labels = ['2', '3', '4', '≥5']
    aug_counts = [50, 50, 50, 46]  # our experiment counts
    aug_pcts = [c / sum(aug_counts) * 100 for c in aug_counts]
    
    colors_aug = ['#70AD47', '#70AD47', '#70AD47', '#70AD47']
    bars2 = ax2.bar(aug_labels, aug_pcts, color=colors_aug, edgecolor='white', width=0.6)
    ax2.set_xlabel('调用链深度', fontsize=12)
    ax2.set_ylabel('样本占比 (%)', fontsize=12)
    ax2.set_title('SliceFusion 扩展分布', fontsize=13, fontweight='bold')
    ax2.set_ylim(0, 40)
    for bar, pct in zip(bars2, aug_pcts):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{pct:.1f}%', ha='center', va='bottom', fontsize=10)
    
    ax2.annotate('均匀覆盖\n各深度层级', xy=(1.5, 28), xytext=(1.5, 35),
                fontsize=10, color='#2E7D32', fontweight='bold',
                ha='center')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig3_1_depth_distribution.png'), bbox_inches='tight')
    plt.savefig(os.path.join(OUT_DIR, 'fig3_1_depth_distribution.pdf'), bbox_inches='tight')
    plt.close()
    print("✓ fig3_1_depth_distribution")


def fig3_2_fusion_by_depth():
    """Fusion success rate and verification rate by depth and method."""
    EXP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'ch3_experiments')
    
    depths = [2, 3, 4, 5]
    global_verify = []
    param_verify = []
    global_time = []
    param_time = []
    
    for d in depths:
        for method, arr_v, arr_t in [('global', global_verify, global_time), ('param', param_verify, param_time)]:
            f = os.path.join(EXP_DIR, f'depth_{d}_{method}.json')
            if os.path.exists(f):
                data = json.load(open(f))
                m = data['metadata']
                arr_v.append(float(m['verification_rate'].replace('%', '')))
                arr_t.append(float(m['avg_elapsed'].replace('s', '')))
            else:
                arr_v.append(0)
                arr_t.append(0)
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    x = np.arange(len(depths))
    w = 0.35
    
    # Verification rate
    bars1 = ax1.bar(x - w/2, global_verify, w, label='全局变量法', color='#4472C4', edgecolor='white')
    bars2 = ax1.bar(x + w/2, param_verify, w, label='参数传递法', color='#ED7D31', edgecolor='white')
    ax1.set_xlabel('调用链深度', fontsize=12)
    ax1.set_ylabel('语法验证通过率 (%)', fontsize=12)
    ax1.set_title('不同深度下的验证通过率', fontsize=13, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(['2', '3', '4', '≥5'])
    ax1.legend()
    ax1.set_ylim(0, 110)
    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax1.text(bar.get_x() + bar.get_width()/2, h + 1, f'{h:.0f}%',
                        ha='center', va='bottom', fontsize=9)
    
    # Average time
    ax2.plot(depths, global_time, 'o-', color='#4472C4', label='全局变量法', linewidth=2, markersize=8)
    ax2.plot(depths, param_time, 's-', color='#ED7D31', label='参数传递法', linewidth=2, markersize=8)
    ax2.set_xlabel('调用链深度', fontsize=12)
    ax2.set_ylabel('平均融合耗时 (s)', fontsize=12)
    ax2.set_title('不同深度下的融合耗时', fontsize=13, fontweight='bold')
    ax2.set_xticks(depths)
    ax2.set_xticklabels(['2', '3', '4', '≥5'])
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig3_2_fusion_by_depth.png'), bbox_inches='tight')
    plt.savefig(os.path.join(OUT_DIR, 'fig3_2_fusion_by_depth.pdf'), bbox_inches='tight')
    plt.close()
    print("✓ fig3_2_fusion_by_depth")


def fig3_3_vuln_types():
    """Fusion results by vulnerability type."""
    EXP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'ch3_experiments')
    
    vuln_types = {
        'format_string': 'CWE-134\n格式化字符串',
        'buffer_overflow': 'CWE-120\n缓冲区溢出',
        'integer_overflow': 'CWE-190\n整数溢出',
        'use_after_free': 'CWE-416\n释放后使用',
        'null_deref': 'CWE-476\n空指针解引用',
    }
    
    labels = []
    success_rates = []
    verify_rates = []
    avg_times = []
    
    for key, label in vuln_types.items():
        f = os.path.join(EXP_DIR, f'vuln_{key}.json')
        if os.path.exists(f):
            data = json.load(open(f))
            m = data['metadata']
            labels.append(label)
            success_rates.append(float(m['success_rate'].replace('%', '')))
            verify_rates.append(float(m['verification_rate'].replace('%', '')))
            avg_times.append(float(m['avg_elapsed'].replace('s', '')))
    
    if not labels:
        print("✗ fig3_3: no vuln data yet")
        return
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    x = np.arange(len(labels))
    w = 0.35
    
    bars1 = ax.bar(x - w/2, success_rates, w, label='融合成功率', color='#4472C4', edgecolor='white')
    bars2 = ax.bar(x + w/2, verify_rates, w, label='语法验证通过率', color='#70AD47', edgecolor='white')
    
    ax.set_xlabel('漏洞类型', fontsize=12)
    ax.set_ylabel('比率 (%)', fontsize=12)
    ax.set_title('不同漏洞类型的融合效果', fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend(loc='lower right')
    ax.set_ylim(0, 115)
    
    for bars in [bars1, bars2]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 1, f'{h:.0f}%',
                    ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig3_3_vuln_types.png'), bbox_inches='tight')
    plt.savefig(os.path.join(OUT_DIR, 'fig3_3_vuln_types.pdf'), bbox_inches='tight')
    plt.close()
    print("✓ fig3_3_vuln_types")


def fig3_4_dispersion():
    """Analyze injection dispersion — how many functions got modified."""
    EXP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'ch3_experiments')
    
    # Collect injected_functions from depth experiments
    depth_data = {}
    for d in [2, 3, 4, 5]:
        f = os.path.join(EXP_DIR, f'depth_{d}_global.json')
        if os.path.exists(f):
            data = json.load(open(f))
            injected = [r.get('injected_functions', 0) for r in data['results'] if r['success']]
            depth_data[d] = injected
    
    if not depth_data:
        print("✗ fig3_4: no data with injected_functions")
        return
    
    fig, ax = plt.subplots(figsize=(8, 5))
    
    positions = list(depth_data.keys())
    bp_data = [depth_data[d] for d in positions]
    
    bp = ax.boxplot(bp_data, positions=range(len(positions)), patch_artist=True,
                    boxprops=dict(facecolor='#4472C4', alpha=0.7),
                    medianprops=dict(color='red', linewidth=2))
    
    ax.set_xlabel('调用链深度', fontsize=12)
    ax.set_ylabel('被注入的函数数量', fontsize=12)
    ax.set_title('漏洞片段分散度分析', fontsize=13, fontweight='bold')
    ax.set_xticks(range(len(positions)))
    ax.set_xticklabels([str(d) if d < 5 else '≥5' for d in positions])
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add mean annotations
    for i, d in enumerate(positions):
        vals = depth_data[d]
        if vals:
            mean_v = np.mean(vals)
            ax.text(i, max(vals) + 0.3, f'μ={mean_v:.1f}', ha='center', fontsize=10, color='#333')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig3_4_dispersion.png'), bbox_inches='tight')
    plt.savefig(os.path.join(OUT_DIR, 'fig3_4_dispersion.pdf'), bbox_inches='tight')
    plt.close()
    print("✓ fig3_4_dispersion")


def fig3_5_pipeline():
    """SliceFusion pipeline overview — text-based diagram."""
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 4)
    ax.axis('off')
    
    boxes = [
        (0.5, 1.5, '目标漏洞\n代码', '#E74C3C'),
        (3.0, 1.5, 'LLM\n智能拆分', '#3498DB'),
        (5.5, 1.5, 'CFG分析\n必经点识别', '#2ECC71'),
        (8.0, 1.5, '调用链\n融合注入', '#F39C12'),
        (10.5, 1.5, '语法\n验证', '#9B59B6'),
        (13.0, 1.5, '融合后\n代码', '#1ABC9C'),
    ]
    
    for x, y, text, color in boxes:
        rect = plt.Rectangle((x-0.7, y-0.5), 1.4, 1.0, facecolor=color, 
                             edgecolor='white', alpha=0.85, linewidth=2, 
                             joinstyle='round')
        ax.add_patch(rect)
        ax.text(x, y, text, ha='center', va='center', fontsize=10, 
               fontweight='bold', color='white')
    
    # Arrows
    for i in range(len(boxes)-1):
        x1 = boxes[i][0] + 0.7
        x2 = boxes[i+1][0] - 0.7
        ax.annotate('', xy=(x2, 1.5), xytext=(x1, 1.5),
                   arrowprops=dict(arrowstyle='->', color='#555', lw=2))
    
    ax.set_title('SliceFusion 代码融合流水线', fontsize=14, fontweight='bold', pad=20)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, 'fig3_5_pipeline.png'), bbox_inches='tight')
    plt.savefig(os.path.join(OUT_DIR, 'fig3_5_pipeline.pdf'), bbox_inches='tight')
    plt.close()
    print("✓ fig3_5_pipeline")


if __name__ == '__main__':
    fig3_1_depth_distribution()
    fig3_2_fusion_by_depth()
    fig3_3_vuln_types()
    fig3_4_dispersion()
    fig3_5_pipeline()
    print(f"\nAll figures saved to {OUT_DIR}")
