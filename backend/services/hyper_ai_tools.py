"""
Hyper AI Tools - Tools for Hyper AI main agent

Provides tools for:
- System overview and diagnostics
- Wallet status queries
- API reference documentation
- Market data (klines, regime, flow)
- Create/save operations (signal pool, prompt, program, AI trader)
- Sub-agent calls (Prompt AI, Program AI, Signal AI, Attribution AI)
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import text, func

from services.hyper_ai_subagents import SUBAGENT_TOOLS, execute_subagent_tool

logger = logging.getLogger(__name__)


# Tool definitions in OpenAI format
HYPER_AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_overview",
            "description": "Get high-level system status: wallets, AI traders, strategies, signal pools, positions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_status",
            "description": "Get wallet balance and position summary (read-only, no credentials exposed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "exchange": {
                        "type": "string",
                        "enum": ["hyperliquid", "binance", "all"],
                        "description": "Filter by exchange (default: all)"
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["testnet", "mainnet", "all"],
                        "description": "Filter by environment (default: all)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_api_reference",
            "description": "Get API reference docs for Prompt variables or Program MarketData/Decision APIs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {
                        "type": "string",
                        "enum": ["prompt", "program"],
                        "description": "Document type: prompt (variables) or program (MarketData/Decision API)"
                    },
                    "api_type": {
                        "type": "string",
                        "enum": ["market", "decision", "all"],
                        "description": "For program only: which API docs (default: all)"
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["en", "zh"],
                        "description": "Language (default: en)"
                    }
                },
                "required": ["doc_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_klines",
            "description": "Get K-line/candlestick data for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol (e.g., BTC, ETH)"},
                    "period": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"], "description": "K-line period (default: 1h)"},
                    "limit": {"type": "integer", "description": "Number of candles (default: 50, max: 200)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_regime",
            "description": "Get current market regime classification for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol"},
                    "period": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h"], "description": "Time period (default: 1h)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_flow",
            "description": "Get market flow data (CVD, OI, Funding, etc.) for a symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol"},
                    "period": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h"], "description": "Time period (default: 1h)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_logs",
            "description": "Get recent system error/warning logs for troubleshooting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["error", "warning", "all"], "description": "Log level filter (default: error)"},
                    "limit": {"type": "integer", "description": "Max entries (default: 20, max: 50)"},
                    "trader_id": {"type": "integer", "description": "Filter by AI Trader ID"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_contact_config",
            "description": "Get support channel URLs (Twitter, Telegram, GitHub).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_trader_issues",
            "description": "Check why an AI Trader is not triggering and provide actionable suggestions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trader_id": {"type": "integer", "description": "AI Trader ID to diagnose"}
                },
                "required": ["trader_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_signal_pool",
            "description": "Create or update a signal pool configuration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {"type": "integer", "description": "Pool ID to update (omit for create)"},
                    "pool_name": {"type": "string", "description": "Display name for the pool"},
                    "symbols": {"type": "array", "items": {"type": "string"}, "description": "Symbols to monitor"},
                    "signal_ids": {"type": "array", "items": {"type": "integer"}, "description": "Signal definition IDs"},
                    "logic": {"type": "string", "enum": ["AND", "OR"], "description": "Logic operator (default: OR)"},
                    "exchange": {"type": "string", "enum": ["hyperliquid", "binance"], "description": "Exchange (default: hyperliquid)"},
                    "enabled": {"type": "boolean", "description": "Enable/disable pool (default: true)"}
                },
                "required": ["pool_name", "symbols", "signal_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_prompt",
            "description": "Create or update a trading prompt template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt_id": {"type": "integer", "description": "Prompt ID to update (omit for create)"},
                    "name": {"type": "string", "description": "Display name"},
                    "description": {"type": "string", "description": "Brief description"},
                    "template_text": {"type": "string", "description": "Main prompt content"}
                },
                "required": ["name", "template_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_program",
            "description": "Create or update a trading program.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_id": {"type": "integer", "description": "Program ID to update (omit for create)"},
                    "name": {"type": "string", "description": "Display name"},
                    "description": {"type": "string", "description": "Brief description"},
                    "code": {"type": "string", "description": "Python strategy code"}
                },
                "required": ["name", "code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_ai_trader",
            "description": "Create a new AI Trader with LLM config. Tests LLM connection before saving. Strategy binding and wallet setup are done separately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Display name for the trader"},
                    "model": {"type": "string", "description": "LLM model name (e.g., gpt-4o, deepseek-chat, claude-3.5-sonnet)"},
                    "base_url": {"type": "string", "description": "LLM API base URL (e.g., https://api.openai.com/v1)"},
                    "api_key": {"type": "string", "description": "LLM API key"}
                },
                "required": ["name", "model", "base_url", "api_key"]
            }
        }
    }
]

# Combine base tools with sub-agent tools
HYPER_AI_TOOLS = HYPER_AI_TOOLS + SUBAGENT_TOOLS


# =============================================================================
# Tool Execution Functions
# =============================================================================

def execute_get_system_overview(db: Session) -> str:
    """Get high-level system status summary."""
    from database.models import (
        Account, HyperliquidWallet, BinanceWallet, PromptTemplate,
        TradingProgram, SignalPool, AccountPromptBinding, AccountProgramBinding,
        HyperliquidPosition
    )

    try:
        result = {
            "wallets": {"hyperliquid": {}, "binance": {}},
            "ai_traders": {"total": 0, "active": 0, "using_prompt": 0, "using_program": 0},
            "strategies": {"prompts": 0, "programs": 0},
            "signal_pools": {"hyperliquid": 0, "binance": 0},
            "open_positions": {}
        }

        # Count wallets by exchange and environment
        hl_wallets = db.query(
            HyperliquidWallet.environment, func.count(HyperliquidWallet.id)
        ).filter(HyperliquidWallet.is_active == "true").group_by(HyperliquidWallet.environment).all()
        for env, count in hl_wallets:
            result["wallets"]["hyperliquid"][env] = count

        bn_wallets = db.query(
            BinanceWallet.environment, func.count(BinanceWallet.id)
        ).filter(BinanceWallet.is_active == "true").group_by(BinanceWallet.environment).all()
        for env, count in bn_wallets:
            result["wallets"]["binance"][env] = count

        # Count AI Traders
        total_traders = db.query(Account).filter(Account.is_active == "true").count()
        active_traders = db.query(Account).filter(
            Account.is_active == "true",
            Account.auto_trading_enabled == "true"
        ).count()
        result["ai_traders"]["total"] = total_traders
        result["ai_traders"]["active"] = active_traders

        # Count by strategy type
        prompt_bindings = db.query(AccountPromptBinding).count()
        program_bindings = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.is_active == True
        ).count()
        result["ai_traders"]["using_prompt"] = prompt_bindings
        result["ai_traders"]["using_program"] = program_bindings

        # Count strategies
        user_prompts = db.query(PromptTemplate).filter(
            PromptTemplate.is_system == "false",
            PromptTemplate.is_deleted == "false"
        ).count()
        programs = db.query(TradingProgram).count()
        result["strategies"]["prompts"] = user_prompts
        result["strategies"]["programs"] = programs

        # Count signal pools by exchange
        pools = db.query(
            SignalPool.exchange, func.count(SignalPool.id)
        ).filter(SignalPool.enabled == True).group_by(SignalPool.exchange).all()
        for exchange, count in pools:
            result["signal_pools"][exchange or "hyperliquid"] = count

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"[get_system_overview] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_wallet_status(db: Session, exchange: str = "all", environment: str = "all") -> str:
    """Get wallet balance and position summary using real-time API (same as frontend)."""
    from database.models import HyperliquidWallet, BinanceWallet, Account
    from services.hyperliquid_trading_client import get_cached_trading_client
    from services.binance_trading_client import BinanceTradingClient
    from utils.encryption import decrypt_private_key

    try:
        wallets = []

        # Query Hyperliquid wallets - use real-time API
        if exchange in ["all", "hyperliquid"]:
            hl_query = db.query(HyperliquidWallet, Account).join(
                Account, HyperliquidWallet.account_id == Account.id
            ).filter(HyperliquidWallet.is_active == "true")

            if environment != "all":
                hl_query = hl_query.filter(HyperliquidWallet.environment == environment)

            for wallet, account in hl_query.all():
                try:
                    # Decrypt private key and use cached client
                    private_key = decrypt_private_key(wallet.private_key_encrypted)
                    client = get_cached_trading_client(
                        account_id=account.id,
                        private_key=private_key,
                        environment=wallet.environment,
                        wallet_address=wallet.wallet_address
                    )
                    account_state = client.get_account_state(db)

                    wallet_info = {
                        "exchange": "hyperliquid",
                        "environment": wallet.environment,
                        "wallet_address": wallet.wallet_address[:10] + "..." + wallet.wallet_address[-6:],
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {
                            "total_equity": float(account_state.get("total_equity", 0)),
                            "available_balance": float(account_state.get("available_balance", 0)),
                            "used_margin": float(account_state.get("used_margin", 0))
                        },
                        "positions": [],
                        "last_updated": "real-time"
                    }

                    # Get positions from API response
                    for pos in account_state.get("positions", []):
                        szi = float(pos.get("szi", 0) or 0)
                        if szi != 0:
                            wallet_info["positions"].append({
                                "symbol": pos.get("coin", ""),
                                "size": abs(szi),
                                "side": "long" if szi > 0 else "short",
                                "unrealized_pnl": float(pos.get("unrealized_pnl", 0) or 0)
                            })

                    wallets.append(wallet_info)
                except Exception as e:
                    logger.warning(f"[get_wallet_status] Failed to get Hyperliquid data for {account.name}: {e}")
                    wallets.append({
                        "exchange": "hyperliquid",
                        "environment": wallet.environment,
                        "wallet_address": wallet.wallet_address[:10] + "..." + wallet.wallet_address[-6:],
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {"total_equity": 0, "available_balance": 0, "used_margin": 0},
                        "positions": [],
                        "error": str(e)
                    })

        # Query Binance wallets - use real-time API
        if exchange in ["all", "binance"]:
            bn_query = db.query(BinanceWallet, Account).join(
                Account, BinanceWallet.account_id == Account.id
            ).filter(BinanceWallet.is_active == "true")

            if environment != "all":
                bn_query = bn_query.filter(BinanceWallet.environment == environment)

            for wallet, account in bn_query.all():
                try:
                    # Decrypt API keys
                    api_key = decrypt_private_key(wallet.api_key_encrypted)
                    secret_key = decrypt_private_key(wallet.secret_key_encrypted)
                    client = BinanceTradingClient(api_key, secret_key, wallet.environment)
                    balance = client.get_balance()

                    wallet_info = {
                        "exchange": "binance",
                        "environment": wallet.environment,
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {
                            "total_equity": float(balance.get("total_equity", 0)),
                            "available_balance": float(balance.get("available_balance", 0)),
                            "unrealized_pnl": float(balance.get("unrealized_pnl", 0))
                        },
                        "positions": [],
                        "last_updated": "real-time"
                    }
                    wallets.append(wallet_info)
                except Exception as e:
                    logger.warning(f"[get_wallet_status] Failed to get Binance data for {account.name}: {e}")
                    wallets.append({
                        "exchange": "binance",
                        "environment": wallet.environment,
                        "trader_id": account.id,
                        "trader_name": account.name,
                        "balance": {"total_equity": 0, "available_balance": 0, "unrealized_pnl": 0},
                        "positions": [],
                        "error": str(e)
                    })

        return json.dumps({"wallets": wallets}, indent=2)

    except Exception as e:
        logger.error(f"[get_wallet_status] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_api_reference(doc_type: str, api_type: str = "all", lang: str = "en") -> str:
    """Get API reference documentation."""
    try:
        if doc_type == "prompt":
            # Read prompt variables reference document
            filename = "PROMPT_VARIABLES_REFERENCE_ZH.md" if lang == "zh" else "PROMPT_VARIABLES_REFERENCE.md"
            doc_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", filename)

            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return json.dumps({"doc_type": "prompt", "lang": lang, "content": content})
            except FileNotFoundError:
                return json.dumps({"error": f"Document not found: {filename}"})

        elif doc_type == "program":
            # Return MarketData/Decision API docs from ai_program_service
            from services.ai_program_service import MARKET_API_DOCS, DECISION_API_DOCS

            if api_type == "market":
                content = MARKET_API_DOCS
            elif api_type == "decision":
                content = DECISION_API_DOCS
            else:
                content = MARKET_API_DOCS + "\n\n" + DECISION_API_DOCS

            return json.dumps({"doc_type": "program", "api_type": api_type, "content": content})

        else:
            return json.dumps({"error": f"Invalid doc_type: {doc_type}"})

    except Exception as e:
        logger.error(f"[get_api_reference] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_klines(db: Session, symbol: str, period: str = "1h", limit: int = 50, exchange: str = "hyperliquid") -> str:
    """Get K-line data for a symbol."""
    from database.models import CryptoKline

    try:
        limit = min(max(limit, 1), 200)

        klines = db.query(CryptoKline).filter(
            CryptoKline.exchange == exchange,
            CryptoKline.symbol == symbol.upper(),
            CryptoKline.period == period,
            CryptoKline.environment == "mainnet"
        ).order_by(CryptoKline.timestamp.desc()).limit(limit).all()

        candles = []
        for k in reversed(klines):
            candles.append({
                "time": datetime.utcfromtimestamp(k.timestamp).strftime("%Y-%m-%d %H:%M UTC"),
                "open": float(k.open_price) if k.open_price else 0,
                "high": float(k.high_price) if k.high_price else 0,
                "low": float(k.low_price) if k.low_price else 0,
                "close": float(k.close_price) if k.close_price else 0,
                "volume": float(k.volume) if k.volume else 0
            })

        return json.dumps({
            "symbol": symbol.upper(),
            "period": period,
            "exchange": exchange,
            "candles": candles,
            "count": len(candles)
        }, indent=2)

    except Exception as e:
        logger.error(f"[get_klines] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_market_regime(db: Session, symbol: str, period: str = "1h") -> str:
    """Get market regime classification for a symbol."""
    try:
        from program_trader.data_provider import DataProvider

        data_provider = DataProvider(db=db, account_id=0, environment="mainnet", exchange="hyperliquid")
        regime = data_provider.get_regime(symbol.upper(), period)

        if regime:
            return json.dumps({
                "symbol": symbol.upper(),
                "period": period,
                "regime": regime.regime,
                "confidence": regime.conf
            }, indent=2)
        else:
            return json.dumps({
                "symbol": symbol.upper(),
                "period": period,
                "regime": "unknown",
                "confidence": 0,
                "note": "Unable to determine market regime"
            })

    except Exception as e:
        logger.error(f"[get_market_regime] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_market_flow(db: Session, symbol: str, period: str = "1h", exchange: str = "hyperliquid") -> str:
    """Get market flow data for a symbol."""
    try:
        from program_trader.data_provider import DataProvider

        data_provider = DataProvider(db=db, account_id=0, environment="mainnet", exchange=exchange)

        flow = {}
        for metric in ["CVD", "OI", "OI_DELTA", "TAKER", "FUNDING"]:
            result = data_provider.get_flow(symbol.upper(), metric, period)
            if result:
                flow[metric] = result

        return json.dumps({
            "symbol": symbol.upper(),
            "period": period,
            "exchange": exchange,
            "flow": flow
        }, indent=2)

    except Exception as e:
        logger.error(f"[get_market_flow] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_get_system_logs(db: Session, level: str = "error", limit: int = 20, trader_id: int = None) -> str:
    """Get recent system logs (same as System Logs page)."""
    from services.system_logger import system_logger

    try:
        limit = min(max(limit, 1), 50)

        # Map level to min_level for system_logger
        min_level = None
        if level == "error":
            min_level = "ERROR"
        elif level == "warning":
            min_level = "WARNING"
        # "all" means no filter

        # Get logs from system_logger (same as frontend System Logs page)
        raw_logs = system_logger.get_logs(limit=limit, min_level=min_level)

        # Format for AI consumption
        logs = []
        for log in raw_logs:
            logs.append({
                "time": log.get("timestamp", ""),
                "level": log.get("level", "INFO"),
                "category": log.get("category", ""),
                "message": log.get("message", ""),
                "details": log.get("details", {})
            })

        return json.dumps({"logs": logs, "total": len(logs)}, indent=2)

    except Exception as e:
        logger.error(f"[get_system_logs] Error: {e}")
        return json.dumps({"error": str(e)})
        return json.dumps({"error": str(e)})


def execute_get_contact_config() -> str:
    """Get support channel URLs."""
    import requests

    try:
        # Try to fetch from external API
        resp = requests.get("https://www.akooi.com/api/config/contact", timeout=5)
        if resp.status_code == 200:
            return json.dumps(resp.json(), indent=2)
    except Exception as e:
        logger.warning(f"[get_contact_config] Failed to fetch from API: {e}")

    # Fallback to defaults
    return json.dumps({
        "twitter": {"url": "https://x.com/GptHammer3309", "enabled": True},
        "telegram": {"url": "https://t.me/+RqxjT7Gttm9hOGEx", "enabled": True},
        "github": {"url": "https://github.com/HammerGPT/Hyper-Alpha-Arena", "enabled": True}
    }, indent=2)


def execute_diagnose_trader_issues(db: Session, trader_id: int) -> str:
    """Diagnose why an AI Trader is not triggering."""
    from database.models import (
        Account, HyperliquidWallet, BinanceWallet, AccountPromptBinding,
        AccountProgramBinding, AccountStrategyConfig, SignalPool,
        HyperliquidAccountSnapshot, BinanceAccountSnapshot, AIDecisionLog, ProgramExecutionLog
    )

    try:
        # Get account
        account = db.query(Account).filter(Account.id == trader_id).first()
        if not account:
            return json.dumps({"error": f"AI Trader with id {trader_id} not found"})

        checks = []
        issues = []

        # Check 1: Trader enabled
        trader_enabled = account.is_active == "true"
        checks.append({"check": "trader_enabled", "passed": trader_enabled})
        if not trader_enabled:
            issues.append("AI Trader is disabled")

        # Check 2: Auto trading enabled
        auto_enabled = account.auto_trading_enabled == "true"
        checks.append({"check": "auto_trading_enabled", "passed": auto_enabled})
        if not auto_enabled:
            issues.append("Auto trading is disabled")

        # Check 3: Strategy bound
        prompt_binding = db.query(AccountPromptBinding).filter(
            AccountPromptBinding.account_id == trader_id
        ).first()
        program_binding = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.account_id == trader_id,
            AccountProgramBinding.is_active == True
        ).first()

        strategy_bound = prompt_binding is not None or program_binding is not None
        strategy_type = "prompt" if prompt_binding else ("program" if program_binding else None)
        checks.append({"check": "strategy_bound", "passed": strategy_bound, "type": strategy_type})
        if not strategy_bound:
            issues.append("No strategy (prompt or program) bound to this trader")

        # Check 4: Wallet bound and has balance
        strategy_config = db.query(AccountStrategyConfig).filter(
            AccountStrategyConfig.account_id == trader_id
        ).first()

        exchange = strategy_config.exchange if strategy_config else "hyperliquid"
        wallet_bound = False
        wallet_balance = 0
        wallet_env = None

        if exchange == "hyperliquid":
            wallet = db.query(HyperliquidWallet).filter(
                HyperliquidWallet.account_id == trader_id,
                HyperliquidWallet.is_active == "true"
            ).first()
            if wallet:
                wallet_bound = True
                wallet_env = wallet.environment
                snapshot = db.query(HyperliquidAccountSnapshot).filter(
                    HyperliquidAccountSnapshot.account_id == trader_id,
                    HyperliquidAccountSnapshot.environment == wallet.environment
                ).order_by(HyperliquidAccountSnapshot.snapshot_time.desc()).first()
                if snapshot:
                    wallet_balance = float(snapshot.available_balance)
        else:
            wallet = db.query(BinanceWallet).filter(
                BinanceWallet.account_id == trader_id,
                BinanceWallet.is_active == "true"
            ).first()
            if wallet:
                wallet_bound = True
                wallet_env = wallet.environment
                snapshot = db.query(BinanceAccountSnapshot).filter(
                    BinanceAccountSnapshot.account_id == trader_id,
                    BinanceAccountSnapshot.environment == wallet.environment
                ).order_by(BinanceAccountSnapshot.snapshot_time.desc()).first()
                if snapshot:
                    wallet_balance = float(snapshot.available_balance)

        checks.append({
            "check": "wallet_bound",
            "passed": wallet_bound,
            "wallet": f"{exchange}/{wallet_env}" if wallet_bound else None
        })
        if not wallet_bound:
            issues.append(f"No {exchange} wallet bound. Go to Settings → Wallets to configure.")

        checks.append({
            "check": "wallet_balance",
            "passed": wallet_balance > 0,
            "balance": wallet_balance,
            "suggestion": "Deposit funds to wallet" if wallet_balance == 0 else None
        })
        if wallet_balance == 0 and wallet_bound:
            issues.append("Wallet balance is 0. Deposit funds to enable trading.")

        # Check 5: Signal pool or scheduled trigger
        if strategy_config:
            has_signal = bool(strategy_config.signal_pool_ids)
            has_scheduled = strategy_config.scheduled_trigger_enabled
            checks.append({
                "check": "trigger_configured",
                "passed": has_signal or has_scheduled,
                "signal_pools": strategy_config.signal_pool_ids,
                "scheduled_enabled": has_scheduled,
                "interval": strategy_config.trigger_interval
            })
            if not has_signal and not has_scheduled:
                issues.append("No trigger configured (neither signal pool nor scheduled)")

        # Check 6: Recent errors
        recent_errors = []
        ai_errors = db.query(AIDecisionLog).filter(
            AIDecisionLog.account_id == trader_id,
            AIDecisionLog.executed == "false"
        ).order_by(AIDecisionLog.decision_time.desc()).limit(3).all()

        for err in ai_errors:
            recent_errors.append({
                "time": err.decision_time.strftime("%Y-%m-%d %H:%M UTC") if err.decision_time else None,
                "type": "ai_decision",
                "message": err.reason[:100] if err.reason else "Unknown"
            })

        status = "healthy" if not issues else "issues_found"
        summary = issues[0] if issues else "All checks passed. Trader should be operational."

        return json.dumps({
            "trader_id": trader_id,
            "trader_name": account.name,
            "status": status,
            "checks": checks,
            "summary": summary,
            "recent_errors": recent_errors
        }, indent=2)

    except Exception as e:
        logger.error(f"[diagnose_trader_issues] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_signal_pool(
    db: Session,
    pool_name: str,
    symbols: List[str],
    signal_ids: List[int],
    pool_id: int = None,
    logic: str = "OR",
    exchange: str = "hyperliquid",
    enabled: bool = True
) -> str:
    """Create or update a signal pool."""
    from database.models import SignalPool, SignalDefinition

    try:
        # Validate signal_ids exist
        existing_signals = db.query(SignalDefinition.id).filter(
            SignalDefinition.id.in_(signal_ids)
        ).all()
        existing_ids = {s[0] for s in existing_signals}
        invalid_ids = set(signal_ids) - existing_ids
        if invalid_ids:
            return json.dumps({"error": f"Invalid signal IDs: {list(invalid_ids)}"})

        symbols_json = json.dumps([s.upper() for s in symbols])
        signal_ids_json = json.dumps(signal_ids)

        if pool_id:
            # Update existing pool
            pool = db.query(SignalPool).filter(SignalPool.id == pool_id).first()
            if not pool:
                return json.dumps({"error": f"Signal pool {pool_id} not found"})

            pool.pool_name = pool_name
            pool.symbols = symbols_json
            pool.signal_ids = signal_ids_json
            pool.logic = logic
            pool.exchange = exchange
            pool.enabled = enabled
            db.commit()
            action = "updated"
        else:
            # Create new pool
            pool = SignalPool(
                pool_name=pool_name,
                symbols=symbols_json,
                signal_ids=signal_ids_json,
                logic=logic,
                exchange=exchange,
                enabled=enabled
            )
            db.add(pool)
            db.commit()
            db.refresh(pool)
            action = "created"

        return json.dumps({
            "success": True,
            "pool_id": pool.id,
            "pool_name": pool_name,
            "action": action,
            "note": "Signal pool saved. Bind it to an AI Trader to start receiving triggers."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[save_signal_pool] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_prompt(
    db: Session,
    name: str,
    template_text: str,
    prompt_id: int = None,
    description: str = None
) -> str:
    """Create or update a trading prompt template."""
    from database.models import PromptTemplate
    import re

    try:
        # Extract variables from template
        variables = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', template_text)
        variables = list(set(variables))

        if prompt_id:
            # Update existing prompt
            prompt = db.query(PromptTemplate).filter(
                PromptTemplate.id == prompt_id,
                PromptTemplate.is_deleted == "false"
            ).first()
            if not prompt:
                return json.dumps({"error": f"Prompt {prompt_id} not found"})

            prompt.name = name
            prompt.template_text = template_text
            if description:
                prompt.description = description
            prompt.updated_by = "hyper_ai"
            db.commit()
            action = "updated"
        else:
            # Create new prompt
            # Generate unique key
            import uuid
            key = f"hyper_ai_{uuid.uuid4().hex[:8]}"

            # Get default system template
            default_system = db.query(PromptTemplate).filter(
                PromptTemplate.is_system == "true"
            ).first()
            system_text = default_system.system_template_text if default_system else ""

            prompt = PromptTemplate(
                key=key,
                name=name,
                description=description or "",
                template_text=template_text,
                system_template_text=system_text,
                is_system="false",
                is_deleted="false",
                created_by="hyper_ai"
            )
            db.add(prompt)
            db.commit()
            db.refresh(prompt)
            action = "created"

        return json.dumps({
            "success": True,
            "prompt_id": prompt.id,
            "name": name,
            "action": action,
            "variables_detected": variables[:20],
            "note": "Prompt saved. Changes apply to bound AI Traders on next trigger."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[save_prompt] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_save_program(
    db: Session,
    name: str,
    code: str,
    program_id: int = None,
    description: str = None
) -> str:
    """Create or update a trading program."""
    from database.models import TradingProgram

    try:
        # Validate code syntax
        from services.ai_program_service import _validate_python_code
        validation = _validate_python_code(code)
        if "Error" in validation or "error" in validation.lower():
            return json.dumps({
                "success": False,
                "error": "Code validation failed",
                "details": validation
            })

        if program_id:
            # Update existing program
            program = db.query(TradingProgram).filter(TradingProgram.id == program_id).first()
            if not program:
                return json.dumps({"error": f"Program {program_id} not found"})

            program.name = name
            program.code = code
            if description:
                program.description = description
            db.commit()
            action = "updated"
        else:
            # Create new program
            program = TradingProgram(
                user_id=1,  # Default user
                name=name,
                description=description or "",
                code=code
            )
            db.add(program)
            db.commit()
            db.refresh(program)
            action = "created"

        return json.dumps({
            "success": True,
            "program_id": program.id,
            "name": name,
            "action": action,
            "validation": {"syntax_valid": True, "security_check": "passed"},
            "note": "Program saved. Use test_run_code to verify logic before binding."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[save_program] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_create_ai_trader(
    db: Session,
    name: str,
    model: str,
    base_url: str,
    api_key: str
) -> str:
    """Create a new AI Trader with LLM config only. Strategy and wallet binding done separately."""
    from database.models import Account

    try:
        # Step 1: Test LLM connection first
        from api.account_routes import test_llm_connection
        import asyncio

        # Create event loop if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        test_result = loop.run_until_complete(test_llm_connection({
            "model": model,
            "base_url": base_url,
            "api_key": api_key
        }))

        if not test_result.get("success"):
            return json.dumps({
                "success": False,
                "error": "LLM connection test failed",
                "details": test_result.get("message", "Unknown error"),
                "note": "Please check your LLM credentials and try again."
            })

        # Step 2: Create Account with LLM config only
        account = Account(
            user_id=1,
            name=name,
            account_type="AI",
            is_active="true",
            auto_trading_enabled="false",  # Disabled until strategy/wallet configured
            model=model,
            base_url=base_url,
            api_key=api_key
        )
        db.add(account)
        db.commit()

        return json.dumps({
            "success": True,
            "trader_id": account.id,
            "trader_name": name,
            "llm_config": {
                "model": model,
                "base_url": base_url,
                "connection_tested": True
            },
            "next_steps": [
                "1. Go to Settings → Wallets to bind a wallet",
                "2. Go to Strategies to create/select a trading strategy",
                "3. Enable auto-trading when ready"
            ],
            "note": "AI Trader created with LLM config. Complete wallet and strategy setup to start trading."
        }, indent=2)

    except Exception as e:
        db.rollback()
        logger.error(f"[create_ai_trader] Error: {e}")
        return json.dumps({"error": str(e)})


# =============================================================================
# Tool Dispatcher
# =============================================================================

def execute_hyper_ai_tool(db: Session, tool_name: str, arguments: Dict[str, Any], user_id: int = 1) -> str:
    """Execute a Hyper AI tool by name."""
    try:
        if tool_name == "get_system_overview":
            return execute_get_system_overview(db)

        elif tool_name == "get_wallet_status":
            return execute_get_wallet_status(
                db,
                exchange=arguments.get("exchange", "all"),
                environment=arguments.get("environment", "all")
            )

        elif tool_name == "get_api_reference":
            return execute_get_api_reference(
                doc_type=arguments.get("doc_type", "prompt"),
                api_type=arguments.get("api_type", "all"),
                lang=arguments.get("lang", "en")
            )

        elif tool_name == "get_klines":
            return execute_get_klines(
                db,
                symbol=arguments.get("symbol", "BTC"),
                period=arguments.get("period", "1h"),
                limit=arguments.get("limit", 50),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "get_market_regime":
            return execute_get_market_regime(
                db,
                symbol=arguments.get("symbol", "BTC"),
                period=arguments.get("period", "1h")
            )

        elif tool_name == "get_market_flow":
            return execute_get_market_flow(
                db,
                symbol=arguments.get("symbol", "BTC"),
                period=arguments.get("period", "1h"),
                exchange=arguments.get("exchange", "hyperliquid")
            )

        elif tool_name == "get_system_logs":
            return execute_get_system_logs(
                db,
                level=arguments.get("level", "error"),
                limit=arguments.get("limit", 20),
                trader_id=arguments.get("trader_id")
            )

        elif tool_name == "get_contact_config":
            return execute_get_contact_config()

        elif tool_name == "diagnose_trader_issues":
            return execute_diagnose_trader_issues(db, trader_id=arguments.get("trader_id"))

        elif tool_name == "save_signal_pool":
            return execute_save_signal_pool(
                db,
                pool_name=arguments.get("pool_name"),
                symbols=arguments.get("symbols", []),
                signal_ids=arguments.get("signal_ids", []),
                pool_id=arguments.get("pool_id"),
                logic=arguments.get("logic", "OR"),
                exchange=arguments.get("exchange", "hyperliquid"),
                enabled=arguments.get("enabled", True)
            )

        elif tool_name == "save_prompt":
            return execute_save_prompt(
                db,
                name=arguments.get("name"),
                template_text=arguments.get("template_text"),
                prompt_id=arguments.get("prompt_id"),
                description=arguments.get("description")
            )

        elif tool_name == "save_program":
            return execute_save_program(
                db,
                name=arguments.get("name"),
                code=arguments.get("code"),
                program_id=arguments.get("program_id"),
                description=arguments.get("description")
            )

        elif tool_name == "create_ai_trader":
            return execute_create_ai_trader(
                db,
                name=arguments.get("name"),
                model=arguments.get("model"),
                base_url=arguments.get("base_url"),
                api_key=arguments.get("api_key")
            )

        # Sub-agent tools
        elif tool_name in ("call_prompt_ai", "call_program_ai", "call_signal_ai", "call_attribution_ai"):
            return execute_subagent_tool(db, tool_name, arguments, user_id=user_id)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"[execute_hyper_ai_tool] Error executing {tool_name}: {e}")
        return json.dumps({"error": str(e)})
