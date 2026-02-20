#!/usr/bin/env python3
"""Batch fusion experiment for Chapter 3: run SliceFusion on PrimeVul call chains."""
import os
import sys
import json
import time
import argparse
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from main import CodeFusionProcessor

lock = threading.Lock()
results = []
success_count = 0
error_count = 0
verify_pass = 0
verify_fail = 0


def process_group(processor, group, target_code, idx, total):
    global success_count, error_count, verify_pass, verify_fail
    t0 = time.time()
    group_idx = group.get('group_index', idx)
    chain = group.get('call_chain', [])
    depth = group.get('call_depth', len(chain))
    
    try:
        result = processor.process_group(group, target_code)
        elapsed = time.time() - t0
        
        with lock:
            if result.success:
                success_count += 1
                if result.verification_passed:
                    verify_pass += 1
                else:
                    verify_fail += 1
            else:
                error_count += 1
            
            results.append({
                'group_index': group_idx,
                'call_chain': chain,
                'call_depth': depth,
                'functions_count': len(group.get('functions', [])),
                'success': result.success,
                'error_message': result.error_message,
                'verification_passed': result.verification_passed,
                'verification_errors': result.verification_errors or [],
                'verification_warnings': result.verification_warnings or [],
                'fused_code': result.fused_code if result.success else {},
                'passing_method': result.passing_method,
                'elapsed': elapsed,
            })
            
            status = '✓' if result.success else '✗'
            vstat = 'V✓' if result.verification_passed else 'V✗' if result.success else ''
            print(f"[{success_count+error_count}/{total}] G{group_idx} d={depth} {status} {vstat} {elapsed:.0f}s (ok:{success_count} err:{error_count} vp:{verify_pass} vf:{verify_fail})")
    
    except Exception as e:
        elapsed = time.time() - t0
        with lock:
            error_count += 1
            results.append({
                'group_index': group_idx,
                'call_chain': chain,
                'call_depth': depth,
                'success': False,
                'error_message': str(e),
                'elapsed': elapsed,
            })
            print(f"[{success_count+error_count}/{total}] G{group_idx} d={depth} ✗ {elapsed:.0f}s - {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", default="output/primevul_valid_grouped_depth_3-5.json")
    parser.add_argument("--target-code", default=None, help="Target vuln code to fuse (default: format string vuln)")
    parser.add_argument("--output", default="output/batch_fusion_results.json")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--model", type=str, default=None, help="LLM model name")
    args = parser.parse_args()

    # Default target: a realistic format string vulnerability
    if args.target_code:
        target_code = args.target_code
    else:
        target_code = '''
void process_user_input(char *user_data) {
    char buffer[256];
    printf(user_data);  // format string vulnerability
    strncpy(buffer, user_data, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\\0';
}
'''

    # Load groups
    data = json.load(open(args.groups))
    groups = data.get('groups', [])[:args.limit]
    print(f"Loaded {len(groups)} groups from {args.groups}")
    print(f"Target code: {target_code[:100]}...")
    print(f"Workers: {args.workers}, Verify: {not args.no_verify}")

    # Init processor
    api_key = os.environ.get("DASHSCOPE_API_KEY", "REDACTED_API_KEY")
    processor = CodeFusionProcessor(
        api_key=api_key,
        enable_verification=not args.no_verify,
        enable_syntax_check=True,
        enable_semantic_check=not args.no_verify,
        model=args.model,
    )

    total = len(groups)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process_group, processor, g, target_code, i, total) for i, g in enumerate(groups)]
        done = 0
        for f in as_completed(futures):
            done += 1
            if done % 5 == 0 or done == total:
                with lock:
                    with open(args.output, 'w') as out:
                        json.dump({
                            'metadata': {
                                'target_code': target_code,
                                'total': total,
                                'success': success_count,
                                'failed': error_count,
                                'verify_pass': verify_pass,
                                'verify_fail': verify_fail,
                            },
                            'results': results,
                        }, out, ensure_ascii=False, indent=2)
                    print(f"  --- Saved {len(results)} results ---")

    # Final save
    with open(args.output, 'w') as f:
        json.dump({
            'metadata': {
                'target_code': target_code,
                'total': total,
                'success': success_count,
                'failed': error_count,
                'verify_pass': verify_pass,
                'verify_fail': verify_fail,
            },
            'results': results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nFINISHED: {success_count} success, {error_count} errors")
    print(f"Verification: {verify_pass} pass, {verify_fail} fail")


if __name__ == "__main__":
    main()
