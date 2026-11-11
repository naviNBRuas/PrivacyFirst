"""Enforces the 'no network code' promise structurally."""
import ast
from pathlib import Path

BANNED = {"socket", "urllib", "urllib3", "http", "httpx", "requests", "aiohttp", "ftplib", "smtplib",
          "telnetlib", "websocket", "websockets", "paramiko", "boto3", "grpc"}


def test_package_imports_no_network_modules():
    root = Path(__file__).resolve().parents[1] / "src" / "privacyfirst"
    bad = []
    for f in root.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            bad += [(f.name, n) for n in names if n in BANNED]
    assert not bad, f"network-capable imports found: {bad}"
