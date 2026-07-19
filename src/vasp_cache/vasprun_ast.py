"""vasprun XML AST — ElementTree AST roundtrip per spec §4.2."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _make_parser() -> ET.XMLParser:
    return ET.XMLParser(
        target=ET.TreeBuilder(insert_comments=True, insert_pis=True),
    )



def parse_to_ast(path: Path | str) -> dict[str, Any]:
    tree = ET.parse(Path(path), parser=_make_parser())
    return _etree_to_ast(tree.getroot())


def ast_to_json(ast: dict[str, Any]) -> str:
    return json.dumps(ast, ensure_ascii=False, separators=(",", ":"))


def json_to_ast(text: str) -> dict[str, Any]:
    return json.loads(text)


def ast_to_xml(ast: dict[str, Any]) -> str:
    root = _ast_to_etree(ast)
    return ET.tostring(root, encoding="unicode")


def write_xml(ast: dict[str, Any], path: Path | str) -> None:
    root = _ast_to_etree(ast)
    tree = ET.ElementTree(root)
    tree.write(Path(path), encoding="UTF-8", xml_declaration=True)


def _etree_to_ast(node: ET.Element) -> dict[str, Any]:
    if node.tag is ET.Comment:
        return {
            "node_type": "comment",
            "text": node.text,
            "tail": node.tail,
        }
    if node.tag is ET.ProcessingInstruction:
        return {
            "node_type": "pi",
            "text": node.text,
            "tail": node.tail,
        }
    return {
        "node_type": "element",
        "tag": node.tag,
        "attrib": dict(node.attrib or {}),
        "text": node.text,
        "tail": node.tail,
        "children": [_etree_to_ast(c) for c in node],
    }


def _ast_to_etree(ast: dict[str, Any]) -> ET.Element:
    if ast["node_type"] == "comment":
        el: ET.Element = ET.Comment(ast["text"])
    elif ast["node_type"] == "pi":
        target, data = _split_pi(ast.get("text", ""))
        el = ET.ProcessingInstruction(target, data)
    else:
        el = ET.Element(ast["tag"], ast.get("attrib", {}))
        for child in ast.get("children", []):
            el.append(_ast_to_etree(child))
    el.text = ast.get("text")
    el.tail = ast.get("tail")
    return el


def _split_pi(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    i = text.index(" ") if " " in text else len(text)
    return text[:i], text[i + 1 :] if i < len(text) else ""
