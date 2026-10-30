import asyncio
from pathlib import Path
from typing import List, Callable, Optional, Dict, Any, Union
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat

from src.models import Signal
from src.parser import SignalParser
from src.duplicate_filter import DuplicateFilter
from src.config import config_mgr, BASE_DIR

SESSION_FILE = str(BASE_DIR / "tg_session")


class TelegramListener:
    def __init__(
        self,
        channels: List[Union[str, int]],
        on_signal: Callable[[Signal], None],
        on_filtered: Optional[Callable[[str, str, str], None]] = None,
        require_sl: bool = True,
        duplicate_window: int = 300,
    ):
        self.channel_targets = channels
        self.on_signal = on_signal
        self.on_filtered = on_filtered
        self.parser = SignalParser(require_sl=require_sl)
        self.duplicate_filter = DuplicateFilter(window_seconds=duplicate_window)

        self.api_id = config_mgr.tg_api_id
        self.api_hash = config_mgr.tg_api_hash
        self.phone = config_mgr.tg_phone

        self.client: Optional[TelegramClient] = None
        self.monitored_entities: List[Any] = []
        self.monitored_names: Dict[int, str] = {}

    def is_configured(self) -> bool:
        return bool(self.api_id and self.api_hash)

    async def init_client(self) -> TelegramClient:
        """Initialize and authenticate Telethon client."""
        if not self.is_configured():
            raise ValueError(
                "Telegram API_ID and API_HASH are missing. "
                "Please configure them in your .env file."
            )

        self.client = TelegramClient(SESSION_FILE, self.api_id, self.api_hash)
        await self.client.start(phone=lambda: self.phone or input("Enter Telegram phone number: "))
        return self.client

    async def resolve_channels(self) -> List[Any]:
        """Resolve channel targets (usernames or IDs) to Telegram entities."""
        if not self.client:
            await self.init_client()

        resolved = []
        self.monitored_names.clear()

        for target in self.channel_targets:
            try:
                # Handle numeric ID vs username
                entity_target = int(target) if isinstance(target, int) or (isinstance(target, str) and (target.lstrip("-").isdigit())) else target
                entity = await self.client.get_entity(entity_target)
                resolved.append(entity)
                name = getattr(entity, "title", None) or getattr(entity, "username", None) or str(target)
                entity_id = getattr(entity, "id", None)
                if entity_id:
                    self.monitored_names[entity_id] = name
            except Exception as e:
                print(f"[!] Warning: Could not resolve channel '{target}': {e}")

        self.monitored_entities = resolved
        return resolved

    async def list_available_channels(self) -> List[Dict[str, Any]]:
        """List all channels and supergroups the logged-in user is member of."""
        if not self.client:
            await self.init_client()

        dialogs = await self.client.get_dialogs()
        results = []
        for d in dialogs:
            if d.is_channel or d.is_group:
                results.append({
                    "id": d.id,
                    "title": d.title,
                    "username": getattr(d.entity, "username", None),
                    "is_broadcast": getattr(d.entity, "broadcast", False),
                })
        return results

    async def start_listening(self) -> None:
        """Register message event handlers and begin listening."""
        if not self.client:
            await self.init_client()

        await self.resolve_channels()

        if not self.monitored_entities:
            print("[!] Warning: No channels were successfully resolved to listen to.")
        else:
            names = ", ".join(self.monitored_names.values())
            print(f"[*] Actively monitoring {len(self.monitored_entities)} channel(s): {names}")

        @self.client.on(events.NewMessage(chats=self.monitored_entities if self.monitored_entities else None))
        async def handler(event: events.NewMessage.Event):
            # If no entities were specified or broad listening, filter by chat
            chat_id = event.chat_id
            channel_name = self.monitored_names.get(chat_id, f"Channel_{chat_id}")
            text = event.raw_text

            if not text:
                return

            signal, reason = self.parser.parse(text, channel=channel_name)
            if signal:
                # Check duplicate filter
                if self.duplicate_filter.is_duplicate(signal.symbol, signal.action.value):
                    if self.on_filtered:
                        self.on_filtered(channel_name, text, "Filtered: Duplicate signal within time window")
                    return

                # Valid, actionable signal!
                self.on_signal(signal)
            else:
                if self.on_filtered:
                    self.on_filtered(channel_name, text, reason)

        await self.client.run_until_disconnected()
