#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SliceFusion-LLM Visualization Demo Script
Generate visualization charts to showcase project effects
"""

import os
import json

# Must set backend before importing pyplot
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# Set font - use English to avoid font issues
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 10


def create_call_chain_diagram(call_chain, slices, output_path):
    """
    Create call chain fusion diagram
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    
    n = len(call_chain)
    box_width = 3.5
    box_height = 1.8
    start_x = 1
    
    colors = ['#E3F2FD', '#E8F5E9', '#FFF3E0', '#FCE4EC', '#F3E5F5']
    accent_colors = ['#1976D2', '#388E3C', '#F57C00', '#C2185B', '#7B1FA2']
    
    # Title
    ax.text(7, 9.5, 'SliceFusion-LLM: Code Slice Fusion Diagram', 
            fontsize=16, fontweight='bold', ha='center', va='center')
    
    # Draw each function block
    y_positions = []
    for i, func_name in enumerate(call_chain):
        y = 8 - i * 2.2
        y_positions.append(y)
        
        # Function box
        rect = FancyBboxPatch(
            (start_x, y - box_height/2), box_width, box_height,
            boxstyle="round,pad=0.05,rounding_size=0.2",
            facecolor=colors[i % len(colors)],
            edgecolor=accent_colors[i % len(accent_colors)],
            linewidth=2
        )
        ax.add_patch(rect)
        
        # Function name (truncate if too long)
        display_name = func_name[:20] + '...' if len(func_name) > 20 else func_name
        ax.text(start_x + box_width/2, y + 0.4, display_name,
                fontsize=10, fontweight='bold', ha='center', va='center',
                color=accent_colors[i % len(accent_colors)])
        
        # Level label
        ax.text(start_x + box_width/2, y - 0.3, f'Level {i+1} Function',
                fontsize=8, ha='center', va='center', color='gray')
        
        # Inserted code slice
        if i < len(slices) and slices[i]:
            slice_x = start_x + box_width + 0.8
            slice_box = FancyBboxPatch(
                (slice_x, y - 0.6), 8, 1.2,
                boxstyle="round,pad=0.05,rounding_size=0.1",
                facecolor='#FFFDE7',
                edgecolor='#FBC02D',
                linewidth=1.5,
                linestyle='--'
            )
            ax.add_patch(slice_box)
            
            # Slice content
            slice_text = slices[i][:55] + '...' if len(slices[i]) > 55 else slices[i]
            ax.text(slice_x + 4, y, f'Slice {i+1}: {slice_text}',
                    fontsize=8, ha='center', va='center', 
                    family='monospace', style='italic')
            
            # Arrow connection
            ax.annotate('', xy=(slice_x, y), xytext=(start_x + box_width, y),
                       arrowprops=dict(arrowstyle='->', color='#FBC02D', lw=1.5))
        
        # Call arrow
        if i < n - 1:
            ax.annotate('', 
                       xy=(start_x + box_width/2, y_positions[i] - box_height/2 - 0.3),
                       xytext=(start_x + box_width/2, y_positions[i] - box_height/2 - 0.1),
                       arrowprops=dict(arrowstyle='->', color='gray', lw=2))
            ax.text(start_x + box_width + 0.1, y - box_height/2 - 0.2, 'call',
                   fontsize=8, color='gray', style='italic')
    
    # Legend
    legend_elements = [
        mpatches.Patch(facecolor='#E3F2FD', edgecolor='#1976D2', label='Original Function'),
        mpatches.Patch(facecolor='#FFFDE7', edgecolor='#FBC02D', linestyle='--', label='Inserted Code Slice'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  Call chain diagram saved: {output_path}")


def create_fusion_flow_diagram(output_path):
    """
    Create system architecture flow diagram
    """
    fig, ax = plt.subplots(1, 1, figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis('off')
    
    # Title
    ax.text(8, 9.5, 'SliceFusion-LLM System Architecture', 
            fontsize=18, fontweight='bold', ha='center')
    
    # Define modules
    modules = [
        {'name': 'Input Layer', 'x': 1, 'y': 7, 'w': 2, 'h': 1.5, 'color': '#BBDEFB', 
         'items': ['JSONL Source', 'Target Code']},
        {'name': 'Data Processing', 'x': 4, 'y': 7, 'w': 2.5, 'h': 1.5, 'color': '#C8E6C9',
         'items': ['Call Relation Extract', 'Call Chain Group']},
        {'name': 'Analysis Layer', 'x': 7.5, 'y': 7, 'w': 2.5, 'h': 1.5, 'color': '#FFE0B2',
         'items': ['CFG Build', 'Dominator Analysis']},
        {'name': 'LLM Split Layer', 'x': 11, 'y': 7, 'w': 2.5, 'h': 1.5, 'color': '#E1BEE7',
         'items': ['Smart Code Split', 'Fallback Mechanism']},
        {'name': 'Fusion Layer', 'x': 4, 'y': 4, 'w': 2.5, 'h': 1.5, 'color': '#B2EBF2',
         'items': ['State Generation', 'Code Insertion']},
        {'name': 'Verification', 'x': 7.5, 'y': 4, 'w': 2.5, 'h': 1.5, 'color': '#FFCDD2',
         'items': ['Syntax Validation', 'LLM Semantic Review']},
        {'name': 'Output Layer', 'x': 11, 'y': 4, 'w': 2.5, 'h': 1.5, 'color': '#DCEDC8',
         'items': ['Fused Code .c', 'Verification Report']},
    ]
    
    for mod in modules:
        # Module box
        rect = FancyBboxPatch(
            (mod['x'], mod['y'] - mod['h']/2), mod['w'], mod['h'],
            boxstyle="round,pad=0.02,rounding_size=0.15",
            facecolor=mod['color'],
            edgecolor='gray',
            linewidth=1.5
        )
        ax.add_patch(rect)
        
        # Module name
        ax.text(mod['x'] + mod['w']/2, mod['y'] + 0.4, mod['name'],
                fontsize=10, fontweight='bold', ha='center', va='center')
        
        # Sub items
        for j, item in enumerate(mod['items']):
            ax.text(mod['x'] + mod['w']/2, mod['y'] - 0.2 - j*0.35, f'- {item}',
                    fontsize=8, ha='center', va='center', color='#424242')
    
    # Arrow connections
    for i, (x1, y1, x2, y2) in enumerate([
        (3, 7, 4, 7),       # Input -> Data Processing
        (6.5, 7, 7.5, 7),   # Data Processing -> Analysis
        (10, 7, 11, 7),     # Analysis -> LLM Split
        (6.5, 4, 7.5, 4),   # Fusion -> Verification
        (10, 4, 11, 4),     # Verification -> Output
    ]):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                   arrowprops=dict(arrowstyle='->', color='#757575', lw=2))
    
    # Curved arrow (from LLM Split to Fusion Layer)
    ax.annotate('', xy=(6.5, 4), xytext=(11, 5.25),
               arrowprops=dict(arrowstyle='->', color='#757575', lw=2,
                              connectionstyle="arc3,rad=-0.3"))
    
    # Bottom description
    ax.text(8, 1.5, 'Key Features: LLM Smart Split | CFG Analysis | Multi-layer Verification | State Passing',
            fontsize=11, ha='center', va='center', 
            bbox=dict(boxstyle='round', facecolor='#F5F5F5', edgecolor='gray'))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  Flow diagram saved: {output_path}")


def create_statistics_chart(stats_data, output_path):
    """
    Create statistics charts
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('SliceFusion-LLM Dataset Statistics', fontsize=16, fontweight='bold')
    
    # 1. Call depth distribution (pie chart)
    ax1 = axes[0, 0]
    depth_labels = ['Depth 1', 'Depth 2', 'Depth 3', 'Depth 4', 'Depth 5+']
    depth_values = [4057, 489, 135, 50, 46]
    colors = ['#42A5F5', '#66BB6A', '#FFCA28', '#EF5350', '#AB47BC']
    explode = (0, 0, 0, 0.1, 0.1)
    ax1.pie(depth_values, explode=explode, labels=depth_labels, colors=colors,
            autopct='%1.1f%%', shadow=True, startangle=90)
    ax1.set_title('Call Chain Depth Distribution', fontsize=12, fontweight='bold')
    
    # 2. Success rate (bar chart)
    ax2 = axes[0, 1]
    methods = ['Global Var', 'Param Pass', 'LLM Split', 'Fallback']
    success_rates = [100, 100, 96, 4]
    bars = ax2.bar(methods, success_rates, color=['#42A5F5', '#66BB6A', '#FFCA28', '#EF5350'])
    ax2.set_ylabel('Success Rate (%)')
    ax2.set_title('Module Success Rates', fontsize=12, fontweight='bold')
    ax2.set_ylim(0, 110)
    for bar, rate in zip(bars, success_rates):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                f'{rate}%', ha='center', va='bottom', fontweight='bold')
    
    # 3. Processing time distribution (horizontal bar chart)
    ax3 = axes[1, 0]
    stages = ['Data Load', 'CFG Analysis', 'LLM Split', 'Code Fusion', 'Syntax Check', 'Semantic Review', 'File Output']
    times = [0.5, 2.3, 28.5, 1.2, 0.3, 16.4, 0.8]
    colors = plt.cm.Blues(np.linspace(0.3, 0.9, len(stages)))
    bars = ax3.barh(stages, times, color=colors)
    ax3.set_xlabel('Time (seconds)')
    ax3.set_title('Processing Time by Stage (50 groups)', fontsize=12, fontweight='bold')
    for bar, time in zip(bars, times):
        ax3.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'{time}s', ha='left', va='center')
    
    # 4. Project distribution (horizontal bar chart)
    ax4 = axes[1, 1]
    projects = ['Linux Kernel', 'MySQL', 'HHVM', 'GPAC', 'TensorFlow', 'Others']
    counts = [7120, 920, 911, 875, 656, 14948]
    colors = plt.cm.Greens(np.linspace(0.3, 0.9, len(projects)))
    bars = ax4.barh(projects, counts, color=colors)
    ax4.set_xlabel('Function Count')
    ax4.set_title('Dataset Project Distribution', fontsize=12, fontweight='bold')
    for bar, count in zip(bars, counts):
        ax4.text(bar.get_width() + 200, bar.get_y() + bar.get_height()/2,
                f'{count}', ha='left', va='center')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  Statistics chart saved: {output_path}")


def create_code_fusion_example(output_path):
    """
    Create code fusion before/after comparison diagram
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    fig.suptitle('Code Fusion Before vs After', fontsize=16, fontweight='bold', y=0.98)
    
    # Left: Before fusion
    ax1 = axes[0]
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 10)
    ax1.axis('off')
    ax1.set_title('Before: Standalone Target Code', fontsize=12, fontweight='bold', pad=20)
    
    # Target code box
    target_rect = FancyBboxPatch(
        (1, 5.5), 8, 3.5,
        boxstyle="round,pad=0.05,rounding_size=0.2",
        facecolor='#FFEBEE',
        edgecolor='#C62828',
        linewidth=2
    )
    ax1.add_patch(target_rect)
    ax1.text(5, 8.5, 'Target Code (To Be Fused)', fontsize=11, fontweight='bold', ha='center')
    
    target_code = '''int secret_value = 0x12345678;
int key = secret_value ^ 0xDEADBEEF;
printf("Computed key: 0x%x", key);'''
    ax1.text(5, 6.8, target_code, fontsize=9, ha='center', va='center',
             family='monospace', linespacing=1.5)
    
    # Call chain box
    chain_rect = FancyBboxPatch(
        (1, 0.5), 8, 4,
        boxstyle="round,pad=0.05,rounding_size=0.2",
        facecolor='#E3F2FD',
        edgecolor='#1565C0',
        linewidth=2
    )
    ax1.add_patch(chain_rect)
    ax1.text(5, 4, 'Call Chain Functions (Original)', fontsize=11, fontweight='bold', ha='center')
    
    chain_text = '''f1() -> f2() -> f3() -> f4()

Each function keeps original code
No target code logic'''
    ax1.text(5, 2.2, chain_text, fontsize=9, ha='center', va='center',
             family='monospace', linespacing=1.5)
    
    # Right: After fusion
    ax2 = axes[1]
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 10)
    ax2.axis('off')
    ax2.set_title('After: Code Distributed in Call Chain', fontsize=12, fontweight='bold', pad=20)
    
    # Fused functions
    funcs = [
        ('f1()', 'g_secret = 0x12345678;', 8.5),
        ('f2()', 'g_key = g_secret ^ 0xDEADBEEF;', 6.2),
        ('f3()', '// original code...', 3.9),
        ('f4()', 'printf("key: 0x%x", g_key);', 1.6),
    ]
    
    colors = ['#E8F5E9', '#FFF3E0', '#E3F2FD', '#FCE4EC']
    edge_colors = ['#2E7D32', '#EF6C00', '#1565C0', '#AD1457']
    
    for i, (fname, code, y) in enumerate(funcs):
        rect = FancyBboxPatch(
            (0.5, y - 0.8), 9, 1.8,
            boxstyle="round,pad=0.05,rounding_size=0.15",
            facecolor=colors[i],
            edgecolor=edge_colors[i],
            linewidth=2
        )
        ax2.add_patch(rect)
        
        ax2.text(1.5, y + 0.3, fname, fontsize=10, fontweight='bold',
                color=edge_colors[i])
        
        # Inserted code highlight
        if '0x' in code or 'printf' in code:
            ax2.text(5, y - 0.2, f'>> {code}', fontsize=9, ha='center',
                    family='monospace', color='#B71C1C', fontweight='bold')
        else:
            ax2.text(5, y - 0.2, code, fontsize=9, ha='center',
                    family='monospace', color='gray')
        
        # Call arrows
        if i < len(funcs) - 1:
            ax2.annotate('', xy=(5, y - 0.8 - 0.3), xytext=(5, y - 0.8 - 0.1),
                        arrowprops=dict(arrowstyle='->', color='gray', lw=2))
    
    # Global variable declaration
    ax2.text(5, 9.5, 'static int g_secret, g_key;  // Shared State',
             fontsize=9, ha='center', family='monospace',
             bbox=dict(boxstyle='round', facecolor='#FFFDE7', edgecolor='#FBC02D'))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  Comparison diagram saved: {output_path}")


def create_verification_result_chart(output_path):
    """
    Create verification result visualization
    """
    fig, ax = plt.subplots(1, 1, figsize=(12, 7))
    
    # Data
    categories = ['Group 0\ncrypto_*', 'Group 1\nzend_*', 'Group 2\nOpen_table_*', 
                  'Group 3\nlatm_*', 'Group 4\nprocess_*']
    
    # Verification results
    syntax_pass = [1, 1, 1, 1, 1]
    semantic_pass = [1, 1, 1, 0.8, 0.9]
    
    x = np.arange(len(categories))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, syntax_pass, width, label='Syntax Validation', color='#66BB6A')
    bars2 = ax.bar(x + width/2, semantic_pass, width, label='Semantic Review', color='#42A5F5')
    
    ax.set_ylabel('Pass Rate', fontsize=12)
    ax.set_title('Verification Results (5 Test Groups)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9)
    ax.legend(loc='lower right')
    ax.set_ylim(0, 1.2)
    
    # Add pass markers
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                'OK', ha='center', va='bottom', fontsize=10, color='green', fontweight='bold')
    
    for bar, val in zip(bars2, semantic_pass):
        symbol = 'OK' if val >= 1 else 'WARN'
        color = 'green' if val >= 1 else 'orange'
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                symbol, ha='center', va='bottom', fontsize=10, color=color, fontweight='bold')
    
    # Add legend
    ax.text(0.02, 0.98, 'OK = Fully Passed\nWARN = Passed with Warnings', 
            transform=ax.transAxes, fontsize=10,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"  Verification chart saved: {output_path}")


def main():
    """Main function - generate all visualization charts"""
    
    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'demo')
    os.makedirs(output_dir, exist_ok=True)
    
    print("=" * 60)
    print("SliceFusion-LLM Visualization Demo")
    print("=" * 60)
    print()
    
    # 1. Create call chain diagram
    print("[1/5] Generating call chain fusion diagram...")
    call_chain = [
        'crypto_get_certificate_data',
        'crypto_cert_fingerprint', 
        'crypto_cert_fingerprint_by_hash',
        'crypto_cert_hash'
    ]
    slices = [
        'g_secret = 0x12345678;',
        'g_key = g_secret ^ 0xDEADBEEF;',
        '',
        'printf("key: 0x%x", g_key);'
    ]
    create_call_chain_diagram(
        call_chain, slices,
        os.path.join(output_dir, 'demo_call_chain.png')
    )
    
    # 2. Create system flow diagram
    print("[2/5] Generating system architecture diagram...")
    create_fusion_flow_diagram(
        os.path.join(output_dir, 'demo_architecture.png')
    )
    
    # 3. Create statistics chart
    print("[3/5] Generating statistics charts...")
    create_statistics_chart(
        {},
        os.path.join(output_dir, 'demo_statistics.png')
    )
    
    # 4. Create code fusion comparison diagram
    print("[4/5] Generating code fusion comparison...")
    create_code_fusion_example(
        os.path.join(output_dir, 'demo_fusion_compare.png')
    )
    
    # 5. Create verification result chart
    print("[5/5] Generating verification results chart...")
    create_verification_result_chart(
        os.path.join(output_dir, 'demo_verification.png')
    )
    
    print()
    print("=" * 60)
    print("All visualization charts generated successfully!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)
    
    # List generated files
    print("\nGenerated chart files:")
    for f in sorted(os.listdir(output_dir)):
        if f.endswith('.png'):
            filepath = os.path.join(output_dir, f)
            size_kb = os.path.getsize(filepath) / 1024
            print(f"  - {f} ({size_kb:.1f} KB)")


if __name__ == '__main__':
    main()
