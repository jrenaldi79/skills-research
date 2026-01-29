#!/usr/bin/env python3
"""
Claude Code Router Log Parser
Extracts and formats API request data for skill research analysis.

Usage:
    python log_parser.py <log_file> [--output <output.json>]
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime


def parse_log_line(line: str) -> dict | None:
    """Parse a single log line into a structured dict."""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def extract_request_body(log_entry: dict) -> dict | None:
    """Extract request body data from a log entry."""
    if log_entry.get("type") == "request body":
        return log_entry.get("data", {})
    return None


def format_system_prompts(system: list) -> list:
    """Format system prompt blocks with metadata."""
    formatted = []
    for i, block in enumerate(system):
        text = block.get("text", "")
        cache_control = block.get("cache_control", {})

        # Detect content type
        content_type = "unknown"
        if "billing-header" in text:
            content_type = "billing"
        elif "You are Claude Code" in text:
            content_type = "identity"
        elif "You are an interactive CLI" in text:
            content_type = "instructions"
        elif "skill" in text.lower():
            content_type = "skill-related"

        formatted.append({
            "index": i,
            "type": content_type,
            "length": len(text),
            "cache_control": cache_control,
            "content": text,
            "preview": text[:200].replace("\n", " ")
        })

    return formatted


def format_messages(messages: list) -> list:
    """Format message array with skill detection."""
    formatted = []

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", [])

        msg_data = {
            "index": i,
            "role": role,
            "blocks": []
        }

        if isinstance(content, list):
            for j, block in enumerate(content):
                block_type = block.get("type", "unknown")
                block_data = {
                    "index": j,
                    "type": block_type
                }

                if block_type == "text":
                    text = block.get("text", "")
                    has_skill_content = any([
                        "Base directory for this skill:" in text,
                        "<system-reminder>" in text and "skill" in text.lower(),
                        "SKILL.md" in text
                    ])
                    has_skill_reference = "skill" in text.lower() and not has_skill_content

                    block_data.update({
                        "length": len(text),
                        "has_skill_content": has_skill_content,
                        "has_skill_reference": has_skill_reference,
                        "content": text,
                        "preview": text[:300].replace("\n", " ")
                    })

                elif block_type == "tool_use":
                    block_data.update({
                        "tool_name": block.get("name", ""),
                        "tool_id": block.get("id", ""),
                        "input": block.get("input", {})
                    })

                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        block_data.update({
                            "tool_use_id": block.get("tool_use_id", ""),
                            "length": len(result_content),
                            "has_skill_content": "skill" in result_content.lower(),
                            "preview": result_content[:300].replace("\n", " ")
                        })

                msg_data["blocks"].append(block_data)

        formatted.append(msg_data)

    return formatted


def extract_skill_tool(tools: list) -> dict | None:
    """Extract the Skill tool definition."""
    for tool in tools:
        if tool.get("name") == "Skill":
            desc = tool.get("description", "")

            # Extract available skills section
            skills_start = desc.find("Available skills:")
            available_skills = ""
            if skills_start != -1:
                available_skills = desc[skills_start:]

            return {
                "name": "Skill",
                "description_length": len(desc),
                "available_skills_section": available_skills,
                "full_description": desc
            }
    return None


def analyze_log_file(log_path: str) -> dict:
    """Analyze a log file and extract structured data."""
    requests = []

    with open(log_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            entry = parse_log_line(line)
            if not entry:
                continue

            request_body = extract_request_body(entry)
            if request_body:
                req_id = entry.get("reqId", f"unknown-{line_num}")
                timestamp = entry.get("time", 0)

                # Extract components
                system = request_body.get("system", [])
                messages = request_body.get("messages", [])
                tools = request_body.get("tools", [])
                model = request_body.get("model", "")

                request_data = {
                    "request_id": req_id,
                    "timestamp": timestamp,
                    "timestamp_readable": datetime.fromtimestamp(timestamp/1000).isoformat() if timestamp else None,
                    "model": model,
                    "line_number": line_num,
                    "system_prompts": format_system_prompts(system),
                    "messages": format_messages(messages),
                    "skill_tool": extract_skill_tool(tools),
                    "tool_count": len(tools),
                    "stats": {
                        "system_prompt_total_chars": sum(len(b.get("text", "")) for b in system),
                        "message_count": len(messages),
                        "has_skill_invocation": any(
                            b.get("tool_name") == "Skill"
                            for m in messages
                            for b in (m.get("content", []) if isinstance(m.get("content"), list) else [])
                            if isinstance(b, dict)
                        ),
                        "has_skill_content_in_messages": any(
                            b.get("has_skill_content", False)
                            for m in messages
                            for b in (m.get("content", []) if isinstance(m.get("content"), list) else [])
                            if isinstance(b, dict)
                        )
                    }
                }

                requests.append(request_data)

    return {
        "log_file": str(log_path),
        "total_requests": len(requests),
        "requests": requests
    }


def main():
    parser = argparse.ArgumentParser(description="Parse Claude Code Router logs")
    parser.add_argument("log_file", help="Path to the log file")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--pretty", "-p", action="store_true", help="Pretty print JSON")

    args = parser.parse_args()

    result = analyze_log_file(args.log_file)

    indent = 2 if args.pretty else None
    output = json.dumps(result, indent=indent, ensure_ascii=False)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
