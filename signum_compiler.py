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
        
        # Second pass: generate code
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
                for i, arg in enumerate(node.args):
                    arg_value = self.visit(arg)
                    # Store arguments in temporary variables
                    self.add_instruction(IROp.SET, f"arg_{i}", arg_value)
                
                # Jump to function
                self.add_instruction(IROp.GOTO, f"func_{func_name}")
                
                # Store return value (would need stack for this)
                result = self.new_temp()
                return result
            
            # Map Python built-ins to Signum operations
            elif func_name == "set":
                # set(key, value)
                key = self.visit(node.args[0])
                value = self.visit(node.args[1])
                self.add_instruction(IROp.SET, key, value)
                return None
                
            elif func_name == "get":
                # get(key) -> value
                key = self.visit(node.args[0])
                result = self.new_temp()
                self.add_instruction(IROp.GET, key, result)
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
                # emit(event_name, data)
                event = self.visit(node.args[0])
                if len(node.args) > 1:
                    data = self.visit(node.args[1])
                else:
                    data = '"{}"'
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
        lines.append(f"contract {self.contract_name} {{")
        self.indent_level = 1
        
        # Declare state variables
        if variables:
            lines.append(f"{self.indent()}// State variables")
            for var in variables.values():
                lines.append(f"{self.indent()}{var.type.value} {var.storage_key};")
            lines.append(f"")
        
        # Constructor
        lines.append(f"{self.indent()}init() {{")
        self.indent_level = 2
        for var in variables.values():
            lines.append(f"{self.indent()}{var.storage_key} = 0;")
        self.indent_level = 1
        lines.append(f"{self.indent()}}}")
        lines.append(f"")
        
        # Main function
        lines.append(f"{self.indent()}function main() {{")
        self.indent_level = 2
        
        # Track labels to avoid duplicates
        seen_labels = set()
        
        # Generate IR instructions as SmartC
        for instr in ir:
            line = self.generate_instruction(instr)
            if line:
                # Handle labels specially (no semicolon)
                if instr.op == IROp.LABEL:
                    if line not in seen_labels:
                        lines.append(f"{self.indent()}{line}")
                        seen_labels.add(line)
                else:
                    # Don't add semicolon for goto and if statements that already have them
                    if line.strip().endswith(';'):
                        lines.append(f"{self.indent()}{line}")
                    else:
                        lines.append(f"{self.indent()}{line};")
        
        self.indent_level = 1
        lines.append(f"{self.indent()}}}")
        self.indent_level = 0
        lines.append(f"}}")
        
        return "\n".join(lines)
    
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
# PART 5: Test Framework
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
                    print(f"❌ {name}: Expected pattern '{pattern}' not found")
                    print(f"   Output snippet: {output[:500]}...")
                    return False
            
            print(f"✅ {name}")
            return True
            
        except Exception as e:
            print(f"❌ {name}: {e}")
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
        expected = ["if (", "goto", "return"]
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
# PART 6: CLI Interface
# ============================================================================

def compile_file(input_path: str, output_path: str = None) -> bool:
    """Compile a Python file to Signum SmartC"""
    try:
        # Read input file
        with open(input_path, 'r') as f:
            source = f.read()
        
        # Parse Python source
        tree = ast.parse(source)
        
        # Convert to IR
        converter = PythonToIRConverter()
        converter.visit(tree)
        ir = converter.get_ir()
        
        # Generate SmartC code
        contract_name = Path(input_path).stem
        generator = SignumCodeGenerator(contract_name)
        output = generator.generate(ir, converter.variables)
        
        # Write output
        if output_path is None:
            output_path = Path(input_path).with_suffix('.smart.c')
        
        with open(output_path, 'w') as f:
            f.write(output)
        
        print(f"✅ Compilation successful!")
        print(f"   Input: {input_path}")
        print(f"   Output: {output_path}")
        print(f"   Instructions: {len(ir)}")
        print(f"   Variables: {len(converter.variables)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Compilation failed: {e}")
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