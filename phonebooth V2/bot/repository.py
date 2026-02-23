from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class ServerEndpoint:
    guild_id: int
    channel_id: int
    starter_user_id: int


@dataclass(slots=True)
class ActiveCall:
    guild_a_id: int
    guild_b_id: int
    endpoint_a: ServerEndpoint
    endpoint_b: ServerEndpoint


@dataclass(slots=True)
class GuildConfig:
    allowed_channels: dict[int, None] = field(default_factory=dict)


class BotRepository:
    def __init__(self) -> None:
        self._configs: dict[int, GuildConfig] = {}
        self._queue: deque[int] = deque()
        self._queued_guilds: set[int] = set()
        self._queue_endpoint_by_guild: dict[int, ServerEndpoint] = {}
        self._active_partner_by_guild: dict[int, int] = {}
        self._active_call_by_guild: dict[int, ActiveCall] = {}

    def _config(self, guild_id: int) -> GuildConfig:
        if guild_id not in self._configs:
            self._configs[guild_id] = GuildConfig()
        return self._configs[guild_id]

    async def set_quick_config(self, guild_id: int, channel_id: int) -> None:
        self._config(guild_id).allowed_channels = {channel_id: None}

    async def set_mode_more(self, guild_id: int) -> None:
        self._config(guild_id)

    async def add_allowed_channel(self, guild_id: int, channel_id: int) -> None:
        self._config(guild_id).allowed_channels[channel_id] = None

    async def remove_allowed_channel(self, guild_id: int, channel_id: int) -> str:
        config = self._config(guild_id)
        existed = channel_id in config.allowed_channels
        config.allowed_channels.pop(channel_id, None)
        return "DELETE 1" if existed else "DELETE 0"

    async def clear_allowed_channels(self, guild_id: int) -> None:
        self._config(guild_id).allowed_channels.clear()

    async def list_allowed_channels(self, guild_id: int) -> list[int]:
        return list(self._config(guild_id).allowed_channels.keys())

    async def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        return channel_id in self._config(guild_id).allowed_channels

    async def get_active_call_for_guild(self, guild_id: int) -> ActiveCall | None:
        return self._active_call_by_guild.get(guild_id)

    async def get_queue_partner_guild(self, guild_id: int) -> int | None:
        scanned = 0
        total = len(self._queue)
        while scanned < total and self._queue:
            candidate_guild = self._queue.popleft()
            scanned += 1

            invalid = (
                candidate_guild == guild_id
                or candidate_guild not in self._queued_guilds
                or candidate_guild in self._active_partner_by_guild
            )
            if invalid:
                self._queued_guilds.discard(candidate_guild)
                self._queue_endpoint_by_guild.pop(candidate_guild, None)
                continue

            # Keep it available for create_call_from_queue, but allow scanning beyond front.
            self._queue.appendleft(candidate_guild)
            return candidate_guild
        return None

    async def put_guild_in_queue(self, guild_id: int, channel_id: int, starter_user_id: int) -> None:
        if guild_id in self._active_partner_by_guild:
            return

        endpoint = ServerEndpoint(guild_id=guild_id, channel_id=channel_id, starter_user_id=starter_user_id)
        if guild_id in self._queued_guilds:
            self._queue_endpoint_by_guild[guild_id] = endpoint
            return

        self._queue.append(guild_id)
        self._queued_guilds.add(guild_id)
        self._queue_endpoint_by_guild[guild_id] = endpoint

    async def is_guild_in_queue(self, guild_id: int) -> bool:
        return guild_id in self._queued_guilds

    async def queue_size(self) -> int:
        return len(self._queued_guilds)

    async def remove_guild_from_queue(self, guild_id: int) -> None:
        self._queued_guilds.discard(guild_id)
        self._queue_endpoint_by_guild.pop(guild_id, None)

    async def create_call_from_queue(self, guild_id: int, partner_guild_id: int, endpoint: ServerEndpoint) -> ActiveCall:
        partner_endpoint = self._queue_endpoint_by_guild.get(partner_guild_id)
        if partner_endpoint is None:
            raise RuntimeError("Partner queue endpoint missing")

        self._queued_guilds.discard(guild_id)
        self._queued_guilds.discard(partner_guild_id)
        self._queue_endpoint_by_guild.pop(guild_id, None)
        self._queue_endpoint_by_guild.pop(partner_guild_id, None)

        call = ActiveCall(
            guild_a_id=guild_id,
            guild_b_id=partner_guild_id,
            endpoint_a=endpoint,
            endpoint_b=partner_endpoint,
        )
        self._active_partner_by_guild[guild_id] = partner_guild_id
        self._active_partner_by_guild[partner_guild_id] = guild_id
        self._active_call_by_guild[guild_id] = call
        self._active_call_by_guild[partner_guild_id] = call
        return call

    async def end_active_call_for_guild(self, guild_id: int) -> ActiveCall | None:
        call = self._active_call_by_guild.get(guild_id)
        if call is None:
            return None

        self._active_partner_by_guild.pop(call.guild_a_id, None)
        self._active_partner_by_guild.pop(call.guild_b_id, None)
        self._active_call_by_guild.pop(call.guild_a_id, None)
        self._active_call_by_guild.pop(call.guild_b_id, None)
        return call

    @staticmethod
    def get_partner_guild_id(call: ActiveCall, guild_id: int) -> int:
        return call.guild_b_id if call.guild_a_id == guild_id else call.guild_a_id

    @staticmethod
    def get_partner_endpoint(call: ActiveCall, guild_id: int) -> ServerEndpoint:
        return call.endpoint_b if call.guild_a_id == guild_id else call.endpoint_a

    @staticmethod
    def get_guild_endpoint(call: ActiveCall, guild_id: int) -> ServerEndpoint:
        return call.endpoint_a if call.guild_a_id == guild_id else call.endpoint_b
