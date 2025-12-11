#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码融合模块

实现将代码片段融合到调用链函数中的逻辑。
"""

import json
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field

from cfg_analyzer import ControlFlowGraph, analyze_code_cfg, BasicBlock
from dominator_analyzer import DominatorAnalyzer, get_fusion_points
from llm_splitter import LLMCodeSplitter, SliceResult, CodeSlice


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    code: str
    cfg: Optional[ControlFlowGraph] = None
    fusion_points: List[int] = field(default_factory=list)
    idx: Optional[int] = None  # 原始数据中的索引
    
    def analyze(self):
        """分析函数的 CFG 和融合点"""
        if self.cfg is None:
            self.cfg = analyze_code_cfg(self.code, self.name)
            self.fusion_points = get_fusion_points(self.cfg)


@dataclass
class CallChain:
    """调用链"""
    functions: List[FunctionInfo]
    depth: int
    call_path: List[str]  # 函数名调用路径
    
    @property
    def function_names(self) -> List[str]:
        return [f.name for f in self.functions]
    
    def get_total_fusion_points(self) -> int:
        """获取总融合点数量"""
        return sum(len(f.fusion_points) for f in self.functions)


@dataclass
class FusionPlan:
    """融合计划"""
    target_code: str
    call_chain: CallChain
    slice_result: SliceResult
    insertion_points: List[Tuple[str, int, str]]  # [(函数名, 块ID, 代码片段)]


class CodeFusionEngine:
    """代码融合引擎"""
    
    def __init__(self, splitter: LLMCodeSplitter = None):
        """
        初始化融合引擎
        
        Args:
            splitter: LLM 代码拆分器
        """
        self.splitter = splitter or LLMCodeSplitter()
    
    def extract_function_name(self, func_code: str) -> str:
        """提取函数名"""
        # 移除注释
        code = re.sub(r'//.*?\n', '\n', func_code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        # 匹配函数定义
        patterns = [
            r'(?:[\w\s\*&<>,]+?)\s+(\w+::~?\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*\{',
            r'^[\s]*(\w+::~?\w+)\s*\([^)]*\)\s*\{',
            r'(?:[\w\s\*&<>,]+?)\s+(\w+)\s*\([^)]*\)\s*\{',
            r'^\s*(?:static\s+)?(?:inline\s+)?(?:virtual\s+)?(?:[\w\*&<>,\s]+)\s+(\w+)\s*\(',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, code, re.MULTILINE)
            if match:
                func_name = match.group(1)
                if '::' in func_name:
                    func_name = func_name.split('::')[-1]
                return func_name
        
        return "unknown"
    
    def build_call_chain(self, functions: List[Dict], call_path: List[str]) -> CallChain:
        """
        构建调用链
        
        Args:
            functions: 函数列表（每个包含 func 字段）
            call_path: 调用路径（函数名列表）
            
        Returns:
            CallChain 对象
        """
        # 创建函数信息映射
        func_map = {}
        for func_data in functions:
            code = func_data.get('func', '')
            name = self.extract_function_name(code)
            func_info = FunctionInfo(
                name=name,
                code=code,
                idx=func_data.get('idx')
            )
            func_map[name] = func_info
        
        # 按调用路径排序
        ordered_functions = []
        for name in call_path:
            if name in func_map:
                func_info = func_map[name]
                func_info.analyze()
                ordered_functions.append(func_info)
        
        return CallChain(
            functions=ordered_functions,
            depth=len(call_path),
            call_path=call_path
        )
    
    def create_fusion_plan(
        self,
        target_code: str,
        call_chain: CallChain,
        passing_method: str = "global"
    ) -> FusionPlan:
        """
        创建融合计划
        
        Args:
            target_code: 要融合的目标代码
            call_chain: 调用链
            passing_method: 变量传递方法 "global" 或 "parameter"
            
        Returns:
            FusionPlan 对象
        """
        # 使用 LLM 拆分代码
        n_parts = len(call_chain.functions)
        slice_result = self.splitter.split_code(
            target_code,
            n_parts,
            call_chain.function_names,
            passing_method
        )
        
        # 确定插入点
        insertion_points = []
        for i, (func, code_slice) in enumerate(zip(call_chain.functions, slice_result.slices)):
            if func.fusion_points:
                # 选择第一个融合点
                block_id = func.fusion_points[0]
            else:
                # 如果没有融合点，使用入口块
                block_id = func.cfg.entry_block_id if func.cfg else 0
            
            insertion_points.append((func.name, block_id, code_slice.code))
        
        return FusionPlan(
            target_code=target_code,
            call_chain=call_chain,
            slice_result=slice_result,
            insertion_points=insertion_points
        )
    
    def execute_fusion(self, plan: FusionPlan) -> Dict[str, str]:
        """
        执行融合
        
        Args:
            plan: 融合计划
            
        Returns:
            融合后的函数代码字典 {函数名: 代码}
        """
        fused_code = {}
        
        for func, (func_name, block_id, insert_code) in zip(
            plan.call_chain.functions, 
            plan.insertion_points
        ):
            if not insert_code.strip() or insert_code.strip() == "// empty slice":
                fused_code[func_name] = func.code
                continue
            
            # 在函数中插入代码
            fused = self._insert_code_into_function(func, block_id, insert_code)
            fused_code[func_name] = fused
        
        return fused_code
    
    def _insert_code_into_function(
        self, 
        func: FunctionInfo, 
        block_id: int, 
        insert_code: str
    ) -> str:
        """
        在函数的指定位置插入代码
        
        Args:
            func: 函数信息
            block_id: 目标基本块ID
            insert_code: 要插入的代码
            
        Returns:
            插入代码后的函数代码
        """
        code = func.code
        
        # 找到函数体真正开始的位置（跳过签名后的注释）
        brace_pos = self._find_function_body_start(code)
        if brace_pos == -1:
            return code
        
        # 如果是入口块或第一个融合点，在变量声明之后插入
        if block_id == func.cfg.entry_block_id or (func.fusion_points and block_id == func.fusion_points[0]):
            # 格式化插入代码
            insert_lines = insert_code.strip().split('\n')
            formatted_insert = '\n    '.join(insert_lines)
            
            # 找到变量声明块的末尾位置
            insert_pos = self._find_after_declarations(code, brace_pos)
            
            return (
                code[:insert_pos] + 
                f"\n    {formatted_insert}\n" +
                code[insert_pos:]
            )
        
        # 否则尝试找到对应的基本块位置
        # 这里简化处理，在函数中间插入
        return self._insert_at_middle(code, insert_code)
    
    def _find_function_body_start(self, code: str) -> int:
        """
        找到函数体真正开始的位置（跳过签名后的注释）
        
        处理以下格式：
        1. void func(...) { ... }
        2. void func(...) /* comment */ { ... }
        3. void func(...) /* {{{ */ { ... }  (PHP/Zend 风格)
        """
        # 首先找到函数签名的结束（最后一个 ) ）
        paren_count = 0
        paren_end = -1
        in_string = False
        in_comment = False
        
        i = 0
        while i < len(code):
            # 跳过注释
            if code[i:i+2] == '/*':
                end = code.find('*/', i + 2)
                if end != -1:
                    i = end + 2
                    continue
                i += 1
                continue
            elif code[i:i+2] == '//':
                end = code.find('\n', i + 2)
                if end != -1:
                    i = end + 1
                    continue
                break
            
            # 处理字符串
            if code[i] in '"\'':
                in_string = not in_string
            if in_string:
                i += 1
                continue
            
            if code[i] == '(':
                paren_count += 1
            elif code[i] == ')':
                paren_count -= 1
                if paren_count == 0:
                    paren_end = i
            
            i += 1
        
        if paren_end == -1:
            # 没找到参数列表，直接找第一个不在注释中的 {
            return self._find_brace_outside_comment(code, 0)
        
        # 从参数列表结束位置开始，找到第一个不在注释中的 {
        return self._find_brace_outside_comment(code, paren_end + 1)
    
    def _find_brace_outside_comment(self, code: str, start: int) -> int:
        """
        从指定位置开始，找到第一个不在注释中的 {
        
        策略：使用状态机跳过注释，找到真正的函数体开始
        """
        i = start
        while i < len(code):
            # 跳过空白
            while i < len(code) and code[i] in ' \t\n\r':
                i += 1
            
            if i >= len(code):
                break
            
            # 检查是否是注释开始
            if code[i:i+2] == '/*':
                # 找到注释结束位置
                end = code.find('*/', i + 2)
                if end == -1:
                    break
                i = end + 2
                continue
            elif code[i:i+2] == '//':
                # 跳过单行注释
                end = code.find('\n', i + 2)
                if end == -1:
                    break
                i = end + 1
                continue
            elif code[i] == '{':
                # 找到了函数体开始
                return i
            else:
                # 可能是其他关键字或字符
                i += 1
        
        # 备用方法：找到最后一个 */ 之后的第一个 {
        last_comment_end = code.rfind('*/')
        if last_comment_end != -1:
            next_brace = code.find('{', last_comment_end + 2)
            if next_brace != -1:
                return next_brace
        
        return code.find('{')
    
    def _find_after_declarations(self, code: str, brace_pos: int) -> int:
        """
        找到变量声明块之后的位置
        
        在 C89 中，变量声明必须在函数开头。
        我们需要在声明之后、第一个可执行语句之前插入代码。
        """
        # 从 { 之后开始分析
        body_start = brace_pos + 1
        
        # 简单策略：找到第一个非声明语句
        # 声明通常是：类型 变量名;  或 类型 变量名 = 值;
        
        lines = code[body_start:].split('\n')
        current_pos = body_start
        
        declaration_patterns = [
            r'^\s*(const\s+)?(unsigned\s+)?(static\s+)?(volatile\s+)?'
            r'(int|char|short|long|float|double|void|bool|Bool|'
            r'u8|u16|u32|u64|s8|s16|s32|s64|'
            r'uint8_t|uint16_t|uint32_t|uint64_t|'
            r'int8_t|int16_t|int32_t|int64_t|'
            r'size_t|ssize_t|'
            r'UINT|UINT8|UINT16|UINT32|UINT64|'
            r'BYTE|WORD|DWORD|BOOL|'
            r'GF_\w+|EFI_\w+|zval|zend_\w+|'
            r'\w+_t|\w+\s*\*)\s+\w+'
        ]
        
        import re
        decl_pattern = re.compile(declaration_patterns[0], re.IGNORECASE)
        
        last_decl_end = body_start
        
        for line in lines:
            stripped = line.strip()
            
            # 跳过空行和注释
            if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
                current_pos += len(line) + 1
                continue
            
            # 检查是否是变量声明
            if decl_pattern.match(stripped) and ';' in stripped and '(' not in stripped:
                # 这是一个声明行
                last_decl_end = current_pos + len(line) + 1
                current_pos += len(line) + 1
                continue
            
            # 遇到非声明语句，停止
            break
        
        # 如果找到了声明，在声明之后插入
        if last_decl_end > body_start:
            return last_decl_end
        
        # 否则在 { 之后插入
        return body_start
    
    def _insert_at_middle(self, func_code: str, insert_code: str) -> str:
        """
        在函数中间位置插入代码
        """
        # 找到函数体真正开始位置
        brace_start = self._find_function_body_start(func_code)
        brace_end = func_code.rfind('}')
        
        if brace_start == -1 or brace_end == -1:
            return func_code
        
        body = func_code[brace_start + 1:brace_end]
        lines = body.split('\n')
        
        # 在中间位置插入
        mid = len(lines) // 2
        
        insert_lines = insert_code.strip().split('\n')
        formatted_insert = '\n    '.join(insert_lines)
        
        lines.insert(mid, f"    {formatted_insert}")
        
        return func_code[:brace_start + 1] + '\n'.join(lines) + func_code[brace_end:]


def analyze_call_chain_group(group: Dict) -> Dict:
    """
    分析一个调用链组
    
    Args:
        group: 包含 functions, call_depth, longest_call_chain 的字典
        
    Returns:
        分析结果字典
    """
    functions = group.get('functions', [])
    call_depth = group.get('call_depth', 0)
    call_chain = group.get('longest_call_chain', [])
    
    # 分析每个函数
    analyzed_functions = []
    for func_data in functions:
        code = func_data.get('func', '')
        cfg = analyze_code_cfg(code)
        fusion_points = get_fusion_points(cfg)
        
        analyzed_functions.append({
            'idx': func_data.get('idx'),
            'name': cfg.function_name,
            'blocks_count': len(cfg.blocks),
            'fusion_points_count': len(fusion_points),
            'fusion_points': fusion_points,
        })
    
    return {
        'call_depth': call_depth,
        'call_chain': call_chain,
        'functions_count': len(functions),
        'analyzed_functions': analyzed_functions,
        'total_fusion_points': sum(f['fusion_points_count'] for f in analyzed_functions)
    }


if __name__ == "__main__":
    # 测试代码
    test_func1 = """
    void outer_func() {
        printf("Start\\n");
        middle_func();
        printf("End\\n");
    }
    """
    
    test_func2 = """
    void middle_func() {
        int x = 10;
        inner_func();
        x += 5;
    }
    """
    
    test_func3 = """
    void inner_func() {
        printf("Inner\\n");
    }
    """
    
    functions = [
        {'func': test_func1, 'idx': 1},
        {'func': test_func2, 'idx': 2},
        {'func': test_func3, 'idx': 3},
    ]
    
    engine = CodeFusionEngine()
    call_chain = engine.build_call_chain(
        functions,
        ['outer_func', 'middle_func', 'inner_func']
    )
    
    print(f"Call chain depth: {call_chain.depth}")
    print(f"Functions: {call_chain.function_names}")
    print(f"Total fusion points: {call_chain.get_total_fusion_points()}")

