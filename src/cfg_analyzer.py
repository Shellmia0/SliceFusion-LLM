#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
控制流图 (CFG) 分析器

使用正则表达式和简单的词法分析来构建 C/C++ 代码的控制流图。
"""

import re
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
import networkx as nx


@dataclass
class BasicBlock:
    """基本块"""
    id: int
    name: str
    statements: List[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    is_entry: bool = False
    is_exit: bool = False
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, BasicBlock):
            return self.id == other.id
        return False
    
    def get_code(self) -> str:
        """获取基本块的代码"""
        return '\n'.join(self.statements)


@dataclass
class ControlFlowGraph:
    """控制流图"""
    function_name: str
    blocks: Dict[int, BasicBlock] = field(default_factory=dict)
    edges: List[Tuple[int, int]] = field(default_factory=list)
    entry_block_id: Optional[int] = None
    exit_block_ids: List[int] = field(default_factory=list)
    
    def add_block(self, block: BasicBlock) -> None:
        """添加基本块"""
        self.blocks[block.id] = block
        if block.is_entry:
            self.entry_block_id = block.id
        if block.is_exit:
            self.exit_block_ids.append(block.id)
    
    def add_edge(self, from_id: int, to_id: int) -> None:
        """添加边"""
        if (from_id, to_id) not in self.edges:
            self.edges.append((from_id, to_id))
    
    def get_successors(self, block_id: int) -> List[int]:
        """获取后继节点"""
        return [to_id for from_id, to_id in self.edges if from_id == block_id]
    
    def get_predecessors(self, block_id: int) -> List[int]:
        """获取前驱节点"""
        return [from_id for from_id, to_id in self.edges if to_id == block_id]
    
    def to_networkx(self) -> nx.DiGraph:
        """转换为 NetworkX 图"""
        G = nx.DiGraph()
        for block_id, block in self.blocks.items():
            G.add_node(block_id, name=block.name, 
                      is_entry=block.is_entry, 
                      is_exit=block.is_exit)
        for from_id, to_id in self.edges:
            G.add_edge(from_id, to_id)
        return G


class CFGAnalyzer:
    """控制流图分析器"""
    
    # 控制流关键字
    CONTROL_KEYWORDS = {
        'if', 'else', 'while', 'for', 'do', 'switch', 'case', 
        'default', 'break', 'continue', 'return', 'goto'
    }
    
    def __init__(self):
        self.block_counter = 0
    
    def _new_block_id(self) -> int:
        """生成新的块ID"""
        self.block_counter += 1
        return self.block_counter
    
    def _reset(self):
        """重置计数器"""
        self.block_counter = 0
    
    def _remove_comments(self, code: str) -> str:
        """移除注释"""
        # 移除单行注释
        code = re.sub(r'//.*?\n', '\n', code)
        # 移除多行注释
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        return code
    
    def _extract_function_body(self, code: str) -> str:
        """提取函数体（花括号内的内容）"""
        # 找到第一个 { 的位置
        brace_start = code.find('{')
        if brace_start == -1:
            return ""
        
        # 匹配对应的 }
        brace_count = 0
        for i, char in enumerate(code[brace_start:], brace_start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return code[brace_start + 1:i]
        
        return code[brace_start + 1:]
    
    def _tokenize_statements(self, code: str) -> List[str]:
        """将代码分割为语句"""
        statements = []
        current = ""
        brace_count = 0
        paren_count = 0
        in_string = False
        string_char = None
        
        i = 0
        while i < len(code):
            char = code[i]
            
            # 处理字符串
            if char in '"\'':
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char and (i == 0 or code[i-1] != '\\'):
                    in_string = False
                current += char
                i += 1
                continue
            
            if in_string:
                current += char
                i += 1
                continue
            
            # 处理花括号
            if char == '{':
                brace_count += 1
                current += char
            elif char == '}':
                brace_count -= 1
                current += char
                if brace_count == 0 and current.strip():
                    statements.append(current.strip())
                    current = ""
            elif char == '(':
                paren_count += 1
                current += char
            elif char == ')':
                paren_count -= 1
                current += char
            elif char == ';' and brace_count == 0 and paren_count == 0:
                current += char
                if current.strip():
                    statements.append(current.strip())
                current = ""
            elif char == '\n':
                current += ' '
            else:
                current += char
            
            i += 1
        
        if current.strip():
            statements.append(current.strip())
        
        return statements
    
    def _is_control_statement(self, stmt: str) -> Tuple[bool, str]:
        """检查是否是控制流语句"""
        stmt_lower = stmt.strip().lower()
        
        for keyword in self.CONTROL_KEYWORDS:
            if stmt_lower.startswith(keyword + ' ') or \
               stmt_lower.startswith(keyword + '(') or \
               stmt_lower == keyword:
                return True, keyword
        
        return False, ""
    
    def _extract_function_name(self, func_code: str) -> str:
        """从函数代码中提取函数名"""
        code = self._remove_comments(func_code)
        
        patterns = [
            # C++ 成员函数
            r'(?:[\w\s\*&<>,]+?)\s+(\w+::~?\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*\{',
            r'^[\s]*(\w+::~?\w+)\s*\([^)]*\)\s*\{',
            # 普通 C 函数
            r'(?:[\w\s\*&<>,]+?)\s+(\w+)\s*\([^)]*\)\s*\{',
            # 简单模式
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
    
    def analyze_function(self, func_code: str, func_name: str = None) -> ControlFlowGraph:
        """
        分析函数代码，构建控制流图
        
        Args:
            func_code: 函数代码
            func_name: 函数名（可选，如果不提供则自动提取）
            
        Returns:
            ControlFlowGraph 对象
        """
        self._reset()
        
        # 自动提取函数名
        if func_name is None:
            func_name = self._extract_function_name(func_code)
        
        cfg = ControlFlowGraph(function_name=func_name)
        
        # 预处理代码
        code = self._remove_comments(func_code)
        body = self._extract_function_body(code)
        
        if not body:
            # 空函数
            entry = BasicBlock(
                id=self._new_block_id(),
                name="entry",
                statements=["// empty function"],
                is_entry=True,
                is_exit=True
            )
            cfg.add_block(entry)
            return cfg
        
        # 分割语句
        statements = self._tokenize_statements(body)
        
        if not statements:
            entry = BasicBlock(
                id=self._new_block_id(),
                name="entry",
                statements=["// empty function"],
                is_entry=True,
                is_exit=True
            )
            cfg.add_block(entry)
            return cfg
        
        # 简单分析：将语句分组到基本块
        blocks = self._build_basic_blocks(statements)
        
        # 添加块到 CFG
        for i, block in enumerate(blocks):
            block.is_entry = (i == 0)
            # 检查是否是退出块
            if block.statements:
                last_stmt = block.statements[-1].strip().lower()
                if last_stmt.startswith('return'):
                    block.is_exit = True
            cfg.add_block(block)
        
        # 如果最后一个块不是退出块，将其标记为退出
        if blocks and not blocks[-1].is_exit:
            blocks[-1].is_exit = True
            cfg.exit_block_ids.append(blocks[-1].id)
        
        # 构建边
        self._build_edges(cfg, blocks)
        
        return cfg
    
    def _build_basic_blocks(self, statements: List[str]) -> List[BasicBlock]:
        """构建基本块列表"""
        blocks = []
        current_statements = []
        
        for stmt in statements:
            is_control, keyword = self._is_control_statement(stmt)
            
            if is_control:
                # 控制语句之前的语句形成一个块
                if current_statements:
                    block = BasicBlock(
                        id=self._new_block_id(),
                        name=f"bb_{self.block_counter}",
                        statements=current_statements.copy()
                    )
                    blocks.append(block)
                    current_statements = []
                
                # 控制语句本身形成一个块
                block = BasicBlock(
                    id=self._new_block_id(),
                    name=f"bb_{self.block_counter}_{keyword}",
                    statements=[stmt]
                )
                blocks.append(block)
            else:
                current_statements.append(stmt)
        
        # 处理剩余语句
        if current_statements:
            block = BasicBlock(
                id=self._new_block_id(),
                name=f"bb_{self.block_counter}",
                statements=current_statements
            )
            blocks.append(block)
        
        return blocks
    
    def _build_edges(self, cfg: ControlFlowGraph, blocks: List[BasicBlock]) -> None:
        """构建控制流边"""
        for i, block in enumerate(blocks):
            if not block.statements:
                continue
            
            last_stmt = block.statements[-1].strip().lower()
            
            # return 语句没有后继
            if last_stmt.startswith('return'):
                continue
            
            # break/continue 需要特殊处理（简化版本：跳到下一个块）
            if last_stmt.startswith('break') or last_stmt.startswith('continue'):
                # 简化处理：连接到下一个块
                if i + 1 < len(blocks):
                    cfg.add_edge(block.id, blocks[i + 1].id)
                continue
            
            # goto 语句（简化处理）
            if last_stmt.startswith('goto'):
                if i + 1 < len(blocks):
                    cfg.add_edge(block.id, blocks[i + 1].id)
                continue
            
            # 条件语句：可能有两个分支
            is_control, keyword = self._is_control_statement(block.statements[-1])
            if is_control and keyword in ('if', 'while', 'for', 'switch'):
                # 连接到下一个块（true 分支）
                if i + 1 < len(blocks):
                    cfg.add_edge(block.id, blocks[i + 1].id)
                # 寻找 else 分支或循环结束后的块
                # 简化处理：如果有下下个块，也连接
                if i + 2 < len(blocks):
                    cfg.add_edge(block.id, blocks[i + 2].id)
            else:
                # 普通语句：顺序执行
                if i + 1 < len(blocks):
                    cfg.add_edge(block.id, blocks[i + 1].id)


def analyze_code_cfg(func_code: str, func_name: str = "unknown") -> ControlFlowGraph:
    """
    分析代码的控制流图
    
    Args:
        func_code: 函数代码
        func_name: 函数名
        
    Returns:
        ControlFlowGraph 对象
    """
    analyzer = CFGAnalyzer()
    return analyzer.analyze_function(func_code, func_name)


def visualize_cfg(cfg: ControlFlowGraph, output_file: str = None) -> str:
    """
    可视化控制流图（返回 DOT 格式）
    
    Args:
        cfg: 控制流图
        output_file: 输出文件路径（可选）
        
    Returns:
        DOT 格式字符串
    """
    lines = [f'digraph "{cfg.function_name}" {{']
    lines.append('  node [shape=box];')
    
    for block_id, block in cfg.blocks.items():
        # 节点标签
        label = f"{block.name}\\n"
        for stmt in block.statements[:3]:  # 只显示前3条语句
            # 转义特殊字符
            stmt_escaped = stmt.replace('"', '\\"').replace('\n', '\\n')
            if len(stmt_escaped) > 40:
                stmt_escaped = stmt_escaped[:37] + "..."
            label += stmt_escaped + "\\n"
        
        # 节点样式
        style = ""
        if block.is_entry:
            style = ', style=filled, fillcolor=lightgreen'
        elif block.is_exit:
            style = ', style=filled, fillcolor=lightcoral'
        
        lines.append(f'  {block_id} [label="{label}"{style}];')
    
    # 边
    for from_id, to_id in cfg.edges:
        lines.append(f'  {from_id} -> {to_id};')
    
    lines.append('}')
    
    dot_str = '\n'.join(lines)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(dot_str)
    
    return dot_str


if __name__ == "__main__":
    # 测试代码
    test_code = """
    int factorial(int n) {
        if (n <= 1) {
            return 1;
        }
        int result = 1;
        for (int i = 2; i <= n; i++) {
            result *= i;
        }
        return result;
    }
    """
    
    cfg = analyze_code_cfg(test_code, "factorial")
    print(f"Function: {cfg.function_name}")
    print(f"Blocks: {len(cfg.blocks)}")
    print(f"Edges: {len(cfg.edges)}")
    print("\nDOT representation:")
    print(visualize_cfg(cfg))

