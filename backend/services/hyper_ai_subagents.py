"""
Hyper AI Sub-agents - Tools for calling specialized AI assistants

Each sub-agent reuses existing AI assistant's conversation system:
- call_prompt_ai: Prompt AI for trading prompt generation/optimization
- call_program_ai: Program AI for strategy code writing
- call_signal_ai: Signal AI for signal pool configuration
- call_attribution_ai: Attribution AI for trade analysis

Sub-agents maintain their own conversation history in their respective tables.
Hyper AI passes conversation_id to continue previous sessions.
"""

import json
import logging
import time
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Sub-agent tool definitions in OpenAI format
SUBAGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "call_prompt_ai",
            "description": """Call Prompt AI to generate or optimize trading prompts.
Use this when user wants to:
- Create a new trading prompt from scratch
- Optimize an existing prompt
- Add/modify variables in a prompt
- Validate prompt syntax

The sub-agent has access to variables reference and can preview prompts with real data.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description for Prompt AI"
                    },
                    "conversation_id": {
                        "type": "integer",
                        "description": "Optional: Continue a previous Prompt AI conversation"
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "AI account ID to use for LLM calls"
                    }
                },
                "required": ["task", "account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_program_ai",
            "description": """Call Program AI to write or modify trading strategy code.
Use this when user wants to:
- Create a new trading program/strategy
- Modify existing program code
- Debug or fix code issues
- Add new features to a program

The sub-agent can query market data, validate code, and run test executions.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description for Program AI"
                    },
                    "conversation_id": {
                        "type": "integer",
                        "description": "Optional: Continue a previous Program AI conversation"
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "AI account ID to use for LLM calls"
                    },
                    "program_id": {
                        "type": "integer",
                        "description": "Optional: Program ID if editing existing program"
                    }
                },
                "required": ["task", "account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_signal_ai",
            "description": """Call Signal AI to configure signal pools.
Use this when user wants to:
- Create a new signal pool
- Modify signal pool configuration
- Add/remove signals from a pool
- Run signal backtest

The sub-agent can query available signals and run backtests.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description for Signal AI"
                    },
                    "conversation_id": {
                        "type": "integer",
                        "description": "Optional: Continue a previous Signal AI conversation"
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "AI account ID to use for LLM calls"
                    }
                },
                "required": ["task", "account_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_attribution_ai",
            "description": """Call Attribution AI to analyze trading performance.
Use this when user wants to:
- Analyze why a trade succeeded or failed
- Get performance attribution report
- Understand decision patterns
- Review historical trades

The sub-agent can query decision logs and provide detailed analysis.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Task description for Attribution AI"
                    },
                    "conversation_id": {
                        "type": "integer",
                        "description": "Optional: Continue a previous Attribution AI conversation"
                    },
                    "account_id": {
                        "type": "integer",
                        "description": "AI account ID to use for LLM calls"
                    }
                },
                "required": ["task", "account_id"]
            }
        }
    }
]


def _run_subagent_stream(generator) -> Dict[str, Any]:
    """
    Run a sub-agent's streaming generator and collect results.
    Returns the final result when 'done' event is received.

    Supports two SSE formats:
    1. Simple format: "data: {"type": "xxx", ...}\n\n"
    2. Standard format: "event: xxx\ndata: {...}\n\n" (as single string)
    """
    result = {
        "status": "failed",
        "content": "",
        "conversation_id": None,
        "message_id": None,
        "tool_calls": [],
        "error": None
    }

    try:
        for event_str in generator:
            # Skip empty strings
            if not event_str or not event_str.strip():
                continue

            event_type = None
            event_data = None

            # Check if this is standard SSE format: "event: xxx\ndata: {...}\n\n"
            if event_str.startswith("event: "):
                # Parse standard SSE format
                lines = event_str.strip().split("\n")
                for line in lines:
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            event_data = json.loads(line[6:].strip())
                        except json.JSONDecodeError:
                            continue
            elif event_str.startswith("data: "):
                # Simple format: "data: {"type": "xxx", ...}"
                try:
                    event_data = json.loads(event_str[6:].strip())
                    event_type = event_data.get("type")
                except json.JSONDecodeError:
                    continue

            # Skip if we couldn't parse
            if not event_type or event_data is None:
                continue

            if event_type == "conversation_created":
                result["conversation_id"] = event_data.get("conversation_id")

            elif event_type == "tool_call":
                result["tool_calls"].append({
                    "name": event_data.get("name"),
                    # Handle both formats: "args" or "arguments"
                    "args": event_data.get("args") or event_data.get("arguments")
                })

            elif event_type == "content":
                result["content"] += event_data.get("content", "")

            elif event_type == "done":
                result["status"] = "success"
                # Handle both formats: "content" field or direct content
                result["content"] = event_data.get("content", result["content"])
                result["conversation_id"] = event_data.get("conversation_id", result["conversation_id"])
                result["message_id"] = event_data.get("message_id")
                break

            elif event_type == "error":
                result["status"] = "failed"
                # Handle both formats: "content" or "message" field
                result["error"] = event_data.get("content") or event_data.get("message", "Unknown error")
                break

            elif event_type == "interrupted":
                result["status"] = "interrupted"
                result["error"] = event_data.get("error", "Interrupted")
                result["message_id"] = event_data.get("message_id")
                break

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"[_run_subagent_stream] Error: {e}")

    return result


def execute_call_prompt_ai(
    db: Session,
    task: str,
    account_id: int,
    conversation_id: Optional[int] = None,
    user_id: int = 1
) -> str:
    """
    Execute Prompt AI sub-agent.
    Reuses existing ai_prompt_generation_service conversation system.
    """
    from services.ai_prompt_generation_service import generate_prompt_with_ai_stream
    from database.models import Account

    logger.info(f"[call_prompt_ai] task={task[:50]}..., account_id={account_id}, conv_id={conversation_id}")

    try:
        # Prompt AI requires Account object, not account_id
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.account_type == "AI"
        ).first()

        if not account:
            return json.dumps({
                "subagent": "prompt_ai",
                "status": "failed",
                "error": f"AI account {account_id} not found"
            })

        generator = generate_prompt_with_ai_stream(
            db=db,
            account=account,
            user_message=task,
            conversation_id=conversation_id,
            user_id=user_id
        )

        result = _run_subagent_stream(generator)

        return json.dumps({
            "subagent": "prompt_ai",
            "status": result["status"],
            "conversation_id": result["conversation_id"],
            "message_id": result["message_id"],
            "content": result["content"][:2000] if result["content"] else None,
            "tool_calls_count": len(result["tool_calls"]),
            "error": result["error"]
        })

    except Exception as e:
        logger.error(f"[call_prompt_ai] Error: {e}")
        return json.dumps({"subagent": "prompt_ai", "status": "failed", "error": str(e)})


def execute_call_program_ai(
    db: Session,
    task: str,
    account_id: int,
    conversation_id: Optional[int] = None,
    program_id: Optional[int] = None,
    user_id: int = 1
) -> str:
    """
    Execute Program AI sub-agent.
    Reuses existing ai_program_service conversation system.
    """
    from services.ai_program_service import generate_program_with_ai_stream

    logger.info(f"[call_program_ai] task={task[:50]}..., account_id={account_id}, conv_id={conversation_id}")

    try:
        generator = generate_program_with_ai_stream(
            db=db,
            account_id=account_id,
            user_message=task,
            conversation_id=conversation_id,
            program_id=program_id,
            user_id=user_id
        )

        result = _run_subagent_stream(generator)

        return json.dumps({
            "subagent": "program_ai",
            "status": result["status"],
            "conversation_id": result["conversation_id"],
            "message_id": result["message_id"],
            "content": result["content"][:2000] if result["content"] else None,
            "tool_calls_count": len(result["tool_calls"]),
            "error": result["error"]
        })

    except Exception as e:
        logger.error(f"[call_program_ai] Error: {e}")
        return json.dumps({"subagent": "program_ai", "status": "failed", "error": str(e)})


def execute_call_signal_ai(
    db: Session,
    task: str,
    account_id: int,
    conversation_id: Optional[int] = None,
    user_id: int = 1
) -> str:
    """
    Execute Signal AI sub-agent.
    Reuses existing ai_signal_generation_service conversation system.
    """
    from services.ai_signal_generation_service import generate_signal_with_ai_stream

    logger.info(f"[call_signal_ai] task={task[:50]}..., account_id={account_id}, conv_id={conversation_id}")

    try:
        generator = generate_signal_with_ai_stream(
            db=db,
            account_id=account_id,
            user_message=task,
            conversation_id=conversation_id,
            user_id=user_id
        )

        result = _run_subagent_stream(generator)

        return json.dumps({
            "subagent": "signal_ai",
            "status": result["status"],
            "conversation_id": result["conversation_id"],
            "message_id": result["message_id"],
            "content": result["content"][:2000] if result["content"] else None,
            "tool_calls_count": len(result["tool_calls"]),
            "error": result["error"]
        })

    except Exception as e:
        logger.error(f"[call_signal_ai] Error: {e}")
        return json.dumps({"subagent": "signal_ai", "status": "failed", "error": str(e)})


def execute_call_attribution_ai(
    db: Session,
    task: str,
    account_id: int,
    conversation_id: Optional[int] = None,
    user_id: int = 1
) -> str:
    """
    Execute Attribution AI sub-agent.
    Reuses existing ai_attribution_service conversation system.
    """
    from services.ai_attribution_service import generate_attribution_analysis_stream

    logger.info(f"[call_attribution_ai] task={task[:50]}..., account_id={account_id}, conv_id={conversation_id}")

    try:
        generator = generate_attribution_analysis_stream(
            db=db,
            account_id=account_id,
            user_message=task,
            conversation_id=conversation_id,
            user_id=user_id
        )

        result = _run_subagent_stream(generator)

        return json.dumps({
            "subagent": "attribution_ai",
            "status": result["status"],
            "conversation_id": result["conversation_id"],
            "message_id": result["message_id"],
            "content": result["content"][:2000] if result["content"] else None,
            "tool_calls_count": len(result["tool_calls"]),
            "error": result["error"]
        })

    except Exception as e:
        logger.error(f"[call_attribution_ai] Error: {e}")
        return json.dumps({"subagent": "attribution_ai", "status": "failed", "error": str(e)})


def execute_subagent_tool(
    db: Session,
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: int = 1
) -> str:
    """
    Execute a sub-agent tool by name.
    This is the main entry point for Hyper AI to call sub-agents.
    """
    try:
        if tool_name == "call_prompt_ai":
            return execute_call_prompt_ai(
                db,
                task=arguments.get("task", ""),
                account_id=arguments.get("account_id"),
                conversation_id=arguments.get("conversation_id"),
                user_id=user_id
            )

        elif tool_name == "call_program_ai":
            return execute_call_program_ai(
                db,
                task=arguments.get("task", ""),
                account_id=arguments.get("account_id"),
                conversation_id=arguments.get("conversation_id"),
                program_id=arguments.get("program_id"),
                user_id=user_id
            )

        elif tool_name == "call_signal_ai":
            return execute_call_signal_ai(
                db,
                task=arguments.get("task", ""),
                account_id=arguments.get("account_id"),
                conversation_id=arguments.get("conversation_id"),
                user_id=user_id
            )

        elif tool_name == "call_attribution_ai":
            return execute_call_attribution_ai(
                db,
                task=arguments.get("task", ""),
                account_id=arguments.get("account_id"),
                conversation_id=arguments.get("conversation_id"),
                user_id=user_id
            )

        else:
            return json.dumps({"error": f"Unknown sub-agent tool: {tool_name}"})

    except Exception as e:
        logger.error(f"[execute_subagent_tool] Error executing {tool_name}: {e}")
        return json.dumps({"error": str(e)})

