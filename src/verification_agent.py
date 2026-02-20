#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 Agent

整合语法验证和语义审查，提供统一的代码验证接口。
"""

import os
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

from syntax_validator import SyntaxValidator, ValidationResult as SyntaxResult
from semantic_reviewer import SemanticReviewer, ReviewResult, IssueLevel


class VerificationStatus(Enum):
    """验证状态"""
    PASSED = "passed"           # 完全通过
    PASSED_WITH_WARNINGS = "passed_with_warnings"  # 通过但有警告
    FAILED = "failed"           # 验证失败
    SKIPPED = "skipped"         # 跳过验证


@dataclass
class VerificationReport:
    """验证报告"""
    status: VerificationStatus
    function_name: str
    
    # 语法验证结果
    syntax_result: Optional[SyntaxResult] = None
    
    # 语义审查结果
    semantic_result: Optional[ReviewResult] = None
    
    # 综合信息
    error_messages: List[str] = field(default_factory=list)
    warning_messages: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    def get_summary(self) -> str:
        """获取验证摘要"""
        status_icons = {
            VerificationStatus.PASSED: "✅",
            VerificationStatus.PASSED_WITH_WARNINGS: "⚠️",
            VerificationStatus.FAILED: "❌",
            VerificationStatus.SKIPPED: "⏭️"
        }
        icon = status_icons.get(self.status, "❓")
        
        error_count = len(self.error_messages)
        warning_count = len(self.warning_messages)
        
        if self.status == VerificationStatus.PASSED:
            return f"{icon} {self.function_name}: 验证通过"
        elif self.status == VerificationStatus.PASSED_WITH_WARNINGS:
            return f"{icon} {self.function_name}: 验证通过 ({warning_count} 个警告)"
        elif self.status == VerificationStatus.FAILED:
            return f"{icon} {self.function_name}: 验证失败 ({error_count} 个错误)"
        else:
            return f"{icon} {self.function_name}: 跳过验证"


@dataclass
class FullVerificationReport:
    """完整验证报告（所有函数）"""
    reports: Dict[str, VerificationReport] = field(default_factory=dict)
    overall_status: VerificationStatus = VerificationStatus.PASSED
    
    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.reports.values() 
                   if r.status in [VerificationStatus.PASSED, VerificationStatus.PASSED_WITH_WARNINGS])
    
    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.reports.values() if r.status == VerificationStatus.FAILED)
    
    def get_summary(self) -> str:
        """获取整体验证摘要"""
        total = len(self.reports)
        if self.overall_status == VerificationStatus.PASSED:
            return f"✅ 验证完成: {self.passed_count}/{total} 通过"
        elif self.overall_status == VerificationStatus.PASSED_WITH_WARNINGS:
            return f"⚠️ 验证完成: {self.passed_count}/{total} 通过 (有警告)"
        else:
            return f"❌ 验证失败: {self.failed_count}/{total} 失败"
    
    def get_detailed_report(self) -> str:
        """获取详细报告"""
        lines = ["=" * 60, "验证报告详情", "=" * 60, ""]
        
        for func_name, report in self.reports.items():
            lines.append(report.get_summary())
            
            if report.error_messages:
                lines.append("  错误:")
                for err in report.error_messages:
                    lines.append(f"    - {err}")
            
            if report.warning_messages:
                lines.append("  警告:")
                for warn in report.warning_messages[:5]:  # 最多显示5个
                    lines.append(f"    - {warn}")
                if len(report.warning_messages) > 5:
                    lines.append(f"    ... 还有 {len(report.warning_messages) - 5} 个警告")
            
            if report.suggestions:
                lines.append("  建议:")
                for sug in report.suggestions[:3]:  # 最多显示3个
                    lines.append(f"    - {sug}")
            
            lines.append("")
        
        lines.append("=" * 60)
        lines.append(self.get_summary())
        
        return "\n".join(lines)


class VerificationAgent:
    """验证 Agent"""
    
    def __init__(
        self,
        enable_syntax: bool = True,
        enable_semantic: bool = True,
        api_key: str = None,
        model: str = None
    ):
        """
        初始化验证 Agent
        
        Args:
            enable_syntax: 是否启用语法验证
            enable_semantic: 是否启用语义审查
            api_key: LLM API 密钥（语义审查需要）
            model: LLM 模型名称
        """
        self.enable_syntax = enable_syntax
        self.enable_semantic = enable_semantic
        
        # 初始化语法验证器
        self.syntax_validator = SyntaxValidator() if enable_syntax else None
        
        # 初始化语义审查器
        self.semantic_reviewer = None
        if enable_semantic:
            try:
                self.semantic_reviewer = SemanticReviewer(api_key=api_key, model=model)
            except ValueError as e:
                print(f"Warning: 语义审查器初始化失败: {e}")
                self.enable_semantic = False
    
    def verify_function(
        self,
        fused_code: str,
        original_code: str = "",
        inserted_code: str = "",
        func_name: str = "unknown",
        shared_state: Dict = None
    ) -> VerificationReport:
        """
        验证单个函数
        
        Args:
            fused_code: 融合后的代码
            original_code: 原始代码（可选）
            inserted_code: 插入的代码（可选）
            func_name: 函数名
            shared_state: 共享状态变量
            
        Returns:
            VerificationReport 对象
        """
        report = VerificationReport(
            status=VerificationStatus.PASSED,
            function_name=func_name
        )
        
        # 1. 语法验证
        if self.enable_syntax and self.syntax_validator:
            if original_code:
                syntax_result = self.syntax_validator.validate_fused_code(original_code, fused_code)
            else:
                syntax_result = self.syntax_validator.validate(fused_code)
            
            report.syntax_result = syntax_result
            
            # 收集语法错误和警告
            for error in syntax_result.errors:
                report.error_messages.append(f"[语法] {error.message}")
            
            for warning in syntax_result.warnings:
                report.warning_messages.append(f"[语法] {warning.message}")
            
            # 如果有语法错误，标记为失败
            if not syntax_result.valid:
                report.status = VerificationStatus.FAILED
                return report  # 语法错误时跳过语义审查
        
        # 2. 语义审查
        if self.enable_semantic and self.semantic_reviewer and inserted_code:
            if original_code:
                context = {"shared_state": shared_state} if shared_state else None
                semantic_result = self.semantic_reviewer.review_fusion(
                    original_code, fused_code, inserted_code, func_name, context
                )
            else:
                semantic_result = self.semantic_reviewer.quick_check(fused_code, inserted_code)
            
            report.semantic_result = semantic_result
            
            # 收集语义问题
            for issue in semantic_result.issues:
                if issue.level == IssueLevel.CRITICAL:
                    report.error_messages.append(f"[语义] {issue.description}")
                elif issue.level == IssueLevel.MAJOR:
                    report.error_messages.append(f"[语义] {issue.description}")
                else:
                    report.warning_messages.append(f"[语义] {issue.description}")
                
                if issue.suggestion:
                    report.suggestions.append(issue.suggestion)
            
            # 添加 LLM 的建议
            report.suggestions.extend(semantic_result.suggestions)
            
            # 如果语义审查未通过
            if not semantic_result.valid:
                report.status = VerificationStatus.FAILED
                return report
        
        # 3. 确定最终状态
        if report.error_messages:
            report.status = VerificationStatus.FAILED
        elif report.warning_messages:
            report.status = VerificationStatus.PASSED_WITH_WARNINGS
        else:
            report.status = VerificationStatus.PASSED
        
        return report
    
    def verify_all(
        self,
        fused_code: Dict[str, str],
        original_functions: Dict[str, str] = None,
        inserted_slices: Dict[str, str] = None,
        shared_state: Dict = None
    ) -> FullVerificationReport:
        """
        验证所有融合后的函数
        
        Args:
            fused_code: 融合后的代码 {函数名: 代码}
            original_functions: 原始函数 {函数名: 代码}
            inserted_slices: 插入的代码片段 {函数名: 代码}
            shared_state: 共享状态变量
            
        Returns:
            FullVerificationReport 对象
        """
        original_functions = original_functions or {}
        inserted_slices = inserted_slices or {}
        
        full_report = FullVerificationReport()
        
        for func_name, fused in fused_code.items():
            original = original_functions.get(func_name, "")
            inserted = inserted_slices.get(func_name, "")
            
            report = self.verify_function(
                fused_code=fused,
                original_code=original,
                inserted_code=inserted,
                func_name=func_name,
                shared_state=shared_state
            )
            
            full_report.reports[func_name] = report
        
        # 确定整体状态
        has_failed = any(r.status == VerificationStatus.FAILED for r in full_report.reports.values())
        has_warnings = any(r.status == VerificationStatus.PASSED_WITH_WARNINGS for r in full_report.reports.values())
        
        if has_failed:
            full_report.overall_status = VerificationStatus.FAILED
        elif has_warnings:
            full_report.overall_status = VerificationStatus.PASSED_WITH_WARNINGS
        else:
            full_report.overall_status = VerificationStatus.PASSED
        
        return full_report


def verify_fusion(
    fused_code: str,
    original_code: str = "",
    inserted_code: str = "",
    func_name: str = "unknown",
    enable_syntax: bool = True,
    enable_semantic: bool = True
) -> VerificationReport:
    """
    验证代码融合的便捷函数
    
    Args:
        fused_code: 融合后的代码
        original_code: 原始代码
        inserted_code: 插入的代码
        func_name: 函数名
        enable_syntax: 是否启用语法验证
        enable_semantic: 是否启用语义审查
        
    Returns:
        VerificationReport 对象
    """
    agent = VerificationAgent(
        enable_syntax=enable_syntax,
        enable_semantic=enable_semantic
    )
    return agent.verify_function(
        fused_code=fused_code,
        original_code=original_code,
        inserted_code=inserted_code,
        func_name=func_name
    )


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
    
    fused_valid = """
    void process_data(int x) {
        g_secret = 42;
        g_key = g_secret ^ 0xFF;
        int result = x * 2;
        printf("Result: %d\\n", result);
    }
    """
    
    fused_invalid = """
    void process_data(int x) {
        g_secret = 42;
        g_key = g_secret ^ 0xFF;
        int result = x * 2;
        printf("Result: %d\\n", result);
    // 缺少闭合花括号
    """
    
    # 测试验证 Agent
    print("=" * 60)
    print("验证 Agent 测试")
    print("=" * 60)
    
    # 只启用语法验证（不需要 API）
    agent = VerificationAgent(enable_syntax=True, enable_semantic=False)
    
    print("\n测试 1: 有效代码")
    report = agent.verify_function(
        fused_code=fused_valid,
        original_code=original,
        inserted_code=inserted,
        func_name="process_data"
    )
    print(report.get_summary())
    
    print("\n测试 2: 无效代码（语法错误）")
    report = agent.verify_function(
        fused_code=fused_invalid,
        original_code=original,
        inserted_code=inserted,
        func_name="process_data"
    )
    print(report.get_summary())
    for err in report.error_messages:
        print(f"  {err}")
    
    # 测试带语义审查（需要 API）
    print("\n" + "=" * 60)
    print("测试语义审查（需要 DASHSCOPE_API_KEY）")
    print("=" * 60)
    
    try:
        agent_full = VerificationAgent(enable_syntax=True, enable_semantic=True)
        report = agent_full.verify_function(
            fused_code=fused_valid,
            original_code=original,
            inserted_code=inserted,
            func_name="process_data"
        )
        print(report.get_summary())
        
        if report.semantic_result:
            print(f"  语义审查置信度: {report.semantic_result.confidence:.0%}")
            print(f"  摘要: {report.semantic_result.summary}")
            
    except Exception as e:
        print(f"语义审查跳过: {e}")

