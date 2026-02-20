#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 语义审查器

使用大语言模型审查融合后代码的语义正确性。
主要检查：
1. 插入位置是否合理
2. 变量使用是否正确
3. 数据流是否正确
4. 是否破坏原函数逻辑
"""

import os
import json
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from openai import OpenAI


class IssueLevel(Enum):
    """问题级别"""
    CRITICAL = "critical"    # 严重问题，代码很可能无法正常工作
    MAJOR = "major"          # 主要问题，可能导致错误行为
    MINOR = "minor"          # 次要问题，代码可以工作但不完美
    SUGGESTION = "suggestion"  # 建议，可以改进的地方


@dataclass
class SemanticIssue:
    """语义问题"""
    level: IssueLevel
    category: str        # 问题类别
    description: str     # 问题描述
    location: str = ""   # 问题位置描述
    suggestion: str = "" # 修复建议
    
    def __str__(self):
        level_icons = {
            IssueLevel.CRITICAL: "🔴",
            IssueLevel.MAJOR: "🟠",
            IssueLevel.MINOR: "🟡",
            IssueLevel.SUGGESTION: "🔵"
        }
        icon = level_icons.get(self.level, "⚪")
        return f"{icon} [{self.category}] {self.description}"


@dataclass
class ReviewResult:
    """审查结果"""
    valid: bool                              # 是否通过审查
    confidence: float                        # 置信度 0.0-1.0
    issues: List[SemanticIssue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    summary: str = ""                        # 审查摘要
    raw_response: str = ""                   # LLM 原始响应
    
    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.level == IssueLevel.CRITICAL)
    
    @property
    def major_count(self) -> int:
        return sum(1 for i in self.issues if i.level == IssueLevel.MAJOR)
    
    def get_summary(self) -> str:
        if self.valid:
            return f"✅ 语义审查通过 (置信度: {self.confidence:.0%})"
        return f"❌ 语义审查未通过 ({self.critical_count} 个严重问题, {self.major_count} 个主要问题)"


class SemanticReviewer:
    """LLM 语义审查器"""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """
        初始化语义审查器
        
        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            model: 模型名称
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = model or "qwen-plus"
        
        if not self.api_key:
            raise ValueError("API key not found. Please set DASHSCOPE_API_KEY environment variable.")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def review_fusion(
        self,
        original_func: str,
        fused_func: str,
        inserted_code: str,
        func_name: str = "",
        context: Dict = None
    ) -> ReviewResult:
        """
        审查单个函数的融合结果
        
        Args:
            original_func: 原始函数代码
            fused_func: 融合后的函数代码
            inserted_code: 插入的代码片段
            func_name: 函数名
            context: 额外上下文信息
            
        Returns:
            ReviewResult 对象
        """
        prompt = self._create_review_prompt(
            original_func, fused_func, inserted_code, func_name, context
        )
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4096,
                extra_body={"enable_thinking": False},
            )
            
            response_text = completion.choices[0].message.content
            return self._parse_response(response_text)
            
        except Exception as e:
            # 如果 LLM 调用失败，返回一个无法确定的结果
            return ReviewResult(
                valid=True,  # 默认通过，因为无法验证
                confidence=0.0,
                issues=[SemanticIssue(
                    level=IssueLevel.MINOR,
                    category="审查失败",
                    description=f"LLM 审查调用失败: {str(e)}"
                )],
                summary="无法完成语义审查",
                raw_response=""
            )
    
    def review_all_fusions(
        self,
        fused_code: Dict[str, str],
        original_functions: Dict[str, str],
        inserted_slices: Dict[str, str],
        shared_state: Dict = None
    ) -> Dict[str, ReviewResult]:
        """
        审查所有融合后的函数
        
        Args:
            fused_code: 融合后的代码 {函数名: 代码}
            original_functions: 原始函数 {函数名: 代码}
            inserted_slices: 插入的代码片段 {函数名: 代码}
            shared_state: 共享状态变量信息
            
        Returns:
            每个函数的审查结果 {函数名: ReviewResult}
        """
        results = {}
        
        context = {"shared_state": shared_state} if shared_state else None
        
        for func_name, fused in fused_code.items():
            original = original_functions.get(func_name, "")
            inserted = inserted_slices.get(func_name, "")
            
            if original and inserted:
                results[func_name] = self.review_fusion(
                    original, fused, inserted, func_name, context
                )
            else:
                # 没有原始代码或插入代码，跳过审查
                results[func_name] = ReviewResult(
                    valid=True,
                    confidence=1.0,
                    summary="无需审查（无插入代码）"
                )
        
        return results
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个 C/C++ 编译检查专家，专门检查代码能否通过编译。

你的任务是检查融合后的代码是否能够通过 C/C++ 编译器的编译。

【只需要检查以下编译相关问题】：
1. 语法错误：括号不匹配、缺少分号、注释符号错误等
2. 代码位置错误：代码被插入到注释中、字符串中、或函数体外部
3. 声明顺序问题：在 C89 模式下，变量声明必须在语句之前

【不需要关注以下问题（这些不影响编译）】：
- 安全性问题（全局变量安全、线程安全等）
- 设计原则（单一职责、副作用等）
- 代码风格和最佳实践
- 未定义的类型、宏、外部函数（这些来自项目其他部分）
- 逻辑正确性（只要语法正确即可）

判断标准：只要代码在语法上能够被 C/C++ 编译器接受，就应该通过验证。

请严格按照 JSON 格式返回结果。"""

    def _create_review_prompt(
        self,
        original_func: str,
        fused_func: str,
        inserted_code: str,
        func_name: str = "",
        context: Dict = None
    ) -> str:
        """创建审查提示词"""
        
        context_info = ""
        if context and context.get("shared_state"):
            shared_vars = ", ".join(context["shared_state"].keys())
            context_info = f"\n【共享状态变量】\n{shared_vars}\n"
        
        func_info = f"（函数名: {func_name}）" if func_name else ""
        
        prompt = f"""请检查以下融合后的代码能否通过 C/C++ 编译{func_info}。

【融合后的函数】
```c
{fused_func}
```

【插入的代码片段】
```c
{inserted_code}
```
{context_info}
请只检查【编译相关】的问题：
1. 语法错误（括号不匹配、缺少分号等）
2. 代码是否被错误插入到注释中或函数体外部
3. C89 下变量声明是否在可执行语句之前（如果明显违反）

【不要报告】：安全问题、设计问题、线程安全、代码风格等（这些不影响编译）

返回 JSON 格式：
```json
{{
    "valid": true或false,
    "confidence": 0.0到1.0,
    "issues": [
        {{
            "level": "critical/major/minor/suggestion",
            "category": "语法错误/位置错误/声明顺序",
            "description": "问题描述"
        }}
    ],
    "summary": "一句话总结"
}}
```

判断标准：
- 只有语法上无法编译的问题才标记为 critical，valid 设为 false
- 可能的编译警告标记为 minor，valid 仍为 true
- 如果代码语法正确能编译，valid 应为 true

只返回 JSON。"""
        
        return prompt
    
    def _parse_response(self, response: str) -> ReviewResult:
        """解析 LLM 响应"""
        
        # 尝试提取 JSON
        result_dict = None
        
        try:
            result_dict = json.loads(response)
        except json.JSONDecodeError:
            pass
        
        if not result_dict:
            # 尝试从 markdown 代码块中提取
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
            if json_match:
                try:
                    result_dict = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
        
        if not result_dict:
            # 尝试找到 JSON 对象
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    result_dict = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
        
        if not result_dict:
            # 解析失败
            return ReviewResult(
                valid=True,
                confidence=0.5,
                issues=[SemanticIssue(
                    level=IssueLevel.MINOR,
                    category="解析失败",
                    description="无法解析 LLM 响应"
                )],
                summary="LLM 响应解析失败",
                raw_response=response
            )
        
        # 构建结果
        issues = []
        for issue_data in result_dict.get("issues", []):
            level_str = issue_data.get("level", "minor").lower()
            level_map = {
                "critical": IssueLevel.CRITICAL,
                "major": IssueLevel.MAJOR,
                "minor": IssueLevel.MINOR,
                "suggestion": IssueLevel.SUGGESTION
            }
            level = level_map.get(level_str, IssueLevel.MINOR)
            
            issues.append(SemanticIssue(
                level=level,
                category=issue_data.get("category", "未分类"),
                description=issue_data.get("description", ""),
                location=issue_data.get("location", ""),
                suggestion=issue_data.get("suggestion", "")
            ))
        
        return ReviewResult(
            valid=result_dict.get("valid", True),
            confidence=float(result_dict.get("confidence", 0.5)),
            issues=issues,
            suggestions=result_dict.get("suggestions", []),
            summary=result_dict.get("summary", ""),
            raw_response=response
        )
    
    def quick_check(self, fused_func: str, inserted_code: str) -> ReviewResult:
        """
        快速检查（不需要原始函数）
        
        Args:
            fused_func: 融合后的函数
            inserted_code: 插入的代码
            
        Returns:
            ReviewResult 对象
        """
        prompt = f"""请检查以下代码能否通过 C/C++ 编译。

【融合后的函数】
```c
{fused_func}
```

【插入的代码片段】
```c
{inserted_code}
```

只检查编译相关问题：语法错误、代码是否在注释中、括号匹配等。
不要报告安全、设计、风格等问题。

返回 JSON：
```json
{{
    "valid": true或false,
    "confidence": 0.0-1.0,
    "issues": [{{"level": "critical/minor", "category": "语法错误/位置错误", "description": "描述"}}],
    "summary": "一句话"
}}
```

只返回 JSON。"""

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是编译检查专家，只检查代码能否通过编译，不关注安全和设计问题。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4096,
                extra_body={"enable_thinking": False},
            )
            
            response_text = completion.choices[0].message.content
            return self._parse_response(response_text)
            
        except Exception as e:
            return ReviewResult(
                valid=True,
                confidence=0.0,
                summary=f"快速检查失败: {str(e)}"
            )


def review_fusion(
    original_func: str,
    fused_func: str,
    inserted_code: str,
    api_key: str = None
) -> ReviewResult:
    """
    审查代码融合的便捷函数
    
    Args:
        original_func: 原始函数
        fused_func: 融合后的函数
        inserted_code: 插入的代码
        api_key: API 密钥（可选）
        
    Returns:
        ReviewResult 对象
    """
    reviewer = SemanticReviewer(api_key=api_key)
    return reviewer.review_fusion(original_func, fused_func, inserted_code)


if __name__ == "__main__":
    # 测试代码
    original = """
    void process_data(int x) {
        int result = x * 2;
        printf("Result: %d\\n", result);
    }
    """
    
    inserted = """
    g_secret = 42;
    g_key = g_secret ^ 0xFF;
    """
    
    fused = """
    void process_data(int x) {
        g_secret = 42;
        g_key = g_secret ^ 0xFF;
        int result = x * 2;
        printf("Result: %d\\n", result);
    }
    """
    
    try:
        reviewer = SemanticReviewer()
        result = reviewer.review_fusion(original, fused, inserted, "process_data")
        
        print("=" * 60)
        print("语义审查结果")
        print("=" * 60)
        print(result.get_summary())
        print(f"\n摘要: {result.summary}")
        
        if result.issues:
            print("\n发现的问题:")
            for issue in result.issues:
                print(f"  {issue}")
                if issue.suggestion:
                    print(f"    → 建议: {issue.suggestion}")
        
        if result.suggestions:
            print("\n改进建议:")
            for sug in result.suggestions:
                print(f"  • {sug}")
                
    except Exception as e:
        print(f"Error: {e}")
        print("请确保设置了 DASHSCOPE_API_KEY 环境变量")

