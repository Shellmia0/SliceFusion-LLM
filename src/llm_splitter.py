#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 代码拆分器

调用大语言模型将一段代码拆分为多个片段，以便插入到调用链中的多个函数中。
"""

import os
import json
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class CodeSlice:
    """代码片段"""
    index: int
    code: str
    description: str
    dependencies: List[str]  # 依赖的变量/状态
    outputs: List[str]  # 输出的变量/状态


@dataclass
class SliceResult:
    """拆分结果"""
    original_code: str
    slices: List[CodeSlice]
    shared_state: Dict[str, str]  # 共享状态变量名 -> 类型
    global_declarations: str  # 全局变量声明代码
    setup_code: str  # 初始化代码
    cleanup_code: str  # 清理代码
    passing_method: str = "global"  # 变量传递方法: "global" 或 "parameter"
    parameter_struct: str = ""  # 参数传递时使用的结构体定义


class LLMCodeSplitter:
    """LLM 代码拆分器"""

    # 变量传递方法
    METHOD_GLOBAL = "global"      # 全局变量方法
    METHOD_PARAMETER = "parameter"  # 参数传递方法

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """
        初始化 LLM 拆分器

        Args:
            api_key: API 密钥（默认从环境变量获取）
            base_url: API 基础 URL
            model: 模型名称
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = model or "qwen-plus"  # 可选: qwen-plus, qwen-turbo, qwen-max

        if not self.api_key:
            raise ValueError("API key not found. Please set DASHSCOPE_API_KEY environment variable.")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _create_split_prompt(self, code: str, n_parts: int, function_names: List[str]) -> str:
        """
        创建代码拆分的提示词

        Args:
            code: 要拆分的代码
            n_parts: 拆分为几个部分
            function_names: 调用链中的函数名列表
        """
        prompt = f"""你是一个代码分析专家。请将以下代码拆分为 {n_parts} 个相互依赖的片段。

这些片段将被插入到一个调用链中的 {n_parts} 个函数中：
调用链：{' -> '.join(function_names)}

【重要】由于每个片段在不同的函数中执行，局部变量无法直接传递！
你必须：
1. 将需要跨函数共享的变量声明为全局变量（放在 shared_state 中）
2. 第一个片段负责初始化全局变量
3. 后续片段使用这些全局变量
4. 最后一个片段执行最终操作

要求：
1. 每个片段应该是语义完整的代码块
2. 片段之间通过【全局变量】传递状态，不能依赖局部变量
3. 按照调用顺序，第一个片段在调用链最外层函数中执行，最后一个片段在最内层函数中执行
4. 所有片段按顺序执行后，效果应该与原始代码相同
5. shared_state 中声明所有需要跨函数共享的变量

原始代码：
```c
{code}
```

请按以下 JSON 格式返回结果：
```json
{{
    "shared_state": {{
        "变量名": "类型（如 int, char*, etc.）"
    }},
    "global_declarations": "全局变量声明代码，如：static int g_secret; static int g_key;",
    "slices": [
        {{
            "index": 0,
            "function": "函数名",
            "code": "代码片段（使用全局变量，如 g_secret = 42;）",
            "description": "描述这段代码做什么",
            "dependencies": ["依赖的全局变量"],
            "outputs": ["输出/修改的全局变量"]
        }}
    ],
    "cleanup_code": "清理代码（如释放内存、重置全局变量等）"
}}
```

示例：如果原始代码是 `int secret = 42; int key = secret ^ 0xABCD; printf("key=%d", key);`
拆分为3个片段应该是：
- shared_state: {{"g_secret": "int", "g_key": "int"}}
- global_declarations: "static int g_secret; static int g_key;"
- 片段1: "g_secret = 42;"
- 片段2: "g_key = g_secret ^ 0xABCD;"
- 片段3: "printf(\\"key=%d\\", g_key);"

只返回 JSON，不要有其他内容。
"""
        return prompt

    def _create_parameter_split_prompt(self, code: str, n_parts: int, function_names: List[str]) -> str:
        """
        创建使用参数传递方法的代码拆分提示词
        """
        prompt = f"""你是一个代码分析专家。请将以下代码拆分为 {n_parts} 个相互依赖的片段。

这些片段将被插入到一个调用链中的 {n_parts} 个函数中：
调用链：{' -> '.join(function_names)}

【重要】使用参数传递方法！
你需要：
1. 定义一个结构体来保存共享状态
2. 每个函数需要添加一个指向该结构体的指针参数
3. 每个片段通过这个结构体指针访问和修改共享状态

要求：
1. 定义结构体 `FusionState` 包含所有需要共享的变量
2. 每个函数添加参数 `FusionState* fusion_state`
3. 片段中通过 `fusion_state->变量名` 访问变量
4. 调用下层函数时传递 `fusion_state` 指针

原始代码：
```c
{code}
```

请按以下 JSON 格式返回结果：
```json
{{{{
    "shared_state": {{{{
        "变量名": "类型"
    }}}},
    "parameter_struct": "typedef struct {{ int secret; int key; }} FusionState;",
    "slices": [
        {{{{
            "index": 0,
            "function": "函数名",
            "code": "代码片段（使用 fusion_state->secret = 42;）",
            "description": "描述",
            "dependencies": ["依赖的变量"],
            "outputs": ["输出的变量"]
        }}}}
    ],
    "init_code": "FusionState fusion_state_data; memset(&fusion_state_data, 0, sizeof(fusion_state_data)); FusionState* fusion_state = &fusion_state_data;"
}}}}
```

示例：如果原始代码是 `int secret = 42; int key = secret ^ 0xABCD; printf("key=%d", key);`
- parameter_struct: "typedef struct {{ int secret; int key; }} FusionState;"
- 片段1: "fusion_state->secret = 42;"
- 片段2: "fusion_state->key = fusion_state->secret ^ 0xABCD;"
- 片段3: "printf(\\"key=%d\\", fusion_state->key);"

只返回 JSON，不要有其他内容。
"""
        return prompt

    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        """
        解析 LLM 的响应
        """
        # 尝试提取 JSON
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def split_code(self, code: str, n_parts: int, function_names: List[str],
                   method: str = "global") -> SliceResult:
        """
        将代码拆分为多个片段

        Args:
            code: 要拆分的代码
            n_parts: 拆分为几个部分
            function_names: 调用链中的函数名列表
            method: 变量传递方法 "global"（全局变量）或 "parameter"（参数传递）

        Returns:
            SliceResult 对象
        """
        if n_parts <= 0:
            raise ValueError("n_parts must be positive")

        if method not in [self.METHOD_GLOBAL, self.METHOD_PARAMETER]:
            method = self.METHOD_GLOBAL

        if n_parts == 1:
            # 不需要拆分
            return SliceResult(
                original_code=code,
                slices=[CodeSlice(
                    index=0,
                    code=code,
                    description="Original code",
                    dependencies=[],
                    outputs=[]
                )],
                shared_state={},
                global_declarations="",
                setup_code="",
                cleanup_code="",
                passing_method=method,
                parameter_struct=""
            )

        # 根据方法选择不同的 prompt
        if method == self.METHOD_PARAMETER:
            prompt = self._create_parameter_split_prompt(code, n_parts, function_names)
        else:
            prompt = self._create_split_prompt(code, n_parts, function_names)

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的代码分析和重构专家，擅长将代码拆分为多个相互依赖的片段。请只返回 JSON 格式的结果。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096,
                extra_body={"enable_thinking": False},
            )

            response_text = completion.choices[0].message.content

            # 解析响应
            result_dict = self._parse_llm_response(response_text)

            if not result_dict:
                print(f"Warning: Failed to parse LLM response. Using fallback splitting.")
                return self._fallback_split(code, n_parts, function_names)

            # 构建结果
            slices = []
            for slice_data in result_dict.get("slices", []):
                slices.append(CodeSlice(
                    index=slice_data.get("index", 0),
                    code=slice_data.get("code", ""),
                    description=slice_data.get("description", ""),
                    dependencies=slice_data.get("dependencies", []),
                    outputs=slice_data.get("outputs", [])
                ))

            return SliceResult(
                original_code=code,
                slices=slices,
                shared_state=result_dict.get("shared_state", {}),
                global_declarations=result_dict.get("global_declarations", ""),
                setup_code=result_dict.get("setup_code", result_dict.get("init_code", "")),
                cleanup_code=result_dict.get("cleanup_code", ""),
                passing_method=method,
                parameter_struct=result_dict.get("parameter_struct", "")
            )

        except Exception as e:
            print(f"Warning: LLM call failed: {e}. Using fallback splitting.")
            return self._fallback_split(code, n_parts, function_names, method)

    def _fallback_split(self, code: str, n_parts: int, function_names: List[str],
                        method: str = "global") -> SliceResult:
        """
        备用拆分方法（简单地按语句数量均分）
        """
        # 简单地按行分割
        lines = [line for line in code.strip().split('\n') if line.strip()]

        if len(lines) < n_parts:
            # 如果行数少于分片数，每行一个分片
            slices = []
            for i, line in enumerate(lines):
                slices.append(CodeSlice(
                    index=i,
                    code=line,
                    description=f"Part {i+1}",
                    dependencies=[],
                    outputs=[]
                ))
            # 补充空分片
            while len(slices) < n_parts:
                slices.append(CodeSlice(
                    index=len(slices),
                    code="// empty slice",
                    description=f"Part {len(slices)+1} (empty)",
                    dependencies=[],
                    outputs=[]
                ))
        else:
            # 均分
            chunk_size = len(lines) // n_parts
            slices = []
            for i in range(n_parts):
                start = i * chunk_size
                end = start + chunk_size if i < n_parts - 1 else len(lines)
                slice_code = '\n'.join(lines[start:end])
                slices.append(CodeSlice(
                    index=i,
                    code=slice_code,
                    description=f"Part {i+1}",
                    dependencies=[],
                    outputs=[]
                ))

        # 根据方法生成不同的变量传递代码
        if method == self.METHOD_PARAMETER:
            param_info = self._generate_fallback_parameters(code)
            return SliceResult(
                original_code=code,
                slices=slices,
                shared_state=param_info.get("shared_state", {}),
                global_declarations="",
                setup_code=param_info.get("init_code", ""),
                cleanup_code="",
                passing_method=method,
                parameter_struct=param_info.get("parameter_struct", "")
            )
        else:
            # 全局变量方法
            global_decl = self._generate_fallback_globals(code)
            return SliceResult(
                original_code=code,
                slices=slices,
                shared_state=global_decl.get("shared_state", {}),
                global_declarations=global_decl.get("declarations", ""),
                setup_code="",
                cleanup_code="",
                passing_method=method,
                parameter_struct=""
            )

    def _generate_fallback_parameters(self, code: str) -> Dict:
        """
        为 fallback 拆分生成参数传递所需的结构体
        """
        import re

        # 匹配简单的变量声明: type name = value;
        var_pattern = r'\b(int|char|float|double|long|short|unsigned)\s+(\w+)\s*='
        matches = re.findall(var_pattern, code)

        shared_state = {}
        struct_fields = []

        for var_type, var_name in matches:
            shared_state[var_name] = var_type
            struct_fields.append(f"    {var_type} {var_name};")

        if struct_fields:
            parameter_struct = "typedef struct {\n" + "\n".join(struct_fields) + "\n} FusionState;"
        else:
            parameter_struct = "typedef struct { int _placeholder; } FusionState;"

        init_code = "FusionState fusion_state_data; memset(&fusion_state_data, 0, sizeof(fusion_state_data)); FusionState* fusion_state = &fusion_state_data;"

        return {
            "shared_state": shared_state,
            "parameter_struct": parameter_struct,
            "init_code": init_code
        }

    def _generate_fallback_globals(self, code: str) -> Dict:
        """
        为 fallback 拆分生成全局变量声明
        分析代码中的变量声明，转换为全局变量
        """
        import re

        # 匹配简单的变量声明: type name = value;
        var_pattern = r'\b(int|char|float|double|long|short|unsigned)\s+(\w+)\s*='
        matches = re.findall(var_pattern, code)

        shared_state = {}
        declarations = []

        for var_type, var_name in matches:
            global_name = f"g_{var_name}"
            shared_state[global_name] = var_type
            declarations.append(f"static {var_type} {global_name};")

        return {
            "shared_state": shared_state,
            "declarations": "\n".join(declarations)
        }


def split_code_for_call_chain(
    code: str,
    call_chain: List[str],
    api_key: str = None
) -> SliceResult:
    """
    将代码拆分以适配调用链

    Args:
        code: 要拆分的代码
        call_chain: 调用链（函数名列表）
        api_key: API 密钥（可选）

    Returns:
        SliceResult 对象
    """
    splitter = LLMCodeSplitter(api_key=api_key)
    n_parts = len(call_chain)
    return splitter.split_code(code, n_parts, call_chain)


class CodeFusionGenerator:
    """代码融合生成器"""

    def __init__(self, splitter: LLMCodeSplitter = None):
        """
        初始化融合生成器

        Args:
            splitter: LLM 拆分器实例
        """
        self.splitter = splitter or LLMCodeSplitter()

    def _create_fusion_prompt(
        self,
        target_code: str,
        call_chain_functions: List[Dict],
        slice_result: SliceResult
    ) -> str:
        """
        创建代码融合的提示词
        """
        functions_desc = "\n".join([
            f"{i+1}. {f['name']}:\n```c\n{f['code']}\n```"
            for i, f in enumerate(call_chain_functions)
        ])

        slices_desc = "\n".join([
            f"片段 {s.index + 1} (插入到 {call_chain_functions[s.index]['name']}):\n```c\n{s.code}\n```"
            for s in slice_result.slices
        ])

        prompt = f"""请将以下代码片段融合到对应的函数中。

调用链中的函数：
{functions_desc}

要插入的代码片段：
{slices_desc}

共享状态变量：
{json.dumps(slice_result.shared_state, indent=2)}

初始化代码：
```c
{slice_result.setup_code}
```

要求：
1. 在每个函数的合适位置插入对应的代码片段
2. 正确处理共享状态的传递
3. 保持原函数的功能不变

**关键语法约束（必须严格遵守）：**
- 返回的每个函数必须是**完整的、语法正确的C函数定义**，包含完整的花括号 {{}} 匹配
- **不要在 switch-case 语句的 case 标签之前插入代码**，应插入到具体的 case 分支内部或 switch 语句之外
- **不要在注释块内部插入代码**
- **不要截断函数**，必须包含从函数签名到最后一个 '}}' 的完整代码
- 所有圆括号 ()、花括号 {{}}、方括号 [] 必须正确匹配
- 如果代码片段引用了共享变量（如全局变量），确保在 global_declarations 中声明它们

请按以下 JSON 格式返回每个函数融合后的代码：
```json
{{
    "fused_functions": [
        {{
            "name": "函数名",
            "code": "融合后的完整函数代码"
        }}
    ],
    "global_declarations": "需要添加的全局声明（如共享状态变量）"
}}
```

只返回 JSON，不要有其他内容。
"""
        return prompt

    def generate_fused_code(
        self,
        target_code: str,
        call_chain_functions: List[Dict],
        slice_result: SliceResult = None
    ) -> Dict:
        """
        生成融合后的代码

        Args:
            target_code: 要融合的目标代码
            call_chain_functions: 调用链函数列表，每个元素包含 name 和 code
            slice_result: 代码拆分结果（可选，如果不提供则自动拆分）

        Returns:
            融合结果字典
        """
        if slice_result is None:
            function_names = [f['name'] for f in call_chain_functions]
            slice_result = self.splitter.split_code(
                target_code,
                len(call_chain_functions),
                function_names
            )

        prompt = self._create_fusion_prompt(
            target_code,
            call_chain_functions,
            slice_result
        )

        try:
            completion = self.splitter.client.chat.completions.create(
                model=self.splitter.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的代码融合专家，擅长将代码片段安全地插入到现有函数中。请只返回 JSON 格式的结果。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096,
                extra_body={"enable_thinking": False},
            )

            response_text = completion.choices[0].message.content
            result_dict = self.splitter._parse_llm_response(response_text)

            if result_dict:
                return result_dict
            else:
                return self._fallback_fusion(call_chain_functions, slice_result)

        except Exception as e:
            print(f"Warning: LLM fusion call failed: {e}. Using fallback fusion.")
            return self._fallback_fusion(call_chain_functions, slice_result)

    def _fallback_fusion(
        self,
        call_chain_functions: List[Dict],
        slice_result: SliceResult
    ) -> Dict:
        """
        备用融合方法
        """
        fused_functions = []

        for i, func in enumerate(call_chain_functions):
            if i < len(slice_result.slices):
                slice_code = slice_result.slices[i].code
                # 简单地在函数开头插入代码
                fused_code = self._insert_code_at_start(func['code'], slice_code)
            else:
                fused_code = func['code']

            fused_functions.append({
                "name": func['name'],
                "code": fused_code
            })

        return {
            "fused_functions": fused_functions,
            "global_declarations": ""
        }

    def _insert_code_at_start(self, func_code: str, insert_code: str) -> str:
        """
        在函数体开头插入代码
        """
        # 找到函数体开始的 {
        brace_pos = func_code.find('{')
        if brace_pos == -1:
            return func_code

        # 在 { 后插入代码
        return (
            func_code[:brace_pos + 1] +
            f"\n    {insert_code}\n" +
            func_code[brace_pos + 1:]
        )


if __name__ == "__main__":
    # 测试代码
    test_code = """
    int secret = 42;
    int key = secret ^ 0xFF;
    printf("Key: %d\\n", key);
    """

    call_chain = ["outer_func", "middle_func", "inner_func"]

    try:
        result = split_code_for_call_chain(test_code, call_chain)
        print(f"Split into {len(result.slices)} slices:")
        for slice in result.slices:
            print(f"\nSlice {slice.index}:")
            print(f"  Code: {slice.code}")
            print(f"  Description: {slice.description}")
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure DASHSCOPE_API_KEY is set in environment variables.")

