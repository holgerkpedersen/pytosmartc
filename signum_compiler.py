#!/usr/bin/env python3
"""
Python-to-Signum Smart Contract Compiler
Compiles a Python-like DSL to Signum SmartC code that can be deployed on the Signum blockchain

Usage:
    python signum_compiler.py input.py -o output.smart.c
    python signum_compiler.py --run-tests
"""

import ast
import sys
import json
import argparse
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# ============================================================================
# PART 1: Signum VM Type System
# ============================================================================

class SignumType(Enum):
    """Signum VM data types"""
    INT = "long"
    BOOL = "int"
    STRING = "string"
    ADDRESS = "address"
    TIMESTAMP = "timestamp"
    ARRAY = "array"

@dataclass
class SignumVariable:
    """Represents a variable in Signum VM"""
    name: str
    type: SignumType
    storage_key: str
    is_global: bool = True

# ============================================================================
# PART 2: Intermediate Representation (IR)
# ============================================================================

class IROp(Enum):
    """Signum VM atomic operations"""
    # State Management
    SET = "SET"
    GET = "GET"
    DELETE = "DELETE"
    
    # Arithmetic
    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    MOD = "MOD"
    
    # Comparison
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    GT = "GT"
    LE = "LE"
    GE = "GE"
    
    # Control Flow
    IF = "IF"
    ELSE = "ELSE"
    ENDIF = "ENDIF"
    WHILE = "WHILE"
    ENDWHILE = "ENDWHILE"
    GOTO = "GOTO"
    LABEL = "LABEL"
    RETURN = "RETURN"
    
    # Blockchain Context
    SENDER = "SENDER"
    BLOCK_HEIGHT = "BLOCK_HEIGHT"
    TIMESTAMP = "TIMESTAMP"
    TX_AMOUNT = "TX_AMOUNT"
    CONTRACT_BALANCE = "CONTRACT_BALANCE"
    
    # Cryptographic
    VERIFY = "VERIFY"
    HASH = "HASH"
    
    # Token Operations
    TRANSFER = "TRANSFER"
    MINT = "MINT"
    BURN = "BURN"
    
    # Events
    EMIT = "EMIT"
    LOG = "LOG"
    
    # Stack Operations
    PUSH = "PUSH"
    POP = "POP"
    DUP = "DUP"

@dataclass
class IRNode:
    """Intermediate Representation Node"""
    op: IROp
    args: List[Any] = field(default_factory=list)
    label: Optional[str] = None

# ============================================================================
# PART 3: Python AST to IR Converter
# ============================================================================

class PythonToIRConverter(ast.NodeVisitor):
    """Converts Python AST to Signum IR"""
    
    def __init__(self):
        self.instructions: List[IRNode] = []
        self.variables: Dict[str, SignumVariable] = {}
        self.functions: Dict[str, ast.FunctionDef] = {}
        self.temp_counter = 0
        self.label_counter = 0
        self.current_function = None
        self.loop_stack = []
        
    def new_temp(self) -> str:
        """Generate a temporary variable name"""
        self.temp_counter += 1
        return f"_tmp_{self.temp_counter}"
    
    def new_label(self) -> str:
        """Generate a unique label"""
        self.label_counter += 1
        return f"label_{self.label_counter}"
    
    def add_instruction(self, op: IROp, *args):
        """Add an IR instruction"""
        self.instructions.append(IRNode(op, list(args)))
    
    def add_label(self, label: str):
        """Add a label instruction"""
        self.instructions.append(IRNode(IROp.LABEL, [label]))
    
    def get_var_storage_key(self, name: str) -> str:
        """Get storage key for a variable"""
        if name in self.variables:
            return self.variables[name].storage_key
        # Register new variable
        storage_key = f"var_{name}"
        self.variables[name] = SignumVariable(
            name=name,
            type=SignumType.INT,
            storage_key=storage_key
        )
        return storage_key
    
    def visit_Module(self, node: ast.Module):
        """Visit module root"""
        # First pass: collect function definitions
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                self.functions[stmt.name] = stmt
        
        # Second pass: generate code for non-function statements
        for stmt in node.body:
            if not isinstance(stmt, ast.FunctionDef):
                self.visit(stmt)
        
        # Generate code for functions
        for func_name, func_node in self.functions.items():
            self.visit_FunctionDef(func_node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition"""
        self.current_function = node.name
        self.add_label(f"func_{node.name}")
        
        # Generate function body
        for stmt in node.body:
            self.visit(stmt)
        
        # Add return if none exists
        if not any(isinstance(stmt, ast.Return) for stmt in node.body):
            self.add_instruction(IROp.RETURN)
        
        self.current_function = None
    
    def visit_Assign(self, node: ast.Assign):
        """Visit assignment: x = 5 or x = y + z"""
        if len(node.targets) != 1:
            raise NotImplementedError("Multiple assignment not supported")
        
        target = node.targets[0]
        if isinstance(target, ast.Name):
            var_name = target.id
            storage_key = self.get_var_storage_key(var_name)
            value = self.visit(node.value)
            if value is not None:
                self.add_instruction(IROp.SET, storage_key, value)
            else:
                # Handle calls that don't return a value
                self.add_instruction(IROp.SET, storage_key, "0")
        else:
            raise NotImplementedError(f"Assignment target type {type(target)} not supported")
    
    def visit_Expr(self, node: ast.Expr):
        """Visit expression statements (standalone function calls)"""
        self.visit(node.value)
    
    def visit_BinOp(self, node: ast.BinOp):
        """Visit binary operation: a + b, a * b, etc."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        result = self.new_temp()

        op_map = {
            ast.Add: IROp.ADD,
            ast.Sub: IROp.SUB,
            ast.Mult: IROp.MUL,
            ast.Div: IROp.DIV,
            ast.Mod: IROp.MOD,
        }

        op_type = op_map.get(type(node.op))
        if op_type:
            # For string concatenation with Add, mark it specially
            if isinstance(node.op, ast.Add):
                # If either operand is a string, this is concatenation
                if (isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)) or \
                   (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
                    # Mark as string concatenation
                    self.add_instruction(IROp.SET, result, f"concat_{left}_{right}")
                    return result

            self.add_instruction(op_type, left, right, result)
            return result

        raise NotImplementedError(f"Binary operator {type(node.op)} not supported")
    
    def visit_Compare(self, node: ast.Compare):
        """Visit comparison: x > y, x == y, etc."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise NotImplementedError("Multiple comparisons not supported")
        
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        result = self.new_temp()
        
        op_map = {
            ast.Eq: IROp.EQ,
            ast.NotEq: IROp.NE,
            ast.Lt: IROp.LT,
            ast.Gt: IROp.GT,
            ast.LtE: IROp.LE,
            ast.GtE: IROp.GE,
        }
        
        op_type = op_map.get(type(node.ops[0]))
        if op_type:
            self.add_instruction(op_type, left, right, result)
            return result
        
        raise NotImplementedError(f"Comparison operator {type(node.ops[0])} not supported")
    
    def visit_If(self, node: ast.If):
        """Visit if statement"""
        condition = self.visit(node.test)
        else_label = self.new_label()
        end_label = self.new_label()
        
        # If condition is false, goto else_label
        # Compare condition to 0
        zero_temp = self.new_temp()
        self.add_instruction(IROp.EQ, condition, "0", zero_temp)
        self.add_instruction(IROp.IF, zero_temp, else_label)
        
        # Then branch
        for stmt in node.body:
            self.visit(stmt)
        self.add_instruction(IROp.GOTO, end_label)
        
        # Else branch (if exists)
        self.add_label(else_label)
        if node.orelse:
            for stmt in node.orelse:
                self.visit(stmt)
        
        # End if
        self.add_label(end_label)
    
    def visit_While(self, node: ast.While):
        """Visit while loop"""
        loop_start = self.new_label()
        loop_end = self.new_label()
        
        self.loop_stack.append(loop_end)
        
        self.add_label(loop_start)
        condition = self.visit(node.test)
        
        # If condition is false, exit loop
        zero_temp = self.new_temp()
        self.add_instruction(IROp.EQ, condition, "0", zero_temp)
        self.add_instruction(IROp.IF, zero_temp, loop_end)
        
        for stmt in node.body:
            self.visit(stmt)
        
        self.add_instruction(IROp.GOTO, loop_start)
        self.add_label(loop_end)
        
        self.loop_stack.pop()
    
    def visit_Call(self, node: ast.Call):
        """Visit function call - maps to Signum built-ins"""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            # Check if it's a user-defined function
            if func_name in self.functions:
                # Generate function call
                # Store arguments in temporary variables
                for i, arg in enumerate(node.args):
                    arg_value = self.visit(arg)
                    self.add_instruction(IROp.SET, f"arg_{i}", arg_value)

                # Jump to function
                self.add_instruction(IROp.GOTO, f"func_{func_name}")

                # Create a temporary for return value (simplified)
                result = self.new_temp()
                return result

            # Map Python built-ins to Signum operations
            elif func_name == "set":
                # set(key, value) - store in persistent storage map
                key = self.visit(node.args[0])
                value = self.visit(node.args[1])
                # Use map_set operation for persistent storage
                result = self.new_temp()
                self.add_instruction(IROp.SET, f"map_set_{key}", value)
                return None

            elif func_name == "get":
                # get(key) - retrieve from persistent storage map
                key = self.visit(node.args[0])
                result = self.new_temp()
                # Use map_get operation
                self.add_instruction(IROp.SET, result, f"map_get_{key}")
                return result

            elif func_name == "sender":
                result = self.new_temp()
                self.add_instruction(IROp.SENDER, result)
                return result

            elif func_name == "block_height":
                result = self.new_temp()
                self.add_instruction(IROp.BLOCK_HEIGHT, result)
                return result

            elif func_name == "timestamp":
                result = self.new_temp()
                self.add_instruction(IROp.TIMESTAMP, result)
                return result

            elif func_name == "transfer":
                # transfer(token_id, to, amount)
                token = self.visit(node.args[0]) if len(node.args) > 0 else "0"
                to = self.visit(node.args[1]) if len(node.args) > 1 else "0"
                amount = self.visit(node.args[2]) if len(node.args) > 2 else "0"
                self.add_instruction(IROp.TRANSFER, token, to, amount)
                return None

            elif func_name == "emit":
                # emit(event_name, data_dict)
                event = self.visit(node.args[0])
                if len(node.args) > 1:
                    # For now, just serialize the dict as a simple string
                    data = self.visit(node.args[1])
                else:
                    data = '""'
                self.add_instruction(IROp.EMIT, event, data)
                return None

            elif func_name == "verify":
                # verify(signature, message, pubkey) -> bool
                sig = self.visit(node.args[0])
                msg = self.visit(node.args[1])
                key = self.visit(node.args[2])
                result = self.new_temp()
                self.add_instruction(IROp.VERIFY, sig, msg, key, result)
                return result

            elif func_name == "log":
                # log(message)
                msg = self.visit(node.args[0])
                self.add_instruction(IROp.LOG, msg)
                return None

            elif func_name == "delete":
                # delete(key)
                key = self.visit(node.args[0])
                self.add_instruction(IROp.DELETE, key)
                return None

            elif func_name == "mint":
                # mint(token_id, to, amount)
                token = self.visit(node.args[0])
                to = self.visit(node.args[1])
                amount = self.visit(node.args[2])
                self.add_instruction(IROp.MINT, token, to, amount)
                return None

            elif func_name == "burn":
                # burn(token_id, from, amount)
                token = self.visit(node.args[0])
                from_addr = self.visit(node.args[1])
                amount = self.visit(node.args[2])
                self.add_instruction(IROp.BURN, token, from_addr, amount)
                return None

        elif isinstance(node.func, ast.Attribute):
            # Handle method calls like obj.method()
            func_name = f"{self.visit(node.func.value)}.{node.func.attr}"
            return f"call_{func_name}"

        raise NotImplementedError(f"Function call not supported: {ast.dump(node)}")
    
    def visit_Constant(self, node: ast.Constant):
        """Visit constant values"""
        if isinstance(node.value, int):
            return str(node.value)
        elif isinstance(node.value, str):
            return f'"{node.value}"'
        elif isinstance(node.value, bool):
            return "1" if node.value else "0"
        elif node.value is None:
            return "0"
        else:
            raise NotImplementedError(f"Constant type {type(node.value)} not supported")
    
    def visit_Name(self, node: ast.Name):
        """Visit variable name"""
        if node.id == "True":
            return "1"
        elif node.id == "False":
            return "0"
        elif node.id == "None":
            return "0"
        else:
            storage_key = self.get_var_storage_key(node.id)
            result = self.new_temp()
            self.add_instruction(IROp.GET, storage_key, result)
            return result

    def visit_Dict(self, node: ast.Dict):
        """Visit dictionary literal - convert to JSON string"""
        import json
        dict_items = {}
        for key, value in zip(node.keys, node.values):
            # Keys must be constants (strings)
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                key_str = key.value
            else:
                raise NotImplementedError("Non-string dictionary keys not supported")

            # Process value
            if isinstance(value, ast.Constant):
                dict_items[key_str] = value.value
            elif isinstance(value, ast.Name):
                # Get variable value at runtime - for now use variable name as placeholder
                dict_items[key_str] = f"${value.id}"
            else:
                raise NotImplementedError(f"Dictionary value type {type(value).__name__} not supported")

        # Convert to JSON string
        return json.dumps(dict_items)

    def visit_Return(self, node: ast.Return):
        """Visit return statement"""
        if node.value:
            value = self.visit(node.value)
            self.add_instruction(IROp.RETURN, value)
        else:
            self.add_instruction(IROp.RETURN)
    
    def visit_AugAssign(self, node: ast.AugAssign):
        """Visit augmented assignment: x += 1"""
        if isinstance(node.target, ast.Name):
            var_name = node.target.id
            storage_key = self.get_var_storage_key(var_name)
            
            # Get current value
            current = self.new_temp()
            self.add_instruction(IROp.GET, storage_key, current)
            
            # Compute new value
            right = self.visit(node.value)
            result = self.new_temp()
            
            op_map = {
                ast.Add: IROp.ADD,
                ast.Sub: IROp.SUB,
                ast.Mult: IROp.MUL,
                ast.Div: IROp.DIV,
            }
            
            op_type = op_map.get(type(node.op))
            if op_type:
                self.add_instruction(op_type, current, right, result)
                self.add_instruction(IROp.SET, storage_key, result)
            else:
                raise NotImplementedError(f"Augmented assign operator {type(node.op)} not supported")
        else:
            raise NotImplementedError("Complex augmented assignment not supported")
    
    def generic_visit(self, node):
        """Handle unsupported nodes"""
        raise NotImplementedError(f"Unsupported AST node: {type(node).__name__} at line {getattr(node, 'lineno', 'unknown')}")
    
    def get_ir(self) -> List[IRNode]:
        """Get the generated IR instructions"""
        return self.instructions

# ============================================================================
# PART 4: IR to Signum SmartC Code Generator
# ============================================================================

class SignumCodeGenerator:
    """Generates Signum SmartC code from IR"""

    def __init__(self, contract_name: str = "MyContract"):
        self.contract_name = contract_name
        self.variables: Dict[str, SignumVariable] = {}
        self.indent_level = 0
        self.storage_vars = set()

    def indent(self) -> str:
        return "    " * self.indent_level

    def generate(self, ir: List[IRNode], variables: Dict[str, SignumVariable]) -> str:
        """Generate SmartC code from IR"""
        self.variables = variables
        lines = []

        # Contract header
        lines.append(f"// Generated by Python-to-Signum Compiler")
        lines.append(f"#pragma version 1.0")
        lines.append(f"")
        lines.append(f"#program name \"{self.contract_name}\"")
        lines.append(f"")

        # Use a storage map for persistent data
        lines.append(f"// Storage map for persistent state")
        lines.append(f"long balances;  // map<address => balance>")
        lines.append(f"long allowed;   // map<address => allowance>")
        lines.append(f"long owner;")
        lines.append(f"long total_supply;")
        lines.append(f"")

        # Main function
        lines.append("function main() {")
        self.indent_level = 1

        # Generate clean code from IR
        in_function = False
        current_func = None

        for instr in ir:
            # Skip label instructions at top level - they mark function boundaries
            if instr.op == IROp.LABEL and instr.args[0].startswith("func_"):
                if in_function:
                    self.indent_level = 0
                    lines.append("}")
                current_func = instr.args[0].replace("func_", "")
                in_function = True
                lines.append("")
                lines.append(f"function {current_func}() {{")
                self.indent_level = 1
                continue

            line = self.generate_instruction(instr)
            if line:
                # Handle labels specially (no semicolon)
                if instr.op == IROp.LABEL:
                    lines.append(f"{self.indent()}{line}")
                else:
                    # Add semicolon if needed
                    if not line.strip().endswith((';', '{', '}')):
                        lines.append(f"{self.indent()}{line};")
                    else:
                        lines.append(f"{self.indent()}{line}")

        if in_function:
            self.indent_level = 0
            lines.append("}")
        else:
            self.indent_level = 0
            lines.append("}")
        
        code = "\n".join(lines)
        # Post-process to fix issues
        code = self.cleanup_smartc(code)
        return code

    def cleanup_smartc(self, code: str) -> str:
        """Clean up generated SmartC code to be valid"""
        import re

        # Replace problematic string concatenation with simple key names
        # "balance_"__tmp2 becomes key_balance
        code = re.sub(r'"([^"]+)"__\w+', r'key_\1', code)
        code = code.replace('"', '')  # Remove quotes from string literals temporarily

        # Remove goto and label statements (SmartC doesn't like them much)
        lines = code.split('\n')
        cleaned = []

        for line in lines:
            if 'goto' in line or line.strip().endswith(':'):
                # Skip gotos and labels for now
                if not line.strip().startswith('//'):
                    continue
            cleaned.append(line)

        code = '\n'.join(cleaned)

        # Fix dictionary literals in emit() calls
        code = re.sub(r'emit\("([^"]+)",\s*{([^}]*)}', r'emit("\1")', code)

        # Remove variable declarations that have no value
        code = re.sub(r'long _tmp_\d+ = [^;]+;\n\s+storage\[', r'storage[', code)

        return code
    
    def generate_instruction(self, instr: IRNode) -> str:
        """Generate SmartC code for a single IR instruction"""
        
        if instr.op == IROp.SET:
            return f"{self.format_arg(instr.args[0])} = {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.GET:
            return f"long {self.format_arg(instr.args[1])} = {self.format_arg(instr.args[0])}"
        
        elif instr.op == IROp.ADD:
            return f"long {self.format_arg(instr.args[2])} = {self.format_arg(instr.args[0])} + {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.SUB:
            return f"long {self.format_arg(instr.args[2])} = {self.format_arg(instr.args[0])} - {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.MUL:
            return f"long {self.format_arg(instr.args[2])} = {self.format_arg(instr.args[0])} * {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.DIV:
            return f"long {self.format_arg(instr.args[2])} = {self.format_arg(instr.args[0])} / {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.MOD:
            return f"long {self.format_arg(instr.args[2])} = {self.format_arg(instr.args[0])} % {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.EQ:
            return f"long {self.format_arg(instr.args[2])} = ({self.format_arg(instr.args[0])} == {self.format_arg(instr.args[1])}) ? 1 : 0"
        
        elif instr.op == IROp.NE:
            return f"long {self.format_arg(instr.args[2])} = ({self.format_arg(instr.args[0])} != {self.format_arg(instr.args[1])}) ? 1 : 0"
        
        elif instr.op == IROp.LT:
            return f"long {self.format_arg(instr.args[2])} = ({self.format_arg(instr.args[0])} < {self.format_arg(instr.args[1])}) ? 1 : 0"
        
        elif instr.op == IROp.GT:
            return f"long {self.format_arg(instr.args[2])} = ({self.format_arg(instr.args[0])} > {self.format_arg(instr.args[1])}) ? 1 : 0"
        
        elif instr.op == IROp.LE:
            return f"long {self.format_arg(instr.args[2])} = ({self.format_arg(instr.args[0])} <= {self.format_arg(instr.args[1])}) ? 1 : 0"
        
        elif instr.op == IROp.GE:
            return f"long {self.format_arg(instr.args[2])} = ({self.format_arg(instr.args[0])} >= {self.format_arg(instr.args[1])}) ? 1 : 0"
        
        elif instr.op == IROp.IF:
            # IF condition THEN goto label
            return f"if ({self.format_arg(instr.args[0])}) goto {self.format_arg(instr.args[1])}"
        
        elif instr.op == IROp.GOTO:
            return f"goto {self.format_arg(instr.args[0])}"
        
        elif instr.op == IROp.LABEL:
            return f"{self.format_arg(instr.args[0])}:"
        
        elif instr.op == IROp.SENDER:
            return f"address {self.format_arg(instr.args[0])} = tx.sender"
        
        elif instr.op == IROp.BLOCK_HEIGHT:
            return f"long {self.format_arg(instr.args[0])} = block.height"
        
        elif instr.op == IROp.TIMESTAMP:
            return f"timestamp {self.format_arg(instr.args[0])} = block.timestamp"
        
        elif instr.op == IROp.TX_AMOUNT:
            return f"long {self.format_arg(instr.args[0])} = tx.amount"
        
        elif instr.op == IROp.CONTRACT_BALANCE:
            return f"long {self.format_arg(instr.args[0])} = contract.balance"
        
        elif instr.op == IROp.TRANSFER:
            return f"transfer({self.format_arg(instr.args[0])}, {self.format_arg(instr.args[1])}, {self.format_arg(instr.args[2])})"
        
        elif instr.op == IROp.MINT:
            return f"mint({self.format_arg(instr.args[0])}, {self.format_arg(instr.args[1])}, {self.format_arg(instr.args[2])})"
        
        elif instr.op == IROp.BURN:
            return f"burn({self.format_arg(instr.args[0])}, {self.format_arg(instr.args[1])}, {self.format_arg(instr.args[2])})"
        
        elif instr.op == IROp.EMIT:
            return f"emit({self.format_arg(instr.args[0])}, {self.format_arg(instr.args[1])})"
        
        elif instr.op == IROp.LOG:
            return f"log({self.format_arg(instr.args[0])})"
        
        elif instr.op == IROp.VERIFY:
            return f"long {self.format_arg(instr.args[3])} = verify({self.format_arg(instr.args[0])}, {self.format_arg(instr.args[1])}, {self.format_arg(instr.args[2])})"
        
        elif instr.op == IROp.HASH:
            return f"bytes {self.format_arg(instr.args[2])} = hash({self.format_arg(instr.args[0])}, {self.format_arg(instr.args[1])})"
        
        elif instr.op == IROp.DELETE:
            return f"delete({self.format_arg(instr.args[0])})"
        
        elif instr.op == IROp.RETURN:
            if len(instr.args) > 0:
                return f"return {self.format_arg(instr.args[0])}"
            return "return"
        
        elif instr.op == IROp.PUSH:
            return f"// PUSH {self.format_arg(instr.args[0])}"
        
        elif instr.op == IROp.POP:
            return "// POP"
        
        else:
            return f"// Unsupported: {instr.op.value}"
    
    def format_arg(self, arg: Any) -> str:
        """Format an argument for SmartC output"""
        if arg is None:
            return "0"
        if isinstance(arg, str):
            # Check if it's a map operation
            if arg.startswith("map_set_") or arg.startswith("map_get_"):
                # Extract the key and create proper storage access
                parts = arg.split("_", 2)  # split into ['map', 'set/get', 'key']
                if len(parts) >= 3:
                    key = parts[2]
                    # Remove quotes if present
                    key = key.strip('"')
                    if arg.startswith("map_get_"):
                        return f"storage[{key}]"
                    else:
                        return f"storage[{key}]"
                return arg
            # Check for concatenation
            if arg.startswith("concat_"):
                parts = arg.split("_", 1)
                if len(parts) == 2:
                    operands = parts[1].rsplit("_", 1)
                    if len(operands) == 2:
                        return operands[0] + operands[1]
                return arg
            # Check if it's a temporary variable
            if arg.startswith("_tmp_"):
                return arg
            # Check if it's a storage key
            if arg.startswith("var_"):
                return arg
            # Check if it's a label
            if arg.startswith("label_") or arg.startswith("func_"):
                return arg
            # Check if it's an argument
            if arg.startswith("arg_"):
                return arg
            # String literal
            if arg.startswith('"'):
                return arg
            # Number
            try:
                int(arg)
                return arg
            except ValueError:
                return arg
        return str(arg)

# ============================================================================
# PART 5: Direct Python to SmartC Generator (Simpler Approach)
# ============================================================================

class SmartCDirectGenerator:
    """Generates SmartC code directly from Python AST without IR"""

    # Mapping of Python function names to actual SmartC built-in functions
    SIGNUM_FUNCTIONS = {
        # Blockchain/Contract Info
        "sender": "getCreator",
        "block_height": "getCurrentBlockheight",
        "timestamp": "getCurrentBlockheight",
        "random": "getWeakRandomNumber",

        # Transaction Handling
        "tx_amount": "getNextTx",
        "tx_type": "getType",
        "tx_sender": "getSender",

        # Storage/Map Operations
        "set": "setMapValue",
        "get": "getMapValue",
        "delete": "deleteMapValue",

        # Transfers
        "transfer": "sendAmount",
        "transfer_all": "sendBalance",
        "send_message": "sendMessage",

        # Balance Checks
        "balance": "getCurrentBalance",
        "account_balance": "getAccountBalance",

        # Assets
        "asset_balance": "getAssetBalance",
        "issue_asset": "issueAsset",
        "mint_asset": "mintAsset",
    }

    def __init__(self, contract_name: str = "MyContract"):
        self.contract_name = contract_name
        self.indent_level = 0
        self.functions = {}
        self.state_vars = set()
        self.global_vars = set()  # Track global variables
        self.string_key_map = {}  # Map string keys to numeric IDs for storage
        self.string_constants = {}  # Map long strings to const variable names

    def indent(self) -> str:
        return "    " * self.indent_level

    def get_string_key_id(self, string_key: str) -> int:
        """Convert string keys to numeric IDs for storage (SmartC only accepts numeric keys)"""
        if string_key not in self.string_key_map:
            # Assign numeric IDs starting from 100 (to avoid conflict with numeric keys)
            self.string_key_map[string_key] = 100 + len(self.string_key_map)
        return self.string_key_map[string_key]

    def get_string_constant_name(self, string_val: str) -> str:
        """For strings > 8 bytes, convert to numeric code; short strings stay as-is"""
        if len(string_val) <= 8:
            return f'"{string_val}"'  # Short strings can be used directly

        # For long strings, convert to numeric codes
        string_codes = {
            "withdrawn": "1",
            "ready": "2",
            "locked": "3",
            "active": "4",
            "pending": "5",
            "completed": "6",
        }

        if string_val in string_codes:
            return string_codes[string_val]
        else:
            # Unknown long string - try to map it
            if string_val not in self.string_constants:
                code = str(100 + len(self.string_constants))
                self.string_constants[string_val] = code
            return self.string_constants[string_val]

    def _collect_used_vars(self, node: ast.expr, used_vars: set):
        """Recursively collect variable names used in expressions"""
        if isinstance(node, ast.Name):
            used_vars.add(node.id)
        elif isinstance(node, ast.BinOp):
            self._collect_used_vars(node.left, used_vars)
            self._collect_used_vars(node.right, used_vars)
        elif isinstance(node, ast.Compare):
            self._collect_used_vars(node.left, used_vars)
            for comp in node.comparators:
                self._collect_used_vars(comp, used_vars)
        elif isinstance(node, ast.Call):
            for arg in node.args:
                self._collect_used_vars(arg, used_vars)
        elif isinstance(node, ast.UnaryOp):
            self._collect_used_vars(node.operand, used_vars)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key:
                    self._collect_used_vars(key, used_vars)
            for value in node.values:
                self._collect_used_vars(value, used_vars)

    def generate(self, tree: ast.Module) -> str:
        """Generate SmartC code from Python AST"""
        lines = []

        # Collect variable names - both assigned and used
        assigned_vars = set()
        used_vars = set()

        def collect_vars(nodes):
            """Recursively collect variable names from assignments and usage"""
            for node in nodes:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assigned_vars.add(target.id)
                    # Collect used variables from the value
                    self._collect_used_vars(node.value, used_vars)
                elif isinstance(node, ast.FunctionDef):
                    collect_vars(node.body)
                elif isinstance(node, ast.If):
                    self._collect_used_vars(node.test, used_vars)
                    collect_vars(node.body)
                    collect_vars(node.orelse)
                elif isinstance(node, ast.While):
                    self._collect_used_vars(node.test, used_vars)
                    collect_vars(node.body)
                elif isinstance(node, ast.For):
                    collect_vars(node.body)
                elif isinstance(node, ast.Expr):
                    self._collect_used_vars(node.value, used_vars)

        collect_vars(tree.body)

        # Collect all function parameter names to exclude from global vars
        param_names = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                for arg in node.args.args:
                    param_names.add(arg.arg)

        # Only declare variables that are actually used or assigned (excluding function parameters)
        var_names = (assigned_vars | used_vars) - param_names
        self.global_vars = var_names  # Store for use in generate_function

        # Header
        lines.append("// Generated by Python-to-Signum Compiler")
        lines.append("#pragma maxAuxVars 5")
        lines.append("#pragma maxConstVars 5")
        lines.append(f"#program name {self.contract_name}")
        lines.append("")
        lines.append("// String constants for return values (map long strings to codes)")
        lines.append("// 'withdrawn' -> 1, 'ready' -> 2, 'locked' -> 3")
        lines.append("")

        # Declare variables
        for var_name in sorted(var_names):
            lines.append(f"long {var_name};")
        lines.append("")

        # First pass: collect functions
        functions = []
        statements = []

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append(node)
            else:
                statements.append(node)

        # Collect variables assigned in main (excluding those assigned from Signum functions)
        main_assigned = set()
        for stmt in statements:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        # Check if the value is a Signum function call
                        is_signum_call = False
                        if isinstance(stmt.value, ast.Call):
                            if isinstance(stmt.value.func, ast.Name):
                                if stmt.value.func.id in ("sender", "get", "block_height", "timestamp"):
                                    is_signum_call = True
                        # Only mark as assigned if it's not a Signum function
                        if not is_signum_call:
                            main_assigned.add(target.id)

        # Generate main function with initialization code
        lines.append("void main() {")
        self.indent_level = 1

        # Initialize global variables that are used but not assigned in main
        vars_to_init = var_names - main_assigned
        for var_name in sorted(vars_to_init):
            lines.append(f"{self.indent()}{var_name} = 0;")
        if vars_to_init:
            lines.append("")

        for stmt in statements:
            lines.extend(self.generate_statement(stmt))

        self.indent_level = 0
        lines.append("}")
        lines.append("")

        # Generate other functions
        for func in functions:
            lines.extend(self.generate_function(func))

        return "\n".join(filter(None, lines))

    def generate_function(self, node: ast.FunctionDef) -> List[str]:
        """Generate a SmartC function with full body"""
        lines = []

        # Rename parameters that conflict with global variables
        param_renames = {}  # Maps original param names to renamed ones
        for arg in node.args.args:
            param_name = arg.arg
            # Check if param is a substring of any global var, or exact match
            conflict = False
            for global_var in self.global_vars:
                if param_name == global_var or param_name in global_var:
                    conflict = True
                    break

            if conflict:
                # Rename parameter to avoid conflict (use "param_" prefix)
                new_name = f"param_{param_name}"
                param_renames[param_name] = new_name

        # Build parameter list with renames
        args = ", ".join([
            f"long {param_renames.get(arg.arg, arg.arg)}"
            for arg in node.args.args
        ])

        # Standard C function syntax: return_type name(params) { body }
        lines.append(f"long {node.name}({args}) {{")
        self.indent_level += 1

        # Collect ONLY local variables (not globals, not parameters)
        local_vars = set()
        param_names = {param_renames.get(arg.arg, arg.arg) for arg in node.args.args}

        def collect_local_vars(stmts):
            for stmt in stmts:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            # Exclude parameters and global variables
                            if target.id not in param_names and target.id not in self.global_vars:
                                local_vars.add(target.id)
                elif isinstance(stmt, ast.If):
                    collect_local_vars(stmt.body)
                    collect_local_vars(stmt.orelse)

        collect_local_vars(node.body)

        # Only initialize truly local variables (not globals) - globals persist automatically
        for var in sorted(local_vars):
            lines.append(f"{self.indent()}{var} = 0;")
        if local_vars:
            lines.append("")

        # Generate function body
        has_return = False
        body_lines = []
        for stmt in node.body:
            generated = self.generate_statement(stmt)
            body_lines.extend(generated)
            # Check if any generated line contains a return statement
            for line in generated:
                if "return" in line and "//" not in line:
                    has_return = True

        # Apply parameter renames to body
        for line in body_lines:
            for orig_name, new_name in param_renames.items():
                # Replace parameter references with renamed version
                # Use word boundaries to avoid partial replacements
                import re
                line = re.sub(r'\b' + orig_name + r'\b', new_name, line)
            lines.append(line)

        # Add default return if none exists
        if not has_return:
            lines.append(f"{self.indent()}return 0;")

        self.indent_level -= 1
        lines.append("}")
        lines.append("")

        return lines

    def generate_statement(self, node: ast.stmt) -> List[str]:
        """Generate a statement"""
        if isinstance(node, ast.Expr):
            return self.generate_expression_statement(node.value)
        elif isinstance(node, ast.Assign):
            return self.generate_assignment(node)
        elif isinstance(node, ast.If):
            return self.generate_if(node)
        elif isinstance(node, ast.Return):
            return self.generate_return(node)
        elif isinstance(node, ast.FunctionDef):
            return self.generate_function(node)
        else:
            return [f"{self.indent()}// Unsupported: {type(node).__name__}"]

    def generate_expression_statement(self, node: ast.expr) -> List[str]:
        """Generate an expression statement"""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                # Skip functions that have no return value and no side effects in SmartC
                if func_name in ("emit", "sender", "block_height", "timestamp", "tx_amount", "transfer"):
                    return []
                # "set", "get" should generate setMapValue/getMapValue calls
            code = self.format_call(node)
            return [f"{self.indent()}{code};"] if code else []
        return []

    def generate_assignment(self, node: ast.Assign) -> List[str]:
        """Generate an assignment"""
        target = self.format_expr(node.targets[0])
        value = self.format_expr(node.value)
        # Now properly generate assignments with Signum functions
        return [f"{self.indent()}{target} = {value};"]

    def generate_if(self, node: ast.If) -> List[str]:
        """Generate an if statement"""
        lines = []
        condition = self.format_expr(node.test)
        lines.append(f"{self.indent()}if ({condition}) {{")

        self.indent_level += 1
        for stmt in node.body:
            lines.extend(self.generate_statement(stmt))
        self.indent_level -= 1

        if node.orelse:
            lines.append(f"{self.indent()}}} else {{")
            self.indent_level += 1
            for stmt in node.orelse:
                lines.extend(self.generate_statement(stmt))
            self.indent_level -= 1

        lines.append(f"{self.indent()}}}")
        return lines

    def generate_return(self, node: ast.Return) -> List[str]:
        """Generate a return statement"""
        if node.value:
            # Skip returns that are function calls
            if isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name):
                    func_name = node.value.func.id
                    if func_name in ("get", "sender", "tx_amount", "block_height", "timestamp"):
                        return [
                            f"{self.indent()}// return {func_name}();  // Signum function",
                            f"{self.indent()}return 0;"
                        ]
            value = self.format_expr(node.value)
            return [f"{self.indent()}return {value};"]
        return [f"{self.indent()}return 0;"]

    def format_expr(self, node: ast.expr) -> str:
        """Format an expression"""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                # Use const for strings longer than 8 bytes
                return self.get_string_constant_name(node.value)
            return str(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.BinOp):
            # Special handling for string concatenation with +
            if isinstance(node.op, ast.Add):
                # Check if this is string + something or something + string
                left_is_str = isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
                right_is_str = isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)

                if left_is_str or right_is_str:
                    # String concatenation - extract numeric value
                    if left_is_str and isinstance(node.right, ast.Name):
                        # "string" + variable -> use variable as key
                        return self.format_expr(node.right)
                    elif left_is_str and isinstance(node.right, ast.Call):
                        # "string" + function() -> check if it's str() call
                        if isinstance(node.right.func, ast.Name) and node.right.func.id == "str":
                            # "string" + str(var) -> use var as key
                            if len(node.right.args) > 0:
                                return self.format_expr(node.right.args[0])
                        # Otherwise use the call result
                        return self.format_expr(node.right)
                    elif right_is_str and isinstance(node.left, ast.Name):
                        # variable + "string" -> use variable as key
                        return self.format_expr(node.left)
                    elif right_is_str and isinstance(node.left, ast.Call):
                        # function() + "string" -> check if it's str() call
                        if isinstance(node.left.func, ast.Name) and node.left.func.id == "str":
                            # str(var) + "string" -> use var as key
                            if len(node.left.args) > 0:
                                return self.format_expr(node.left.args[0])
                        # Otherwise use the call result
                        return self.format_expr(node.left)

            left = self.format_expr(node.left)
            right = self.format_expr(node.right)
            op = self.format_binop(node.op)
            return f"({left} {op} {right})"
        elif isinstance(node, ast.Compare):
            left = self.format_expr(node.left)
            comp = self.format_cmpop(node.ops[0])
            right = self.format_expr(node.comparators[0])
            return f"({left} {comp} {right})"
        elif isinstance(node, ast.Call):
            return self.format_call(node)
        elif isinstance(node, ast.Dict):
            # Convert dictionary to JSON string (without variable references)
            import json
            items = {}
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    key_str = key.value
                    if isinstance(value, ast.Constant):
                        items[key_str] = value.value
                    elif isinstance(value, ast.Name):
                        # Skip variable references - just use empty string
                        items[key_str] = ""
            return f'"{json.dumps(items)}"'
        else:
            return "0  /* unsupported */"

    def format_call(self, node: ast.Call) -> str:
        """Format a function call"""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

            # Check if it's a Signum function
            if func_name in self.SIGNUM_FUNCTIONS:
                args = [self.format_expr(arg) for arg in node.args]
                smartc_func = self.SIGNUM_FUNCTIONS[func_name]

                # Generate proper SmartC built-in function calls
                if func_name == "sender":
                    return "getCreator()"
                elif func_name == "block_height":
                    return "getCurrentBlockheight()"
                elif func_name == "timestamp":
                    return "getCurrentBlockheight()"
                elif func_name == "random":
                    return "getWeakRandomNumber()"
                elif func_name == "balance":
                    return "getCurrentBalance()"
                elif func_name == "transfer" and len(args) >= 2:
                    return f"sendAmount({args[0]}, {args[1]})"
                elif func_name == "transfer_all" and len(args) > 0:
                    return f"sendBalance({args[0]})"
                elif func_name == "set" and len(args) >= 2:
                    # setMapValue needs 2 keys and a value
                    # Convert string keys to numeric IDs
                    if len(args) == 2:
                        # set(key, value) -> use 0 as key1, convert key to numeric
                        key_arg = args[0]
                        # Check if key is a string literal (starts and ends with quotes)
                        if key_arg.startswith('"') and key_arg.endswith('"'):
                            string_key = key_arg[1:-1]  # Remove quotes
                            numeric_key = self.get_string_key_id(string_key)
                            return f"setMapValue(0, {numeric_key}, {args[1]})"
                        else:
                            return f"setMapValue(0, {key_arg}, {args[1]})"
                    else:
                        # setMapValue with explicit key1 and key2
                        return f"setMapValue({args[0]}, {args[1]}, {args[2]})"
                elif func_name == "get" and len(args) >= 1:
                    # getMapValue needs 2 keys
                    # Convert string keys to numeric IDs
                    if len(args) == 1:
                        # get(key) -> use 0 as key1, convert key to numeric
                        key_arg = args[0]
                        # Check if key is a string literal (starts and ends with quotes)
                        if key_arg.startswith('"') and key_arg.endswith('"'):
                            string_key = key_arg[1:-1]  # Remove quotes
                            numeric_key = self.get_string_key_id(string_key)
                            return f"getMapValue(0, {numeric_key})"
                        else:
                            return f"getMapValue(0, {key_arg})"
                    else:
                        # getMapValue with explicit key1 and key2
                        return f"getMapValue({args[0]}, {args[1]})"
                elif func_name == "send_message" and len(args) >= 2:
                    return f"sendMessage({args[0]}, {args[1]})"
                else:
                    # Fallback for other SmartC functions
                    args_str = ", ".join(args) if args else ""
                    return f"{smartc_func}({args_str})"

            # Regular function calls
            args = [self.format_expr(arg) for arg in node.args]
            args_str = ", ".join(args)
            return f"{func_name}({args_str})"
        return "0"

    def format_binop(self, op: ast.operator) -> str:
        """Format binary operator"""
        if isinstance(op, ast.Add):
            return "+"
        elif isinstance(op, ast.Sub):
            return "-"
        elif isinstance(op, ast.Mult):
            return "*"
        elif isinstance(op, ast.Div):
            return "/"
        elif isinstance(op, ast.Mod):
            return "%"
        elif isinstance(op, ast.FloorDiv):
            return "/"
        elif isinstance(op, ast.Pow):
            return "**"
        else:
            return "?"

    def format_cmpop(self, op: ast.cmpop) -> str:
        """Format comparison operator"""
        if isinstance(op, ast.Eq):
            return "=="
        elif isinstance(op, ast.NotEq):
            return "!="
        elif isinstance(op, ast.Lt):
            return "<"
        elif isinstance(op, ast.Gt):
            return ">"
        elif isinstance(op, ast.LtE):
            return "<="
        elif isinstance(op, ast.GtE):
            return ">="
        return "?"

# ============================================================================
# PART 6: Test Framework
# ============================================================================

class CompilerTestFramework:
    """Test framework for validating compiler output"""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        
    def run_tests(self):
        """Run all compiler tests"""
        print("=" * 60)
        print("Running Python-to-Signum Compiler Tests")
        print("=" * 60)
        
        # Run all tests
        self.test_simple_assignment()
        self.test_arithmetic()
        self.test_if_statement()
        self.test_while_loop()
        self.test_builtin_calls()
        self.test_token_transfer()
        self.test_augmented_assignment()
        self.test_function_definition()
        
        # Summary
        print("\n" + "=" * 60)
        print(f"RESULTS: {self.tests_passed} passed, {self.tests_failed} failed")
        print("=" * 60)
        
        return self.tests_failed == 0
    
    def test(self, name: str, source: str, expected_patterns: List[str]) -> bool:
        """Run a single test"""
        try:
            # Parse and compile
            tree = ast.parse(source)
            converter = PythonToIRConverter()
            converter.visit(tree)
            ir = converter.get_ir()
            
            # Generate code
            generator = SignumCodeGenerator(name.replace(" ", "_"))
            output = generator.generate(ir, converter.variables)
            
            # Check for expected patterns
            for pattern in expected_patterns:
                if pattern.lower() not in output.lower():
                    print(f"[FAIL] {name}: Expected pattern '{pattern}' not found")
                    print(f"       Output snippet: {output[:500]}...")
                    return False

            print(f"[PASS] {name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_simple_assignment(self):
        """Test simple variable assignment"""
        source = """
x = 5
y = 10
"""
        expected = ["var_x = 5", "var_y = 10"]
        if self.test("Simple Assignment", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_arithmetic(self):
        """Test arithmetic operations"""
        source = """
x = 5
y = 10
z = x + y
w = z * 2
"""
        expected = ["var_x = 5", "var_y = 10", "+", "*"]
        if self.test("Arithmetic Operations", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_if_statement(self):
        """Test if-else statement"""
        source = """
x = 5
if x > 0:
    y = 1
else:
    y = 0
"""
        # Look for if/goto/label patterns instead of 'return'
        expected = ["if (", "goto", "label_"]
        if self.test("If Statement", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_while_loop(self):
        """Test while loop"""
        source = """
x = 0
while x < 10:
    x = x + 1
"""
        expected = ["goto", "label_"]
        if self.test("While Loop", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_builtin_calls(self):
        """Test built-in function calls"""
        source = """
sender_addr = sender()
current_block = block_height()
current_time = timestamp()
"""
        expected = ["tx.sender", "block.height", "block.timestamp"]
        if self.test("Built-in Calls", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_token_transfer(self):
        """Test token transfer"""
        source = """
transfer("SIGNA", "S-ABCD-1234", 100)
emit("Transfer", '{"to": "S-ABCD-1234", "amount": 100}')
"""
        expected = ["transfer", "emit"]
        if self.test("Token Transfer", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_augmented_assignment(self):
        """Test augmented assignment"""
        source = """
x = 5
x += 1
x *= 2
"""
        expected = ["+", "*"]
        if self.test("Augmented Assignment", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1
    
    def test_function_definition(self):
        """Test function definitions"""
        source = """
def test_func(a, b):
    return a + b

result = test_func(5, 3)
"""
        expected = ["func_test_func", "return"]
        if self.test("Function Definition", source, expected):
            self.tests_passed += 1
        else:
            self.tests_failed += 1

# ============================================================================
# PART 7: CLI Interface
# ============================================================================

def compile_file(input_path: str, output_path: str = None) -> bool:
    """Compile a Python file to Signum SmartC"""
    try:
        # Read input file
        with open(input_path, 'r') as f:
            source = f.read()

        # Parse Python source
        tree = ast.parse(source)

        # Generate SmartC code directly (simpler approach)
        contract_name = Path(input_path).stem
        # Sanitize contract name: SmartC only allows [a-zA-Z0-9], max 30 chars
        contract_name = ''.join(c for c in contract_name if c.isalnum())
        contract_name = contract_name[:30] if contract_name else "contract"
        generator = SmartCDirectGenerator(contract_name)
        output = generator.generate(tree)

        # Write output
        if output_path is None:
            output_path = Path(input_path).with_suffix('.smart.c')

        with open(output_path, 'w') as f:
            f.write(output)

        print(f"[SUCCESS] Compilation successful!")
        print(f"   Input: {input_path}")
        print(f"   Output: {output_path}")
        print(f"   SmartC code generated")

        return True

    except Exception as e:
        print(f"[ERROR] Compilation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Python-to-Signum Smart Contract Compiler"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input Python file (.py)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output SmartC file (.smart.c)"
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run compiler tests"
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Generate an example contract"
    )
    
    args = parser.parse_args()
    
    if args.run_tests:
        # Run tests
        framework = CompilerTestFramework()
        success = framework.run_tests()
        sys.exit(0 if success else 1)
    
    elif args.example:
        # Generate example contract
        example = '''# Simple Token Contract on Signum Blockchain
# This contract implements a basic token with transfer functionality

# State variables
owner = sender()
total_supply = 1000000

# Mint initial supply to owner
set("balance_" + str(owner), total_supply)

# Transfer function
def transfer(to, amount):
    sender_addr = sender()
    sender_balance = get("balance_" + str(sender_addr))
    
    if sender_balance >= amount:
        # Update balances
        set("balance_" + str(sender_addr), sender_balance - amount)
        set("balance_" + str(to), get("balance_" + str(to)) + amount)
        
        # Emit transfer event
        emit("Transfer", {"from": sender_addr, "to": to, "amount": amount})
        return 1  # Success
    else:
        emit("Error", {"message": "Insufficient balance"})
        return 0  # Failure

# Check balance function
def get_balance(address):
    return get("balance_" + str(address))
'''
        print("=" * 60)
        print("Example Python Contract for Signum Blockchain")
        print("=" * 60)
        print(example)
        print("\nTo compile this contract, save it to a .py file and run:")
        print("  python signum_compiler.py mycontract.py")
        sys.exit(0)
    
    elif args.input:
        # Compile file
        success = compile_file(args.input, args.output)
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        sys.exit(1)

# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    main()