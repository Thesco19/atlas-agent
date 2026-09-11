#!/usr/bin/env python3
"""Exemplo de Servidor MCP (Model Context Protocol) 100% biblioteca padrão do Python.
Compatível com Linux 32-bit e 64-bit, sem precisar de Node.js ou pacotes externos.

Para testar no atlas-agent, basta criar um arquivo .mcp.json no seu projeto com:
{
  "mcpServers": {
    "demo": {
      "command": "python3",
      "args": ["examples/mcp_server_demo.py"]
    }
  }
}
"""
import sys
import json
import os
import platform
import datetime

def handle_initialize(req_id, params):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "atlas-demo-mcp-server",
                "version": "1.0.0"
            }
        }
    }

def handle_tools_list(req_id):
    tools = [
        {
            "name": "get_system_info",
            "description": "Retorna informações detalhadas do hardware, arquitetura 32/64-bit e sistema operacional.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_current_time",
            "description": "Retorna data, hora atual e timezone do sistema.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "Formato opcional ('iso' ou 'human')",
                        "default": "human"
                    }
                },
                "required": []
            }
        },
        {
            "name": "calculate_expression",
            "description": "Calcula expressões matemáticas com precisão.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Expressão aritmética (ex: '2 ** 16', '1024 * 768')"
                    }
                },
                "required": ["expression"]
            }
        }
    ]
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": tools
        }
    }

def handle_tools_call(req_id, params):
    name = params.get("name")
    args = params.get("arguments", {})

    if name == "get_system_info":
        mem_mb = "N/A"
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_mb = f"{int(line.split()[1]) // 1024} MB"
                        break
        except Exception:
            pass

        info = {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
            "python": platform.python_version(),
            "ram_total": mem_mb
        }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(info, indent=2)
                    }
                ]
            }
        }

    elif name == "get_current_time":
        now = datetime.datetime.now()
        fmt = args.get("format", "human")
        text = now.isoformat() if fmt == "iso" else now.strftime("%A, %d de %B de %Y - %H:%M:%S")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Hora local: {text}"}]
            }
        }

    elif name == "calculate_expression":
        expr = args.get("expression", "").strip()
        # Avaliação segura apenas para operações aritméticas básicas
        allowed_chars = set("0123456789+-*/(). %")
        if not expr or not all(c in allowed_chars for c in expr):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": "Expressão inválida ou contém caracteres proibidos."}]
                }
            }
        try:
            val = eval(expr, {"__builtins__": None}, {})
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"{expr} = {val}"}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Erro no cálculo: {e}"}]
                }
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Ferramenta desconhecida: {name}"
        }
    }

def main():
    """Loop principal de leitura de comandos JSON-RPC 2.0 via stdin."""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            msg = json.loads(line)
            req_id = msg.get("id")
            method = msg.get("method")

            if method == "initialize":
                resp = handle_initialize(req_id, msg.get("params", {}))
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                # Notificação - sem resposta
                continue

            elif method == "tools/list":
                resp = handle_tools_list(req_id)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                resp = handle_tools_call(req_id, msg.get("params", {}))
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif req_id is not None:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Método não suportado: {method}"
                    }
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            sys.stderr.write(f"MCP Server Error: {e}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    main()
