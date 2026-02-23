from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

try:
    from bot.config import get_settings
    from bot.repository import ActiveCall, BotRepository, ServerEndpoint
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from bot.config import get_settings
    from bot.repository import ActiveCall, BotRepository, ServerEndpoint


class PhoneboothCog(commands.Cog):
    def __init__(self, bot: commands.Bot, repo: BotRepository) -> None:
        self.bot = bot
        self.repo = repo
        self._match_lock = asyncio.Lock()
        self._webhook_cache: dict[int, discord.Webhook] = {}

    async def _get_text_channel(self, channel_id: int) -> discord.TextChannel | None:
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        try:
            fetched = await self.bot.fetch_channel(channel_id)
        except discord.DiscordException:
            return None
        return fetched if isinstance(fetched, discord.TextChannel) else None

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        cached = self._webhook_cache.get(channel.id)
        if cached is not None:
            return cached

        permissions = channel.permissions_for(channel.guild.me) if channel.guild.me else None
        if permissions is None or not permissions.manage_webhooks:
            return None

        try:
            hooks = await channel.webhooks()
            existing = next((hook for hook in hooks if hook.name == "Phonebooth Relay" and hook.token), None)
            webhook = existing or await channel.create_webhook(name="Phonebooth Relay")
        except discord.DiscordException:
            return None

        self._webhook_cache[channel.id] = webhook
        return webhook

    async def _notify_call_connected(self, call: ActiveCall) -> None:
        channel_a = await self._get_text_channel(call.endpoint_a.channel_id)
        channel_b = await self._get_text_channel(call.endpoint_b.channel_id)

        guild_a = self.bot.get_guild(call.endpoint_a.guild_id)
        guild_b = self.bot.get_guild(call.endpoint_b.guild_id)
        name_a = guild_a.name if guild_a else f"server-{call.endpoint_a.guild_id}"
        name_b = guild_b.name if guild_b else f"server-{call.endpoint_b.guild_id}"

        if channel_a is not None:
            await channel_a.send(f"Connected. You are now paired with **{name_b}**.")
        if channel_b is not None:
            await channel_b.send(f"Connected. You are now paired with **{name_a}**.")

    async def _notify_call_ended_for_partner(self, call: ActiveCall, ended_by_guild_id: int, reason: str) -> None:
        partner_endpoint = self.repo.get_partner_endpoint(call, ended_by_guild_id)
        partner_channel = await self._get_text_channel(partner_endpoint.channel_id)
        if partner_channel is None:
            return

        ended_by_guild = self.bot.get_guild(ended_by_guild_id)
        ended_name = ended_by_guild.name if ended_by_guild else "The other server"
        await partner_channel.send(f"{ended_name} {reason}.")

    async def _ensure_allowed_channel(self, ctx: commands.Context) -> bool:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return False

        allowed = await self.repo.is_channel_allowed(guild.id, ctx.channel.id)
        if not allowed:
            await ctx.send("This channel is not configured. Run `c.config` here first.")
            return False
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return
        if message.guild is None or not isinstance(message.channel, discord.TextChannel):
            return

        content = (message.content or "").strip()
        prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else "c."
        if content.startswith(prefix):
            return

        call = await self.repo.get_active_call_for_guild(message.guild.id)
        if call is None:
            return

        source = self.repo.get_guild_endpoint(call, message.guild.id)
        if source.channel_id != message.channel.id:
            return

        partner_endpoint = self.repo.get_partner_endpoint(call, message.guild.id)
        destination_channel = await self._get_text_channel(partner_endpoint.channel_id)
        if destination_channel is None:
            return

        attachment_urls = [attachment.url for attachment in message.attachments]
        sticker_names = [sticker.name for sticker in message.stickers]

        parts: list[str] = []
        if content:
            parts.append(content)
        if attachment_urls:
            parts.append("\n".join(attachment_urls))
        if sticker_names:
            parts.append("Stickers: " + ", ".join(sticker_names))

        relay_text = "\n".join(parts).strip()
        if not relay_text:
            return

        webhook = await self._get_or_create_webhook(destination_channel)
        if webhook is not None:
            try:
                await webhook.send(
                    relay_text,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            except discord.DiscordException:
                pass

        await destination_channel.send(
            f"**{message.author.display_name}**: {relay_text}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="c")
    async def start_call(self, ctx: commands.Context) -> None:
        if not await self._ensure_allowed_channel(ctx):
            return

        guild = ctx.guild
        if guild is None:
            return

        async with self._match_lock:
            active_call = await self.repo.get_active_call_for_guild(guild.id)
            if active_call is not None:
                partner_id = self.repo.get_partner_guild_id(active_call, guild.id)
                partner_guild = self.bot.get_guild(partner_id)
                partner_name = partner_guild.name if partner_guild else f"server-{partner_id}"
                await ctx.send(f"Call already connected with **{partner_name}**. Use `c.h` to hang up.")
                return

            if await self.repo.is_guild_in_queue(guild.id):
                await ctx.send("Already searching for a server. Please wait for a connection.")
                return

            partner_guild_id = await self.repo.get_queue_partner_guild(guild.id)
            if partner_guild_id is None:
                await self.repo.put_guild_in_queue(guild.id, ctx.channel.id, ctx.author.id)
                await ctx.send("Searching globally for another server.")
                return

            endpoint = ServerEndpoint(guild_id=guild.id, channel_id=ctx.channel.id, starter_user_id=ctx.author.id)
            try:
                created = await self.repo.create_call_from_queue(guild.id, partner_guild_id, endpoint)
            except RuntimeError:
                await self.repo.put_guild_in_queue(guild.id, ctx.channel.id, ctx.author.id)
                await ctx.send("Partner disappeared during match. Searching again.")
                return

        await self._notify_call_connected(created)

    @commands.command(name="s")
    async def skip_call(self, ctx: commands.Context) -> None:
        if not await self._ensure_allowed_channel(ctx):
            return

        guild = ctx.guild
        if guild is None:
            return

        async with self._match_lock:
            ended = await self.repo.end_active_call_for_guild(guild.id)
            if ended is None:
                if await self.repo.is_guild_in_queue(guild.id):
                    await ctx.send("Already searching. There is no active call to skip yet.")
                else:
                    await ctx.send("No active call to skip. Use `c.c` to start searching.")
                return

            await self.repo.put_guild_in_queue(guild.id, ctx.channel.id, ctx.author.id)
            partner_guild_id = await self.repo.get_queue_partner_guild(guild.id)
            if partner_guild_id is None:
                await ctx.send("Skipped. Searching globally for a new server now.")
                pending_call = None
            else:
                endpoint = ServerEndpoint(guild_id=guild.id, channel_id=ctx.channel.id, starter_user_id=ctx.author.id)
                try:
                    pending_call = await self.repo.create_call_from_queue(guild.id, partner_guild_id, endpoint)
                except RuntimeError:
                    await self.repo.put_guild_in_queue(guild.id, ctx.channel.id, ctx.author.id)
                    await ctx.send("Skipped, but next partner disappeared. Searching again.")
                    pending_call = None

        await self._notify_call_ended_for_partner(ended, guild.id, "skipped")
        if pending_call is not None:
            await self._notify_call_connected(pending_call)

    @commands.command(name="h")
    async def hangup_call(self, ctx: commands.Context) -> None:
        if not await self._ensure_allowed_channel(ctx):
            return

        guild = ctx.guild
        if guild is None:
            return

        async with self._match_lock:
            ended = await self.repo.end_active_call_for_guild(guild.id)
            if ended is not None:
                await ctx.send("Call ended.")
            else:
                in_queue = await self.repo.is_guild_in_queue(guild.id)
                if in_queue:
                    await self.repo.remove_guild_from_queue(guild.id)
                    await ctx.send("Search canceled. Your server was removed from queue.")
                else:
                    await ctx.send("Nothing to stop. This server is not in a call or queue.")

        if ended is not None:
            await self._notify_call_ended_for_partner(ended, guild.id, "hung up")

    @commands.command(name="friendme")
    async def friend_me(self, ctx: commands.Context) -> None:
        if not await self._ensure_allowed_channel(ctx):
            return

        guild = ctx.guild
        if guild is None:
            return

        call = await self.repo.get_active_call_for_guild(guild.id)
        if call is None:
            await ctx.send("You need an active call first. Start one with `c.c`.")
            return

        partner_endpoint = self.repo.get_partner_endpoint(call, guild.id)
        partner_channel = await self._get_text_channel(partner_endpoint.channel_id)
        if partner_channel is None:
            await ctx.send("Couldn't find the connected server channel.")
            return

        await partner_channel.send(
            f"{ctx.author.display_name} wants to connect. Username: `{ctx.author.name}`",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await ctx.send("Sent your username to the other server.")

    @commands.command(name="status")
    async def status(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        channels = await self.repo.list_allowed_channels(guild.id)
        in_queue = await self.repo.is_guild_in_queue(guild.id)
        queue_size = await self.repo.queue_size()
        call = await self.repo.get_active_call_for_guild(guild.id)

        if call is not None:
            partner_id = self.repo.get_partner_guild_id(call, guild.id)
            partner_guild = self.bot.get_guild(partner_id)
            partner_name = partner_guild.name if partner_guild else f"server-{partner_id}"
            local_endpoint = self.repo.get_guild_endpoint(call, guild.id)
            partner_endpoint = self.repo.get_partner_endpoint(call, guild.id)
            await ctx.send(
                "Status:\n"
                f"- Active call: yes\n"
                f"- Partner server: {partner_name} ({partner_id})\n"
                f"- Local call channel: <#{local_endpoint.channel_id}>\n"
                f"- Partner call channel: <#{partner_endpoint.channel_id}>\n"
                f"- Configured channels: {', '.join(f'<#{ch}>' for ch in channels) if channels else 'none'}\n"
                f"- Queue size: {queue_size}"
            )
            return

        await ctx.send(
            "Status:\n"
            f"- Active call: no\n"
            f"- In queue: {'yes' if in_queue else 'no'}\n"
            f"- Configured channels: {', '.join(f'<#{ch}>' for ch in channels) if channels else 'none'}\n"
            f"- Queue size: {queue_size}"
        )

    @commands.command(name="config")
    @commands.has_guild_permissions(manage_guild=True)
    async def config(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        allowed_channels = await self.repo.list_allowed_channels(guild.id)
        if len(allowed_channels) == 1 and allowed_channels[0] == ctx.channel.id:
            await ctx.send(f"Already configured for {ctx.channel.mention}.")
            return

        await self.repo.set_quick_config(guild.id, ctx.channel.id)
        await ctx.send(f"Configured. Bot is now active only in {ctx.channel.mention}.")

    @config.error
    async def config_permission_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need `Manage Server` permission to use config commands.")
            return
        raise error


async def main() -> None:
    settings = get_settings()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True

    bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents, help_command=None, case_insensitive=True)

    @bot.event
    async def on_ready() -> None:
        print(f"Logged in as {bot.user} ({bot.user.id})")

    @bot.event
    async def setup_hook() -> None:
        repo = BotRepository()
        await bot.add_cog(PhoneboothCog(bot, repo))

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        raise error

    await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
