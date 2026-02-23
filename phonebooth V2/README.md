# Phonebooth Discord Bot (Calls Only)

This bot runs global cross-server call matchmaking in-memory with prefix `c.`.

No Supabase, no logs, no event persistence.

## Setup
1. Copy env file:
```bash
cp .env.example .env
```

2. Fill `.env`:
- `DISCORD_BOT_TOKEN`
- `COMMAND_PREFIX` (default `c.`)
- `DISCORD_APPLICATION_ID` (optional metadata)
- `DISCORD_GUILD_ID` (optional metadata)

3. Install dependencies:
```bash
pip install -e .
```

4. Run bot:
```bash
python -m bot.main
```

## Commands
- `c.c` start/find call
- `c.s` skip current caller and search next
- `c.h` hang up active call or leave queue
- `c.friendme` share your username with current caller

## Config Command (Manage Server required)
- `c.config` set bot active channel to the current channel

Call commands only work in configured channels. If used elsewhere:
`This channel is not configured. Run c.config here first.`

## Cross-Server Behavior
- Matchmaking is global across all servers where the bot is present.
- If server A has a waiting user and server B starts `c.c`, they can be paired.
- During an active call, normal messages in the configured call channels are relayed to the partner channel.
- Relay includes sender name and avatar (via webhook when `Manage Webhooks` permission exists; fallback is bot-formatted text).

## Important Behavior
- State is in-memory only.
- Restarting the bot clears:
  - configured channel allow-lists
  - queue
  - active calls
