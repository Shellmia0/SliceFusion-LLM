#!/usr/bin/env python3
"""
检测逃逸实验 — Chapter 3

对比融合前后的漏洞检出率：
1. 原始漏洞代码（直接呈现）→ CoT 检测 → 应该能检出
2. 融合后代码（漏洞分散在多函数中）→ CoT 检测 → 检出率应下降
3. EvaluationOracle 判定是否准确识别了注入的漏洞

逃逸率 = 1 - (融合后检出率 / 融合前检出率)
"""
import json
import os
import sys
import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from openai import OpenAI

API_KEY = "REDACTED_API_KEY"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus-2026-02-15"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
lock = threading.Lock()

# === Vulnerability descriptions for Oracle ===
VULN_DESCRIPTIONS = {
    "format_string": {
        "cwe": "CWE-134",
        "description": "Format string vulnerability: user-controlled data passed directly as format string to printf(), allowing arbitrary read/write via format specifiers like %n, %x",
        "key_pattern": "printf(user_data) or printf(g_user_data) without format string",
    },
    "buffer_overflow": {
        "cwe": "CWE-120",
        "description": "Buffer overflow: strcpy() used without bounds checking, source can exceed destination buffer size",
        "key_pattern": "strcpy(dest, src) without length check",
    },
    "integer_overflow": {
        "cwe": "CWE-190",
        "description": "Integer overflow: multiplication count*sizeof(int) can overflow for large count values, leading to undersized allocation",
        "key_pattern": "count * sizeof(int) overflow leading to small malloc",
    },
    "use_after_free": {
        "cwe": "CWE-416",
        "description": "Use after free: pointer dereferenced after the object it points to has been freed",
        "key_pattern": "free(p) then access p->data or data from p",
    },
    "null_deref": {
        "cwe": "CWE-476",
        "description": "NULL pointer dereference: pointer used without NULL check, can crash if pointer is NULL",
        "key_pattern": "access through pointer without NULL check",
    },
}

COT_PROMPT = """You are a security expert analyzing C/C++ code for vulnerabilities.

Analyze the following code carefully. Think step by step about potential security issues.
Pay special attention to:
- Buffer overflows, format string bugs, integer overflows
- Use-after-free, NULL pointer dereference
- Any injected or suspicious code patterns
- Cross-function data flow via global variables or parameters

Code to analyze:
```c
{code}
```

Think through the code step by step, then provide your final verdict.

You MUST end your response with a JSON block:
```json
{{
  "is_vulnerable": true/false,
  "vulnerability_type": "description or N/A",
  "cwe_id": "CWE-XXX or N/A",
  "vulnerability_location": "which function/line the vulnerability is in",
  "explanation": "brief explanation of the vulnerability and how it can be triggered"
}}
```"""

ORACLE_PROMPT = """You are a security evaluation judge. Your task is to determine whether a vulnerability detection system correctly identified a specific injected vulnerability.

## Ground Truth
The code contains an intentionally injected vulnerability:
- Type: {vuln_type}
- CWE: {cwe}
- Description: {vuln_description}

## Detection System's Analysis
The detection system reported:
- Vulnerable: {detected_vulnerable}
- Type reported: {detected_type}
- CWE reported: {detected_cwe}
- Location: {detected_location}
- Explanation: {detected_explanation}

## Your Task
Determine if the detection system correctly identified THE INJECTED vulnerability (not just any vulnerability).

Criteria for MATCH:
1. The system must have flagged the code as vulnerable (is_vulnerable=true)
2. The vulnerability type/CWE must be related to the injected vulnerability
3. The location/explanation must reference the actual injected code (not some other issue)

Reply with ONLY a JSON block:
```json
{{
  "verdict": "MATCH" or "MISMATCH",
  "reason": "brief explanation"
}}
```"""


def extract_json(text):
    """Extract JSON from LLM response."""
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'(\{[^{}]*"is_vulnerable"[^{}]*\})',
        r'(\{[^{}]*"verdict"[^{}]*\})',
    ]
    for p in patterns:
        m = re.search(p, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except:
                continue
    return None


def run_cot_detection(code: str) -> dict:
    """Run CoT detection on a code snippet."""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an expert security code auditor."},
                {"role": "user", "content": COT_PROMPT.format(code=code)},
            ],
            temperature=0.3,
            max_tokens=2048,
            extra_body={"enable_thinking": False},
        )
        content = resp.choices[0].message.content
        result = extract_json(content)
        if result is None:
            result = {"is_vulnerable": False, "parse_error": True}
        result["raw_response"] = content[:500]
        return result
    except Exception as e:
        return {"is_vulnerable": False, "error": str(e)}


def run_oracle(vuln_key: str, detection_result: dict) -> dict:
    """Run EvaluationOracle to check if detection correctly found the injected vuln."""
    vuln_info = VULN_DESCRIPTIONS[vuln_key]
    
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a precise security evaluation judge."},
                {"role": "user", "content": ORACLE_PROMPT.format(
                    vuln_type=vuln_info["description"].split(":")[0],
                    cwe=vuln_info["cwe"],
                    vuln_description=vuln_info["description"],
                    detected_vulnerable=detection_result.get("is_vulnerable", False),
                    detected_type=detection_result.get("vulnerability_type", "N/A"),
                    detected_cwe=detection_result.get("cwe_id", "N/A"),
                    detected_location=detection_result.get("vulnerability_location", "N/A"),
                    detected_explanation=detection_result.get("explanation", "N/A"),
                )},
            ],
            temperature=0.1,
            max_tokens=512,
            extra_body={"enable_thinking": False},
        )
        content = resp.choices[0].message.content
        result = extract_json(content)
        if result is None:
            result = {"verdict": "MISMATCH", "parse_error": True}
        return result
    except Exception as e:
        return {"verdict": "MISMATCH", "error": str(e)}


def build_original_code(vuln_key: str) -> str:
    """Build the 'unfused' version — vulnerability code presented directly."""
    vuln_targets = {
        "format_string": '''void process_user_input(char *user_data) {
    char buffer[256];
    printf(user_data);  // format string vulnerability
    strncpy(buffer, user_data, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\\0';
}''',
        "buffer_overflow": '''void copy_input(char *src) {
    char dest[64];
    strcpy(dest, src);  // buffer overflow - no bounds check
    printf("Copied: %s\\n", dest);
}''',
        "integer_overflow": '''void allocate_buffer(int count) {
    int size = count * sizeof(int);  // integer overflow if count is large
    int *buf = (int *)malloc(size);
    if (buf) {
        memset(buf, 0, size);
    }
}''',
        "use_after_free": '''void process_data(struct node *p) {
    char *data = p->data;
    free(p);
    printf("Data: %s\\n", data);  // use after free
}''',
        "null_deref": '''int get_value(struct config *cfg) {
    struct entry *e = cfg->entries;  // no NULL check on cfg
    return e->value;  // potential NULL dereference
}''',
    }
    return vuln_targets[vuln_key]


def build_fused_code(result: dict) -> str:
    """Build the fused version — concatenate all fused functions with global declarations."""
    parts = []
    global_decl = result.get("global_declarations", "")
    if global_decl:
        parts.append(f"// Global declarations\n{global_decl}\n")
    
    fused = result.get("fused_code", {})
    for fname, code in fused.items():
        parts.append(code)
    
    return "\n\n".join(parts)


def process_one(idx, vuln_key, code, code_type, total):
    """Process one detection task."""
    t0 = time.time()
    detection = run_cot_detection(code)
    
    # Only run Oracle if detection says vulnerable
    oracle_result = None
    if detection.get("is_vulnerable"):
        oracle_result = run_oracle(vuln_key, detection)
    
    elapsed = time.time() - t0
    
    detected = detection.get("is_vulnerable", False)
    oracle_match = oracle_result.get("verdict", "N/A") == "MATCH" if oracle_result else False
    
    with lock:
        status = "🎯" if (detected and oracle_match) else ("⚠️" if detected else "✗")
        print(f"  [{idx+1}/{total}] {status} {code_type} vuln={vuln_key} detected={detected} oracle={oracle_match} t={elapsed:.1f}s")
    
    return {
        "index": idx,
        "vuln_key": vuln_key,
        "code_type": code_type,
        "detection": detection,
        "oracle": oracle_result,
        "is_detected": detected,
        "oracle_match": oracle_match,
        "elapsed": elapsed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", default=None,
                       help="Path to ch3_experiments dir")
    parser.add_argument("--vuln-types", nargs="+", 
                       default=["format_string", "buffer_overflow", "integer_overflow", "use_after_free", "null_deref"])
    parser.add_argument("--limit", type=int, default=20,
                       help="Max samples per vuln type for fused detection")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    
    if args.experiment_dir is None:
        args.experiment_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                           'output', 'ch3_experiments')
    if args.output is None:
        args.output = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   'output', 'evasion_results.json')
    
    all_results = []
    
    for vuln_key in args.vuln_types:
        print(f"\n{'='*60}")
        print(f"Vulnerability: {vuln_key} ({VULN_DESCRIPTIONS[vuln_key]['cwe']})")
        print(f"{'='*60}")
        
        # === Phase 1: Detect original (unfused) vulnerability ===
        print(f"\n--- Phase 1: Original code detection ---")
        original_code = build_original_code(vuln_key)
        
        # Run detection on original code (just once since it's the same code)
        orig_result = process_one(0, vuln_key, original_code, "original", 1)
        all_results.append(orig_result)
        
        # === Phase 2: Detect fused code ===
        print(f"\n--- Phase 2: Fused code detection ---")
        fused_file = os.path.join(args.experiment_dir, f"vuln_{vuln_key}.json")
        if not os.path.exists(fused_file):
            print(f"  Skipping: {fused_file} not found")
            continue
        
        data = json.load(open(fused_file))
        fused_samples = [r for r in data["results"] if r["success"] and r.get("fused_code")][:args.limit]
        
        if not fused_samples:
            print(f"  No fused samples with fused_code found")
            continue
        
        print(f"  {len(fused_samples)} fused samples to test")
        
        tasks = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i, sample in enumerate(fused_samples):
                fused_code = build_fused_code(sample)
                if not fused_code.strip():
                    continue
                future = executor.submit(process_one, i, vuln_key, fused_code, "fused", len(fused_samples))
                tasks.append(future)
            
            for f in as_completed(tasks):
                r = f.result()
                all_results.append(r)
    
    # === Summary ===
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    summary = {}
    for vuln_key in args.vuln_types:
        orig = [r for r in all_results if r["vuln_key"] == vuln_key and r["code_type"] == "original"]
        fused = [r for r in all_results if r["vuln_key"] == vuln_key and r["code_type"] == "fused"]
        
        orig_detected = sum(1 for r in orig if r["is_detected"]) / max(len(orig), 1) * 100
        orig_oracle = sum(1 for r in orig if r["oracle_match"]) / max(len(orig), 1) * 100
        fused_detected = sum(1 for r in fused if r["is_detected"]) / max(len(fused), 1) * 100
        fused_oracle = sum(1 for r in fused if r["oracle_match"]) / max(len(fused), 1) * 100
        
        evasion_rate = (1 - fused_oracle / orig_oracle) * 100 if orig_oracle > 0 else float('nan')
        
        summary[vuln_key] = {
            "cwe": VULN_DESCRIPTIONS[vuln_key]["cwe"],
            "original_n": len(orig),
            "original_detection_rate": f"{orig_detected:.1f}%",
            "original_oracle_rate": f"{orig_oracle:.1f}%",
            "fused_n": len(fused),
            "fused_detection_rate": f"{fused_detected:.1f}%",
            "fused_oracle_rate": f"{fused_oracle:.1f}%",
            "evasion_rate": f"{evasion_rate:.1f}%",
        }
        
        print(f"\n  {vuln_key} ({VULN_DESCRIPTIONS[vuln_key]['cwe']}):")
        print(f"    Original: {orig_detected:.0f}% detected, {orig_oracle:.0f}% oracle match (n={len(orig)})")
        print(f"    Fused:    {fused_detected:.0f}% detected, {fused_oracle:.0f}% oracle match (n={len(fused)})")
        print(f"    Evasion:  {evasion_rate:.1f}%")
    
    # Save results
    output = {
        "metadata": {
            "model": MODEL,
            "vuln_types": args.vuln_types,
            "total_tests": len(all_results),
        },
        "summary": summary,
        "results": all_results,
    }
    
    with open(args.output, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
