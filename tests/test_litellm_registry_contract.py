"""The update_model registry route must describe the existing handler's route."""
import ast
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'apps/litellm/vendor/woow_litellm_mcp_server'


def test_update_model_registry_matches_handler_method_and_path():
    registry = runpy.run_path(str(PACKAGE / 'registry.py'))['TOOL_REGISTRY']
    [spec] = [tool for tool in registry if tool.name == 'litellm_update_model']
    tree = ast.parse((PACKAGE / 'tools/models.py').read_text())
    [handler] = [node for node in ast.walk(tree)
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == spec.name]
    [returned] = [node.value for node in handler.body if isinstance(node, ast.Return)]
    assert isinstance(returned, ast.Await)
    call = returned.value
    assert spec.method == call.func.attr.upper() == 'PATCH'
    path = call.args[0]
    assert isinstance(path, ast.JoinedStr)
    prefix, parameter, suffix = path.values
    assert isinstance(parameter, ast.FormattedValue)
    assert parameter.value.func.id == 'quote' and parameter.value.args[0].id == 'model_id'
    assert {arg.arg: ast.literal_eval(arg.value) for arg in parameter.value.keywords} == {'safe': ''}
    assert spec.path == prefix.value + '{model_id}' + suffix.value
    assert spec.operations == ('update',) and spec.dangerous is False
