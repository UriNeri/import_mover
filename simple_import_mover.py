import ast
import inspect

def move_global_imports_to_functions(code_string):
    """
    Moves global import statements into the functions where they are used.

    Args:
        code_string (str): The Python code as a string.

    Returns:
        str: Modified Python code with imports moved into functions.
    """
    tree = ast.parse(code_string)
    global_imports = []
    function_nodes = {}

    # Separate global imports and function definitions
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            global_imports.append(node)
        elif isinstance(node, ast.FunctionDef):
            function_nodes[node.name] = node

    # Move relevant imports into functions
    for function_name, function_node in function_nodes.items():
        imports_to_move = []
        for global_import in global_imports:
            for node in ast.walk(function_node):
                if isinstance(node, ast.Name):
                    imported_names = []
                    if isinstance(global_import, ast.Import):
                        imported_names = [alias.name for alias in global_import.names]
                    elif isinstance(global_import, ast.ImportFrom):
                         imported_names = [alias.name for alias in global_import.names]
                    if node.id in imported_names or (isinstance(global_import, ast.ImportFrom) and node.id == global_import.module):
                        imports_to_move.append(global_import)
                        break

        # Add imports to the beginning of the function body
        function_node.body = imports_to_move + function_node.body

        # Remove moved imports from global imports list
        for import_node in imports_to_move:
            if import_node in global_imports:
                global_imports.remove(import_node)

    # Reconstruct the code
    new_body = global_imports + list(function_nodes.values())
    tree.body = new_body
    return ast.unparse(tree)

# Example usage:
code = open("test/dummy_script.py").read()

modified_code = move_global_imports_to_functions(code)
print(modified_code)