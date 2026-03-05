#!/usr/bin/env python3
"""
evaluation_oracle.py - EvaluationOracle 严格评估机制

基于 LLM-as-Judge 范式的漏洞检测评估模块。
与传统的标签匹配不同，EvaluationOracle 进行三阶段评估：
  1. 标签一致性检查：检测结果是否正确判断了漏洞存在性
  2. 定位准确性验证：是否准确定位了漏洞片段所在位置
  3. 推理合理性评估：推理过程是否基于正确的代码分析逻辑

严格 TP 定义：检测方法必须同时满足（1）正确判断漏洞存在，
（2）准确定位漏洞关键片段位置，（3）正确识别漏洞类型。

用法:
    from evaluation_oracle import EvaluationOracle

    oracle = EvaluationOracle(api_key="...", model="qwen3-235b-a22b")
    result = oracle.evaluate(
        ground_truth={
            "cwe": "CWE-134",
            "vuln_type": "format_string",
            "description": "格式化字符串漏洞",
            "injected_locations": ["function_a", "function_c"],
        },
        detection_result={
            "is_vulnerable": True,
            "vulnerability_type": "format string",
            "cwe_id": "CWE-134",
            "vulnerability_location": "function_a, line 15",
            "explanation": "printf called with user-controlled format string",
        }
    )
    print(result.verdict)  # "TP", "FP", "FN", "TN"
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ============================================================
# 漏洞类型定义
# ============================================================

VULNERABILITY_DEFINITIONS = {
    "format_string": {
        "cwe": "CWE-134",
        "name": "格式化字符串漏洞",
        "description": "Format string vulnerability: user-controlled data passed directly "
                       "as format string to printf/sprintf, allowing arbitrary read/write "
                       "via format specifiers like %n, %x.",
        "key_indicators": ["printf(user_data)", "sprintf without format", "fprintf(fp, var)"],
    },
    "buffer_overflow": {
        "cwe": "CWE-120",
        "name": "缓冲区溢出",
        "description": "Buffer overflow: data written beyond the allocated buffer boundary, "
                       "typically via strcpy/memcpy without bounds checking.",
        "key_indicators": ["strcpy without length check", "memcpy with unchecked size", "gets()"],
    },
    "integer_overflow": {
        "cwe": "CWE-190",
        "name": "整数溢出",
        "description": "Integer overflow: arithmetic operation produces a result that exceeds "
                       "the representation range of the integer type, leading to wraparound.",
        "key_indicators": ["multiplication overflow", "size_t wraparound", "count * sizeof"],
    },
    "use_after_free": {
        "cwe": "CWE-416",
        "name": "释放后使用",
        "description": "Use-after-free: a pointer is dereferenced after the memory it points "
                       "to has been freed, leading to undefined behavior.",
        "key_indicators": ["free(p) then p->field", "dangling pointer access"],
    },
    "null_deref": {
        "cwe": "CWE-476",
        "name": "空指针解引用",
        "description": "NULL pointer dereference: a pointer is used without NULL check, "
                       "which may crash the program if the pointer is NULL.",
        "key_indicators": ["pointer access without NULL check", "malloc without NULL check"],
    },
}


# ============================================================
# 评估提示词
# ============================================================

ORACLE_JUDGE_PROMPT = """You are a security evaluation oracle. Your task is to rigorously assess
whether a vulnerability detection system correctly identified a specific injected vulnerability
in code that has been modified by SliceFusion (vulnerability fragments dispersed across multiple functions).

## Ground Truth (Injected Vulnerability)
- Vulnerability Type: {vuln_type_name}
- CWE: {cwe}
- Description: {vuln_description}
- Injected Locations: {injected_locations}

## Detection System's Report
- Flagged as vulnerable: {det_vulnerable}
- Reported type: {det_type}
- Reported CWE: {det_cwe}
- Reported location: {det_location}
- Explanation: {det_explanation}

## Evaluation Criteria

### Phase 1: Label Consistency
Did the detection system correctly identify the presence of a vulnerability?

### Phase 2: Localization Accuracy
Did the detection system identify the CORRECT vulnerability (the injected one, not some other issue)?
For SliceFusion samples, the vulnerability is dispersed across multiple functions.
The detection must reference at least one of the actual injected locations.

### Phase 3: Reasoning Validity
Is the detection system's reasoning logically sound?
Did it correctly trace the cross-function data flow?
Or did it merely guess based on superficial pattern matching?

## Output Format
Reply with ONLY a JSON block:
```json
{{
  "phase1_label_match": true/false,
  "phase2_location_match": true/false,
  "phase3_reasoning_valid": true/false,
  "verdict": "TP" | "FP" | "FN" | "TN",
  "confidence": 0.0-1.0,
  "reason": "brief explanation of the verdict"
}}
```

Verdict rules:
- TP: All three phases pass (label correct + location accurate + reasoning valid)
- FP: Detection says vulnerable but location/type is wrong (phases 2 or 3 fail)
- FN: Detection says not vulnerable but vulnerability exists
- TN: Detection says not vulnerable and code is indeed safe (only for safe control samples)
"""


# ============================================================
# 数据类
# ============================================================

@dataclass
class OracleResult:
    """EvaluationOracle 评估结果"""
    verdict: str  # "TP", "FP", "FN", "TN"
    phase1_label_match: bool = False
    phase2_location_match: bool = False
    phase3_reasoning_valid: bool = False
    confidence: float = 0.0
    reason: str = ""
    raw_response: str = ""

    @property
    def is_correct_detection(self) -> bool:
        return self.verdict == "TP"

    @property
    def is_evasion(self) -> bool:
        return self.verdict in ("FN", "FP")

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "phase1_label_match": self.phase1_label_match,
            "phase2_location_match": self.phase2_location_match,
            "phase3_reasoning_valid": self.phase3_reasoning_valid,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class StrictMetrics:
    """严格评估指标（基于 EvaluationOracle 的 TP/FP/TN/FN 定义）"""
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def strict_accuracy(self) -> float:
        """严格准确率: (TP + TN) / Total"""
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def strict_precision(self) -> float:
        """严格精确率: TP / (TP + FP)"""
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def strict_recall(self) -> float:
        """严格召回率: TP / (TP + FN)"""
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def strict_f1(self) -> float:
        """严格F1分数"""
        p, r = self.strict_precision, self.strict_recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def evasion_rate(self) -> float:
        """逃逸率: 1 - strict_recall"""
        return 1.0 - self.strict_recall

    def to_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
            "total": self.total,
            "strict_accuracy": round(self.strict_accuracy * 100, 1),
            "strict_precision": round(self.strict_precision * 100, 1),
            "strict_recall": round(self.strict_recall * 100, 1),
            "strict_f1": round(self.strict_f1 * 100, 1),
            "evasion_rate": round(self.evasion_rate * 100, 1),
        }


# ============================================================
# EvaluationOracle 主类
# ============================================================

class EvaluationOracle:
    """
    EvaluationOracle 严格评估机制
    
    基于 LLM-as-Judge 范式，对漏洞检测结果进行三阶段评估：
    标签一致性 → 定位准确性 → 推理合理性
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = "qwen3-235b-a22b",
    ):
        if OpenAI is None:
            raise ImportError("openai package required: pip install openai")
        
        self.client = OpenAI(
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        self.model = model

    def evaluate(
        self,
        ground_truth: Dict,
        detection_result: Dict,
    ) -> OracleResult:
        """
        评估单个检测结果。

        Args:
            ground_truth: 真实标签
                - cwe: str (e.g., "CWE-134")
                - vuln_type: str (e.g., "format_string")
                - description: str
                - injected_locations: List[str] (函数名列表)
            detection_result: 检测系统输出
                - is_vulnerable: bool
                - vulnerability_type: str
                - cwe_id: str
                - vulnerability_location: str
                - explanation: str

        Returns:
            OracleResult
        """
        vuln_key = ground_truth.get("vuln_type", "")
        vuln_def = VULNERABILITY_DEFINITIONS.get(vuln_key, {})

        prompt = ORACLE_JUDGE_PROMPT.format(
            vuln_type_name=vuln_def.get("name", ground_truth.get("description", "")),
            cwe=ground_truth.get("cwe", "N/A"),
            vuln_description=vuln_def.get("description", ground_truth.get("description", "")),
            injected_locations=", ".join(ground_truth.get("injected_locations", ["unknown"])),
            det_vulnerable=detection_result.get("is_vulnerable", False),
            det_type=detection_result.get("vulnerability_type", "N/A"),
            det_cwe=detection_result.get("cwe_id", "N/A"),
            det_location=detection_result.get("vulnerability_location", "N/A"),
            det_explanation=detection_result.get("explanation", "N/A"),
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise security evaluation oracle."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = resp.choices[0].message.content
            parsed = self._extract_json(raw)

            if parsed is None:
                return OracleResult(verdict="FN", reason="Failed to parse oracle response", raw_response=raw[:300])

            return OracleResult(
                verdict=parsed.get("verdict", "FN"),
                phase1_label_match=parsed.get("phase1_label_match", False),
                phase2_location_match=parsed.get("phase2_location_match", False),
                phase3_reasoning_valid=parsed.get("phase3_reasoning_valid", False),
                confidence=parsed.get("confidence", 0.0),
                reason=parsed.get("reason", ""),
                raw_response=raw[:300],
            )
        except Exception as e:
            return OracleResult(verdict="FN", reason=f"Oracle error: {e}")

    def evaluate_batch(
        self,
        samples: List[Dict],
    ) -> tuple:
        """
        批量评估，返回 (results_list, StrictMetrics)。

        每个 sample 需包含:
            - ground_truth: dict
            - detection_result: dict
        """
        results = []
        metrics = StrictMetrics()

        for sample in samples:
            result = self.evaluate(
                ground_truth=sample["ground_truth"],
                detection_result=sample["detection_result"],
            )
            results.append(result)

            if result.verdict == "TP":
                metrics.tp += 1
            elif result.verdict == "FP":
                metrics.fp += 1
            elif result.verdict == "TN":
                metrics.tn += 1
            else:
                metrics.fn += 1

        return results, metrics

    @staticmethod
    def compare_label_vs_oracle(
        detection_results: List[Dict],
        oracle_results: List[OracleResult],
    ) -> Dict:
        """
        对比纯标签匹配 vs EvaluationOracle 评估结果。
        
        Returns:
            {
                "label_match_rate": float,
                "oracle_strict_rate": float,
                "overestimate_pct": float,
            }
        """
        n = len(detection_results)
        if n == 0:
            return {"label_match_rate": 0, "oracle_strict_rate": 0, "overestimate_pct": 0}

        label_correct = sum(1 for d in detection_results if d.get("is_vulnerable", False))
        oracle_correct = sum(1 for o in oracle_results if o.verdict == "TP")

        label_rate = label_correct / n * 100
        oracle_rate = oracle_correct / n * 100
        overestimate = ((label_rate - oracle_rate) / oracle_rate * 100) if oracle_rate > 0 else float("inf")

        return {
            "label_match_rate": round(label_rate, 1),
            "oracle_strict_rate": round(oracle_rate, 1),
            "overestimate_pct": round(overestimate, 1),
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'(\{[^{}]*"verdict"[^{}]*\})',
        ]
        for p in patterns:
            m = re.search(p, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        return None
