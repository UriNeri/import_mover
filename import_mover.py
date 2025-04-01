import argparse
# import ast
import libcst as cst
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Union
from dataclasses import dataclass, field
import sys
# from rich.traceback import install
from collections import defaultdict
# import libcst.metadata as meta
# from libcst.metadata import ScopeProvider
import re

# install(show_locals=True)

@dataclass
class ImportInfo:
    """Store information about imports and their usage."""
    node: cst.Import | cst.ImportFrom
    names: Set[str] = field(default_factory=set)
    used_in_functions: Dict[str, bool] = field(default_factory=dict)
    is_used: bool = False

class MoveImportsTransformer(cst.CSTTransformer):
    """Transformer that moves imports into the functions where they are used."""
    def __init__(self, imports_by_function: Dict[str, List[cst.CSTNode]], module: cst.Module):
        self.imports_by_function = imports_by_function
        self.function_stack: List[str] = []
        self.module = module
        self.processed_imports: Dict[str, Set[str]] = defaultdict(set)
        super().__init__()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self.function_stack.append(node.name.value)
        logging.debug(f"Visiting function: {node.name.value} (stack: {self.function_stack})")
        return True

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        current_function = self.function_stack[-1]
        logging.debug(f"Processing function: {current_function} (stack: {self.function_stack})")
        
        if current_function in self.imports_by_function:
            imports = self.imports_by_function[current_function]
            logging.debug(f"  Found {len(imports)} imports to move into {current_function}")
            new_body = []
            
            # Preserve docstring if it exists
            if (isinstance(updated_node.body.body[0], cst.SimpleStatementLine) and
                isinstance(updated_node.body.body[0].body[0], cst.Expr) and
                isinstance(updated_node.body.body[0].body[0].value, cst.SimpleString)):
                new_body.append(updated_node.body.body[0])
                start_idx = 1
                logging.debug("  Preserved docstring")
            else:
                start_idx = 0
                
            # Add imports at the beginning (after docstring if exists)
            for imp in imports:
                # Skip if we've already added this import to this function
                import_str = self.module.code_for_node(imp)
                if import_str in self.processed_imports[current_function]:
                    logging.debug(f"  Skipping duplicate import: {import_str}")
                    continue
                
                # Create a new import node based on the original
                if isinstance(imp, cst.Import):
                    new_imp = cst.Import(names=imp.names)
                    logging.debug(f"  Adding import: {self.module.code_for_node(new_imp)}")
                elif isinstance(imp, cst.ImportFrom):
                    new_imp = cst.ImportFrom(
                        module=imp.module,
                        names=imp.names,
                        relative=imp.relative,
                        lpar=imp.lpar,
                        rpar=imp.rpar
                    )
                    logging.debug(f"  Adding import from: {self.module.code_for_node(new_imp)}")
                new_body.append(cst.SimpleStatementLine([new_imp]))
                self.processed_imports[current_function].add(import_str)
            
            # Add rest of function body
            new_body.extend(updated_node.body.body[start_idx:])
            
            updated_body = updated_node.body.with_changes(body=new_body)
            updated_node = updated_node.with_changes(body=updated_body)
            logging.debug(f"  Updated function body for {current_function}")
        else:
            logging.debug(f"  No imports to move into {current_function}")
        
        self.function_stack.pop()
        return updated_node

class RemoveUnusedImportTransformer(cst.CSTTransformer):
    """Transformer that handles unused imports - either comments them out or removes them."""
    def __init__(
        self, 
        unused_imports: Dict[Union[cst.Import, cst.ImportFrom], Set[str]],
        keep_old_imports: bool = True,
        module: cst.Module = None
    ) -> None:
        self.unused_imports = unused_imports
        self.keep_old_imports = keep_old_imports
        self.module = module
        super().__init__()

    def leave_SimpleStatementLine(
        self, 
        original_node: cst.SimpleStatementLine, 
        updated_node: cst.SimpleStatementLine
    ) -> Union[cst.SimpleStatementLine, cst.FlattenSentinel]:
        # Only process nodes that contain imports
        if not any(isinstance(stmt, (cst.Import, cst.ImportFrom)) for stmt in updated_node.body):
            return updated_node
            
        new_statements = []
        for stmt in updated_node.body:
            if isinstance(stmt, (cst.Import, cst.ImportFrom)) and stmt in self.unused_imports:
                if self.keep_old_imports:
                    # Create a comment node
                    import_str = self.module.code_for_node(stmt).strip()
                    new_statements.append(cst.SimpleStatementLine([
                        cst.Expr(cst.SimpleString(f'# {import_str}'))
                    ]))
                # If not keeping old imports, skip this statement
            else:
                # Keep non-import statements or used imports
                new_statements.append(cst.SimpleStatementLine([stmt]))
                
        if not new_statements:
            return updated_node
            
        if len(new_statements) == 1:
            return new_statements[0]
            
        return cst.FlattenSentinel(new_statements)

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> cst.Import:
        return updated_node

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        return updated_node

def process_file(
    source_path: Path,
    log_path: Optional[str],
    output_path: str,
    keep_old_imports: bool = True,
    remove_unused_imports: bool = True,
    whitelist_libs: Optional[Set[str]] = None,
) -> None:
    """Process a Python file to move imports into functions where they are used."""
    # Skip __init__.py files by default
    if source_path.name == "__init__.py":
        logging.info(f"Skipping __init__.py file: {source_path}")
        return

    # Read and parse the source code
    source_code = source_path.read_text()
    wrapper = cst.metadata.MetadataWrapper(cst.parse_module(source_code))
    
    # Get scope information
    scopes = set(wrapper.resolve(cst.metadata.ScopeProvider).values())
    logging.debug(f"Found {len(scopes)} scopes:")
    for scope in scopes:
        logging.debug(f"  Scope type: {type(scope).__name__}")
        if hasattr(scope, 'name'):
            logging.debug(f"    Name: {scope.name}")
    
    # Track unused imports and their locations
    unused_imports: Dict[Union[cst.Import, cst.ImportFrom], Set[str]] = defaultdict(set)
    imports_by_function: Dict[str, List[cst.CSTNode]] = defaultdict(list)
    
    # Track line numbers of global imports and imports used in class/decorator definitions
    global_import_lines = []
    keep_global_imports = set()
    
    # Keep whitelisted library imports at global scope
    if whitelist_libs:
        for scope in scopes:
            if isinstance(scope, cst.metadata.GlobalScope):
                for assignment in scope.assignments:
                    if isinstance(assignment.node, (cst.Import, cst.ImportFrom)):
                        import_str = wrapper.module.code_for_node(assignment.node)
                        if any(lib in import_str for lib in whitelist_libs):
                            keep_global_imports.add(assignment.node)
                            logging.debug(f"Keeping whitelisted import: {import_str}")
    
    # First pass: identify imports used in class definitions and decorators
    for scope in scopes:
        if isinstance(scope, cst.metadata.ClassScope):
            # Get the class node
            class_def = scope.node
            # Check class bases for imports
            for base in class_def.bases:
                if isinstance(base.value, cst.Name):
                    # Find the import that defines this base class
                    for assignment in scope.parent.assignments:
                        if (isinstance(assignment, cst.metadata.Assignment) and 
                            assignment.name == base.value.value and
                            isinstance(assignment.node, (cst.Import, cst.ImportFrom))):
                            keep_global_imports.add(assignment.node)
                            logging.debug(f"Found import used in class definition: {wrapper.module.code_for_node(assignment.node)}")
            
            # Check class decorators
            for decorator in class_def.decorators:
                if isinstance(decorator.decorator, cst.Name):
                    # Find the import that defines this decorator
                    for assignment in scope.parent.assignments:
                        if (isinstance(assignment, cst.metadata.Assignment) and 
                            assignment.name == decorator.decorator.value and
                            isinstance(assignment.node, (cst.Import, cst.ImportFrom))):
                            keep_global_imports.add(assignment.node)
                            logging.debug(f"Found import used in class decorator: {wrapper.module.code_for_node(assignment.node)}")
        
        elif isinstance(scope, cst.metadata.FunctionScope):
            # Get the function node
            func_def = scope.node
            # Skip lambda functions as they don't have decorators
            if isinstance(func_def, cst.Lambda):
                continue
            
            # Check function decorators
            for decorator in func_def.decorators:
                if isinstance(decorator.decorator, cst.Name):
                    # Find the import that defines this decorator
                    for assignment in scope.parent.assignments:
                        if (isinstance(assignment, cst.metadata.Assignment) and 
                            assignment.name == decorator.decorator.value and
                            isinstance(assignment.node, (cst.Import, cst.ImportFrom))):
                            keep_global_imports.add(assignment.node)
                            logging.debug(f"Found import used in function decorator: {wrapper.module.code_for_node(assignment.node)}")
    
    # Analyze scopes to find unused imports and function usage
    for scope in scopes:
        scope_name = getattr(scope, 'name', 'global')
        assignments = list(scope.assignments)  # Convert to list
        logging.debug(f"\nAnalyzing scope: {scope_name}")
        logging.debug(f"  Found {len(assignments)} assignments")
        
        for assignment in assignments:
            if isinstance(assignment, cst.metadata.Assignment):
                node = assignment.node
                if isinstance(node, (cst.Import, cst.ImportFrom)):
                    # Get the line number of this import
                    pos = wrapper.resolve(cst.metadata.PositionProvider)[node]
                    logging.debug(f"  Found import at line {pos.start.line}: {wrapper.module.code_for_node(node)}")
                    logging.debug(f"    Assignment name: {assignment.name}")
                    logging.debug(f"    References: {len(assignment.references)}")
                    
                    if isinstance(scope, cst.metadata.GlobalScope):
                        global_import_lines.append(pos.start.line)
                        logging.debug(f"    Added to global imports")
                        
                    # Skip moving imports used in class definitions or decorators
                    if node in keep_global_imports:
                        logging.debug(f"    Keeping as global (used in class/decorator)")
                        continue
                        
                    if len(assignment.references) == 0:
                        unused_imports[node].add(assignment.name)
                        logging.debug(f"    Marked as unused")
                    else:
                        logging.debug(f"    Reference locations:")
                        for ref in assignment.references:
                            ref_scope = ref.scope
                            ref_scope_name = getattr(ref_scope, 'name', 'global')
                            logging.debug(f"      - In scope: {ref_scope_name} ({type(ref_scope).__name__})")
                            if isinstance(ref.scope, cst.metadata.scope_provider.FunctionScope):
                                imports_by_function[ref.scope.name].append(node)
                                logging.debug(f"        Added to function imports for {ref.scope.name}")

    logging.debug("\nSummary:")
    logging.debug("Unused imports:")
    for node, names in unused_imports.items():
        logging.debug(f"  {wrapper.module.code_for_node(node)}: {names}")
    
    logging.debug("\nImports by function:")
    for func_name, imports in imports_by_function.items():
        logging.debug(f"  {func_name}:")
        for imp in imports:
            logging.debug(f"    {wrapper.module.code_for_node(imp)}")

    # Create transformers
    transformers = []
    
    # Add RemoveUnusedImportTransformer if needed
    if remove_unused_imports:
        transformers.append(RemoveUnusedImportTransformer(
            unused_imports, 
            keep_old_imports=keep_old_imports,
            module=wrapper.module
        ))
    
    # Add MoveImportsTransformer
    transformers.append(MoveImportsTransformer(imports_by_function, module=wrapper.module))
    
    # Apply transformations
    modified_module = wrapper.module
    for transformer in transformers:
        modified_module = modified_module.visit(transformer)
    
    # Create a temporary file
    temp_output = Path(output_path).with_suffix('.tmp')
    try:
        # Write modified code to temp file
        temp_output.write_text(modified_module.code)
        
        # Read the temp file and modify global imports
        with temp_output.open('r') as f:
            lines = f.readlines()
        
        # Comment out global imports except those used in class definitions or decorators
        modified_lines = []
        for i, line in enumerate(lines, start=1):
            line_contains_kept_import = any(
                wrapper.module.code_for_node(imp) in line 
                for imp in keep_global_imports
            )
            
            if (i in global_import_lines and line.strip() and 
                not line.strip().startswith('#') and 
                not line_contains_kept_import):
                modified_lines.append(f"# {line}")
                logging.debug(f"Commented out line {i}: {line.strip()}")
            else:
                modified_lines.append(line)
        
        # Write final output
        Path(output_path).write_text(''.join(modified_lines))
        
        # Clean up temp file
        temp_output.unlink()
        
    except Exception as e:
        # Clean up temp file if it exists
        if temp_output.exists():
            temp_output.unlink()
        raise e
    
    # Log changes if requested
    if log_path:
        with open(log_path, 'w') as f:
            # Log unused imports
            for node, names in unused_imports.items():
                for name in names:
                    f.write(f"Unused import: {name}\n")
            
            # Log imports moved to functions
            for func_name, imports in imports_by_function.items():
                f.write(f"\nImports moved to function {func_name}:\n")
                for imp in imports:
                    # Use module.code_for_node for generating code
                    f.write(f"  {wrapper.module.code_for_node(imp)}\n")

def main():
    parser = argparse.ArgumentParser(description='Move global imports into functions where they are used.')
    parser.add_argument('file', type=str, help='Python file to process')
    parser.add_argument('--log', type=str, help='Log file to write changes to')
    parser.add_argument('--log-level', type=str, default='DEBUG',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Set the logging level')
    parser.add_argument('-o', '--output', type=str, default=None,
                      help='Modified file path (default is with a suffix "_im")')
    parser.add_argument('--keep-old-imports', action='store_true', default=True,
                      help='Keep old imports as comments (default: True)')
    parser.add_argument('--remove-unused-imports', action='store_true', default=True,
                      help='Remove unused imports instead of commenting them (default: True)')
    parser.add_argument('--whitelist', type=str,
                      help='Comma-separated list of libraries to keep at global scope')
    parser.add_argument('--ignore-files', type=str,
                      help='Regular expression pattern for files to ignore')

    args = parser.parse_args()
    
    # Process whitelist
    whitelist_libs = set(lib.strip() for lib in args.whitelist.split(',')) if args.whitelist else None
    
    # If the --output flag is not set, create default output path
    if args.output is None:
        args.output = str(Path(args.file).with_suffix('')) + '_im.py'

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    try:
        source_path = Path(args.file)
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {args.file}")
            
        # Check if file should be ignored
        if args.ignore_files and re.match(args.ignore_files, str(source_path)):
            logging.info(f"Skipping ignored file: {source_path}")
            return
            
        process_file(
            source_path,
            args.log,
            args.output,
            keep_old_imports=args.keep_old_imports,
            remove_unused_imports=args.remove_unused_imports,
            whitelist_libs=whitelist_libs,
        )
        logging.info(f"Successfully processed {args.file} --> output file: {args.output}")
        
    except Exception as e:
        logging.error(f"Error processing file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
    ## Basic usage
# python import_mover.py your_script.py

# # With logging to file
# python import_mover.py your_script.py --log changes.log

# # With specific log level
# python import_mover.py your_script.py --log-level DEBUG