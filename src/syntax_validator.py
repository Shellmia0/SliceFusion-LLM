#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语法结构验证器

验证 C/C++ 代码的基本语法结构，不依赖编译器。
主要检查：
1. 括号匹配（花括号、圆括号、方括号）
2. 字符串/字符引号匹配
3. 语句完整性（分号检查）
4. 函数结构完整性
"""

import re
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


class ErrorLevel(Enum):
    """错误级别"""
    ERROR = "error"      # 严重错误，代码肯定无法运行
    WARNING = "warning"  # 警告，可能有问题
    INFO = "info"        # 提示信息


@dataclass
class SyntaxError:
    """语法错误"""
    level: ErrorLevel
    message: str
    line: int = 0
    column: int = 0
    context: str = ""
    
    def __str__(self):
        loc = f"[Line {self.line}] " if self.line > 0 else ""
        return f"{loc}{self.level.value.upper()}: {self.message}"


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: List[SyntaxError] = field(default_factory=list)
    warnings: List[SyntaxError] = field(default_factory=list)
    
    @property
    def error_count(self) -> int:
        return len(self.errors)
    
    @property
    def warning_count(self) -> int:
        return len(self.warnings)
    
    def get_summary(self) -> str:
        if self.valid:
            if self.warnings:
                return f"✅ 语法验证通过 ({self.warning_count} 个警告)"
            return "✅ 语法验证通过"
        return f"❌ 语法验证失败 ({self.error_count} 个错误, {self.warning_count} 个警告)"


class SyntaxValidator:
    """语法结构验证器"""
    
    def __init__(self):
        # 括号配对
        self.bracket_pairs = {
            '{': '}',
            '(': ')',
            '[': ']'
        }
        self.closing_brackets = set(self.bracket_pairs.values())
        self.opening_brackets = set(self.bracket_pairs.keys())
    
    def validate(self, code: str) -> ValidationResult:
        """
        验证代码的语法结构
        
        Args:
            code: C/C++ 代码
            
        Returns:
            ValidationResult 对象
        """
        errors = []
        warnings = []
        
        # 预处理：移除注释
        clean_code = self._remove_comments(code)
        
        # 1. 括号匹配检查
        bracket_errors = self._check_brackets(clean_code)
        errors.extend(bracket_errors)
        
        # 2. 引号匹配检查
        quote_errors = self._check_quotes(clean_code)
        errors.extend(quote_errors)
        
        # 3. 语句完整性检查
        stmt_warnings = self._check_statements(clean_code)
        warnings.extend(stmt_warnings)
        
        # 4. 函数结构检查
        func_errors = self._check_function_structure(clean_code)
        errors.extend(func_errors)
        
        # 5. 常见错误模式检查
        pattern_warnings = self._check_common_patterns(clean_code)
        warnings.extend(pattern_warnings)
        
        valid = len(errors) == 0
        
        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings
        )
    
    def _remove_comments(self, code: str) -> str:
        """移除代码中的注释"""
        # 移除单行注释
        code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
        # 移除多行注释
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        return code
    
    def _check_brackets(self, code: str) -> List[SyntaxError]:
        """检查括号匹配"""
        errors = []
        stack = []  # [(bracket_char, line_num, col)]
        
        lines = code.split('\n')
        in_string = False
        string_char = None
        
        for line_num, line in enumerate(lines, 1):
            col = 0
            i = 0
            while i < len(line):
                char = line[i]
                
                # 处理字符串
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and (i == 0 or line[i-1] != '\\'):
                        in_string = False
                    i += 1
                    col += 1
                    continue
                
                if in_string:
                    i += 1
                    col += 1
                    continue
                
                # 检查括号
                if char in self.opening_brackets:
                    stack.append((char, line_num, col))
                elif char in self.closing_brackets:
                    if not stack:
                        errors.append(SyntaxError(
                            level=ErrorLevel.ERROR,
                            message=f"多余的闭括号 '{char}'",
                            line=line_num,
                            column=col,
                            context=line.strip()
                        ))
                    else:
                        open_bracket, open_line, open_col = stack.pop()
                        expected_close = self.bracket_pairs[open_bracket]
                        if char != expected_close:
                            errors.append(SyntaxError(
                                level=ErrorLevel.ERROR,
                                message=f"括号不匹配：期望 '{expected_close}'，实际 '{char}'（对应第 {open_line} 行的 '{open_bracket}'）",
                                line=line_num,
                                column=col,
                                context=line.strip()
                            ))
                
                i += 1
                col += 1
        
        # 检查未闭合的括号
        for open_bracket, open_line, open_col in stack:
            expected_close = self.bracket_pairs[open_bracket]
            errors.append(SyntaxError(
                level=ErrorLevel.ERROR,
                message=f"未闭合的括号 '{open_bracket}'，缺少 '{expected_close}'",
                line=open_line,
                column=open_col,
                context=lines[open_line - 1].strip() if open_line <= len(lines) else ""
            ))
        
        return errors
    
    def _check_quotes(self, code: str) -> List[SyntaxError]:
        """检查引号匹配"""
        errors = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # 跳过预处理指令
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            # 简单检查：每行的引号应该成对
            in_string = False
            string_char = None
            string_start = 0
            
            i = 0
            while i < len(line):
                char = line[i]
                
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        string_char = char
                        string_start = i
                    elif char == string_char:
                        # 检查是否是转义
                        escape_count = 0
                        j = i - 1
                        while j >= 0 and line[j] == '\\':
                            escape_count += 1
                            j -= 1
                        if escape_count % 2 == 0:
                            in_string = False
                
                i += 1
            
            if in_string:
                errors.append(SyntaxError(
                    level=ErrorLevel.ERROR,
                    message=f"未闭合的字符串（从列 {string_start} 开始）",
                    line=line_num,
                    column=string_start,
                    context=line.strip()
                ))
        
        return errors
    
    def _check_statements(self, code: str) -> List[SyntaxError]:
        """检查语句完整性"""
        warnings = []
        lines = code.split('\n')
        
        # 需要以分号结尾的语句模式
        statement_patterns = [
            r'^\s*\w+\s+\w+\s*=',       # 变量声明赋值
            r'^\s*\w+\s*=',              # 赋值语句
            r'^\s*\w+\s*\([^)]*\)\s*$',  # 函数调用（没有分号的情况）
            r'^\s*return\s+',            # return 语句
            r'^\s*break\s*$',            # break
            r'^\s*continue\s*$',         # continue
        ]
        
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # 跳过空行、注释、预处理指令、控制结构
            if not stripped or stripped.startswith('#'):
                continue
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue
            if any(stripped.startswith(kw) for kw in ['if', 'else', 'while', 'for', 'switch', 'case', 'default', 'do']):
                continue
            if stripped.endswith('{') or stripped.endswith('}') or stripped == '{' or stripped == '}':
                continue
            
            # 检查是否应该有分号但没有
            for pattern in statement_patterns:
                if re.match(pattern, stripped):
                    if not stripped.endswith(';') and not stripped.endswith('{'):
                        warnings.append(SyntaxError(
                            level=ErrorLevel.WARNING,
                            message="语句可能缺少分号",
                            line=line_num,
                            context=stripped
                        ))
                    break
        
        return warnings
    
    def _check_function_structure(self, code: str) -> List[SyntaxError]:
        """检查函数结构完整性"""
        errors = []
        
        # 检查是否有函数定义的基本结构
        # 函数模式：返回类型 函数名(参数) { ... }
        func_pattern = r'(?:[\w\s\*&<>,]+?)\s+(\w+)\s*\([^)]*\)\s*\{'
        
        matches = list(re.finditer(func_pattern, code))
        
        for match in matches:
            func_name = match.group(1)
            start_pos = match.end() - 1  # { 的位置
            
            # 检查函数体的花括号是否匹配
            brace_count = 1
            pos = start_pos + 1
            
            while pos < len(code) and brace_count > 0:
                if code[pos] == '{':
                    brace_count += 1
                elif code[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            if brace_count != 0:
                line_num = code[:match.start()].count('\n') + 1
                errors.append(SyntaxError(
                    level=ErrorLevel.ERROR,
                    message=f"函数 '{func_name}' 的花括号不匹配",
                    line=line_num
                ))
        
        return errors
    
    def _check_common_patterns(self, code: str) -> List[SyntaxError]:
        """检查常见错误模式"""
        warnings = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # 检查 if/while/for 后面直接跟分号（可能是错误）
            if re.match(r'^(if|while|for)\s*\([^)]+\)\s*;', stripped):
                warnings.append(SyntaxError(
                    level=ErrorLevel.WARNING,
                    message="控制语句后直接跟分号，可能是错误",
                    line=line_num,
                    context=stripped
                ))
            
            # 检查 = 和 == 的可能混淆（在 if/while 条件中）
            if_match = re.match(r'^(if|while)\s*\((.+)\)', stripped)
            if if_match:
                condition = if_match.group(2)
                # 简单检查：如果条件中有单个 = 且不是 == 或 != 或 <= 或 >=
                if re.search(r'[^=!<>]=[^=]', condition):
                    warnings.append(SyntaxError(
                        level=ErrorLevel.WARNING,
                        message="条件中使用了 '='，是否应该是 '=='？",
                        line=line_num,
                        context=stripped
                    ))
            
            # 检查数组越界的明显模式（如 arr[sizeof(arr)]）
            if 'sizeof' in stripped and '[' in stripped:
                if re.search(r'\[\s*sizeof\s*\(\s*\w+\s*\)\s*\]', stripped):
                    warnings.append(SyntaxError(
                        level=ErrorLevel.WARNING,
                        message="可能的数组越界：使用 sizeof 作为索引",
                        line=line_num,
                        context=stripped
                    ))
        
        return warnings
    
    def validate_fused_code(self, original_code: str, fused_code: str) -> ValidationResult:
        """
        验证融合后的代码
        
        比较原始代码和融合后代码的结构差异
        """
        # 首先验证融合后代码的基本语法
        result = self.validate(fused_code)
        
        # 额外检查：确保融合没有破坏原始结构
        orig_braces = original_code.count('{') 
        fused_braces = fused_code.count('{')
        
        # 融合后的代码花括号数量应该相同或更多（插入的代码可能有新的块）
        if fused_braces < orig_braces:
            result.warnings.append(SyntaxError(
                level=ErrorLevel.WARNING,
                message=f"融合后代码的花括号数量减少（原始: {orig_braces}, 融合后: {fused_braces}）",
                line=0
            ))
        
        return result


def validate_code(code: str) -> ValidationResult:
    """
    验证代码语法结构的便捷函数
    
    Args:
        code: C/C++ 代码
        
    Returns:
        ValidationResult 对象
    """
    validator = SyntaxValidator()
    return validator.validate(code)


def validate_fused_code(original: str, fused: str) -> ValidationResult:
    """
    验证融合后代码的便捷函数
    
    Args:
        original: 原始代码
        fused: 融合后的代码
        
    Returns:
        ValidationResult 对象
    """
    validator = SyntaxValidator()
    return validator.validate_fused_code(original, fused)


if __name__ == "__main__":
    # 测试代码
    test_code_valid = """
    int test_function(int x) {
        if (x > 0) {
            return x * 2;
        } else {
            return -x;
        }
    }
    """
    
    test_code_invalid = """
    int broken_function(int x) {
        if (x > 0) {
            return x * 2;
        // 缺少闭合括号
    }
    """
    
    test_code_warning = """
    int warning_function(int x) {
        if (x = 5) {  // 应该是 ==
            return x;
        }
        int y = 10  // 缺少分号
        return y;
    }
    """
    
    validator = SyntaxValidator()
    
    print("=" * 60)
    print("测试 1: 有效代码")
    print("=" * 60)
    result = validator.validate(test_code_valid)
    print(result.get_summary())
    
    print("\n" + "=" * 60)
    print("测试 2: 无效代码（括号不匹配）")
    print("=" * 60)
    result = validator.validate(test_code_invalid)
    print(result.get_summary())
    for error in result.errors:
        print(f"  {error}")
    
    print("\n" + "=" * 60)
    print("测试 3: 有警告的代码")
    print("=" * 60)
    result = validator.validate(test_code_warning)
    print(result.get_summary())
    for warning in result.warnings:
        print(f"  {warning}")

