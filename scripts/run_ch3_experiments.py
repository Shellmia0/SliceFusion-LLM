#!/usr/bin/env python3
"""
Chapter 3 全量实验 — SliceFusion

实验矩阵:
1. 全局变量法 × 不同调用深度 (depth 2,3,4,5+) — 各取50组
2. 参数传递法 × 不同调用深度 (depth 2,3,4,5+) — 各取50组  
3. 多种漏洞类型 × 全局变量法 — 5种CWE，各20组
4. 消融实验 — 去掉verification/semantic reviewer

输出: output/ch3_experiments/ 目录下
"""
import os
import sys
import json
import time
import argparse
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from main import CodeFusionProcessor

MODEL = "qwen3.5-plus-2026-02-15"
API_KEY = "REDACTED_API_KEY"
WORKERS = 4
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'ch3_experiments')

# === 漏洞类型定义 ===
VULN_TARGETS = {
    "format_string": {
        "cwe": "CWE-134",
        "name": "Format String Vulnerability",
        "code": '''void process_user_input(char *user_data) {
    char buffer[256];
    printf(user_data);  // format string vulnerability
    strncpy(buffer, user_data, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\\0';
}'''
    },
    "buffer_overflow": {
        "cwe": "CWE-120",
        "name": "Buffer Overflow",
        "code": '''void copy_input(char *src) {
    char dest[64];
    strcpy(dest, src);  // buffer overflow - no bounds check
    printf("Copied: %s\\n", dest);
}'''
    },
    "integer_overflow": {
        "cwe": "CWE-190",
        "name": "Integer Overflow",
        "code": '''void allocate_buffer(int count) {
    int size = count * sizeof(int);  // integer overflow if count is large
    int *buf = (int *)malloc(size);
    if (buf) {
        memset(buf, 0, size);
    }
}'''
    },
    "use_after_free": {
        "cwe": "CWE-416",
        "name": "Use After Free",
        "code": '''void process_data(struct node *p) {
    char *data = p->data;
    free(p);
    printf("Data: %s\\n", data);  // use after free
}'''
    },
    "null_deref": {
        "cwe": "CWE-476",
        "name": "NULL Pointer Dereference",
        "code": '''int get_value(struct config *cfg) {
    struct entry *e = cfg->entries;  // no NULL check on cfg
    return e->value;  // potential NULL dereference
}'''
    },
}

lock = threading.Lock()

def run_single(processor, group, target_code, idx, total, label="", method="global"):
    t0 = time.time()
    try:
        result = processor.process_group(group, target_code, group_index=idx, passing_method=method)
        elapsed = time.time() - t0
        # Count how many functions got injected slices
        fused = result.fused_code or {}
        original_funcs = {f.get('name', ''): f.get('code', '') for f in group.get('functions', [])}
        injected_count = 0
        for fname, fcode in fused.items():
            orig = original_funcs.get(fname, '')
            if orig and fcode != orig:
                injected_count += 1
        
        return {
            'group_index': idx,
            'call_depth': group.get('call_depth', len(group.get('call_chain', []))),
            'functions_count': len(group.get('functions', [])),
            'success': result.success,
            'error_message': result.error_message,
            'verification_passed': result.verification_passed,
            'verification_errors': getattr(result, 'verification_errors', None) or [],
            'verification_warnings': getattr(result, 'verification_warnings', None) or [],
            'passing_method': result.passing_method,
            'elapsed': elapsed,
            'fused_code': fused,
            'global_declarations': result.global_declarations or '',
            'injected_functions': injected_count,
        }
    except Exception as e:
        return {
            'group_index': idx,
            'call_depth': group.get('call_depth', 0),
            'functions_count': len(group.get('functions', [])),
            'success': False,
            'error_message': str(e),
            'verification_passed': False,
            'verification_errors': [str(e)],
            'verification_warnings': [],
            'passing_method': 'unknown',
            'elapsed': time.time() - t0,
            'fused_code': {},
            'global_declarations': '',
            'injected_functions': 0,
        }

def run_experiment(name, groups, target_code, method="global", enable_verify=True, enable_semantic=False):
    """Run one experiment batch."""
    print(f"\n{'='*60}")
    print(f"Experiment: {name}")
    print(f"Groups: {len(groups)}, Method: {method}, Verify: {enable_verify}")
    print(f"{'='*60}")
    
    processor = CodeFusionProcessor(
        api_key=API_KEY,
        enable_verification=enable_verify,
        enable_syntax_check=enable_verify,
        enable_semantic_check=enable_semantic,
        model=MODEL,
    )
    
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(run_single, processor, g, target_code, i, len(groups), name, method): i
            for i, g in enumerate(groups)
        }
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            done = len(results)
            status = '✓' if r['success'] else '✗'
            v = '✓' if r.get('verification_passed') else '✗'
            print(f"  [{done}/{len(groups)}] {status} verify={v} depth={r['call_depth']} t={r['elapsed']:.1f}s")
    
    # Sort by index
    results.sort(key=lambda x: x['group_index'])
    
    # Stats
    total = len(results)
    success = sum(1 for r in results if r['success'])
    v_pass = sum(1 for r in results if r.get('verification_passed'))
    avg_time = sum(r['elapsed'] for r in results) / total if total else 0
    
    output = {
        'metadata': {
            'experiment': name,
            'model': MODEL,
            'method': method,
            'target_code': target_code[:200],
            'total': total,
            'success': success,
            'success_rate': f"{success/total*100:.1f}%" if total else "N/A",
            'verification_pass': v_pass,
            'verification_rate': f"{v_pass/total*100:.1f}%" if total else "N/A",
            'avg_elapsed': f"{avg_time:.1f}s",
            'enable_verify': enable_verify,
            'enable_semantic': enable_semantic,
        },
        'results': results,
    }
    
    outpath = os.path.join(OUTPUT_DIR, f"{name}.json")
    with open(outpath, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n  Results: {success}/{total} success ({success/total*100:.1f}%)")
    print(f"  Verification: {v_pass}/{total} pass ({v_pass/total*100:.1f}%)")
    print(f"  Avg time: {avg_time:.1f}s")
    print(f"  Saved: {outpath}")
    
    return output

def load_groups_by_depth(all_groups, depth, limit=50):
    """Filter groups by call depth and limit count."""
    filtered = [g for g in all_groups if g.get('call_depth') == depth]
    return filtered[:limit]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=str, default="all",
                       help="Which experiment to run: depth|vuln|ablation|all")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    
    global WORKERS
    WORKERS = args.workers
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Load all groups
    data = json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'output', 'primevul_valid_grouped_depth_2+.json'
    )))
    all_groups = data.get('groups', [])
    print(f"Loaded {len(all_groups)} total groups")
    
    depth_dist = Counter(g.get('call_depth', 0) for g in all_groups)
    print(f"Depth distribution: {dict(sorted(depth_dist.items()))}")
    
    default_target = VULN_TARGETS["format_string"]["code"]
    
    if args.experiment in ("depth", "all"):
        # === Experiment 1: Depth comparison (global var method) ===
        for depth in [2, 3, 4, 5]:
            if depth == 5:
                groups = [g for g in all_groups if g.get('call_depth', 0) >= 5][:args.limit]
            else:
                groups = load_groups_by_depth(all_groups, depth, args.limit)
            if not groups:
                print(f"No groups for depth={depth}, skipping")
                continue
            run_experiment(
                f"depth_{depth}_global",
                groups, default_target, method="global"
            )
        
        # === Experiment 2: Depth comparison (parameter method) ===
        for depth in [2, 3, 4, 5]:
            if depth == 5:
                groups = [g for g in all_groups if g.get('call_depth', 0) >= 5][:args.limit]
            else:
                groups = load_groups_by_depth(all_groups, depth, args.limit)
            if not groups:
                print(f"No groups for depth={depth}, skipping")
                continue
            run_experiment(
                f"depth_{depth}_param",
                groups, default_target, method="parameter"
            )
    
    if args.experiment in ("vuln", "all"):
        # === Experiment 3: Different vulnerability types ===
        depth4_groups = load_groups_by_depth(all_groups, 4, args.limit)
        if not depth4_groups:
            depth4_groups = load_groups_by_depth(all_groups, 3, args.limit)
        
        for vuln_key, vuln_info in VULN_TARGETS.items():
            run_experiment(
                f"vuln_{vuln_key}",
                depth4_groups[:20], vuln_info["code"], method="global"
            )
    
    if args.experiment in ("ablation", "all"):
        # === Experiment 4: Ablation ===
        depth3_groups = load_groups_by_depth(all_groups, 3, 30)
        
        # Full pipeline
        run_experiment(
            "ablation_full",
            depth3_groups, default_target, method="global",
            enable_verify=True, enable_semantic=True
        )
        # No semantic review
        run_experiment(
            "ablation_no_semantic",
            depth3_groups, default_target, method="global",
            enable_verify=True, enable_semantic=False
        )
        # No verification at all
        run_experiment(
            "ablation_no_verify",
            depth3_groups, default_target, method="global",
            enable_verify=False, enable_semantic=False
        )
    
    print("\n" + "="*60)
    print("All experiments completed!")
    print(f"Results in: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
