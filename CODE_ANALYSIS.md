# Falcon Premium Bot - Complete Code Analysis

**Date:** July 29, 2026  
**Language:** Python (discord.py)  
**File Size:** 3,151 lines  
**Purpose:** Discord bot for member tracking, moderation, giveaways, and server management

---

## 📋 Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Database Schema](#database-schema)
4. [Features & Commands](#features--commands)
5. [Event Handlers](#event-handlers)
6. [Advanced Features](#advanced-features)
7. [Security & Permissions](#security--permissions)
8. [Key Issues & Observations](#key-issues--observations)

---

## 🏗️ Architecture Overview

### Bot Framework
- **Framework:** discord.py
- **Class:** `FalconBot(commands.Bot)`
- **Intents:** 
  - `message_content` (read message content)
  - `members` (track member join/leave)
  - `invites` (track invitation codes)
  - `presences` (member status tracking)

### Initialization
```python
- Command prefix: Dynamic (!, comma, or empty if noprefix active)
- Database: SQLite (falcon_data.db)
- Owner system: Multi-owner with PRIMARY_OWNER_IDS hardcoded
- In-memory tracking: Invite cache, channel/role deletes, bans, joins
- Music queues: Per-guild music player state
```

### Key Attributes
```python
- inv_cache: Guild invite tracking (code → uses count)
- recent_joins/deletes/bans: Deques for anti-raid/nuke detection
- music_queues: Per-guild music queue list
- now_playing: Current song per guild
```

---

## 🔧 Core Components

### 1. Primary Owner System
- **Hardcoded IDs:** 3 primary owners (immutable via commands)
- **Database Owners:** Additional owners can be added via commands
- **Hierarchy:** PRIMARY_OWNER_IDS > bot_owners (DB) > bot_staff (DB)

### 2. Database Layer
**Location:** `falcon_data.db` (auto-created on startup)

**Key Tables:**
- `users` - Member stats (joins, messages, voice time, bonus)
- `guild_settings` - Server config (channels, messages, thresholds)
- `invite_roles` - Auto-roles for invite milestones
- `message_roles` - Auto-roles for message milestones
- `giveaways` - Active giveaway tracking
- `premium_users/premium_guilds` - Premium status + expiry
- `antinuke_settings/antiraid_settings` - Security configs
- `autoroles` - Auto-role assignments
- `live_leaderboards` - Live leaderboard state
- `disabled_commands/modules` - Command disabling per channel
- `blacklisted_channels/categories` - Message tracking exclusions

**Helper Functions:**
- `update_user()` - Increment user stats (joins, messages, voice)
- `get_user_data()` - Fetch user stats
- `build_lb_embed()` - Generate leaderboard embeds

### 3. Permission System
```python
is_bot_owner(uid)        # Check admin
is_bot_staff(uid)        # Check staff (includes owners)
is_bot_blacklisted(uid)  # Check user blacklist
is_user_premium(uid)     # Check premium expiry
```

### 4. Emoji Management
- **Smart Emoji Picker:** Auto-selects guild emojis based on keyword matching
- **Keywords Mapped:** 15 sections (premium, invites, messages, voice, etc.)
- **Fallback:** Uses default emojis if no custom emojis available
- **Auto-apply:** Applied on first join if owner is in guild

---

## 📊 Database Schema

### Users Table
```sql
user_id (PK)
├── joins, left, bonus, total_msgs
├── weekly_msgs, today_msgs
├── voice_alltime, voice_weekly, voice_daily
```

### Guild Settings
```sql
guild_id (PK)
├── Channels: join_channel_id, leave_channel_id
├── Messages: join_message, leave_message, vanity_message
├── Thresholds: alt_threshold
├── Resets: msg_weekly_reset, msg_daily_reset, voice_daily_reset, voice_weekly_reset
```

### Tracking Tables
```
invite_tracker (invitee_id → inviter_id, joined_at)
blacklisted_channels (guild_id, channel_id)
blacklisted_categories (guild_id, category_id)
greet_channels (guild_id, channel_id, greet_type)
```

### Configuration Tables
```
autoroles (role_type: 'all'|'bots'|'humans')
invite_roles (required_invites milestone)
message_roles (required_msgs milestone)
disabled_commands/modules (per channel)
polls, giveaways, premium_users/guilds
```

---

## 🎯 Features & Commands

### 1. **Invite Tracking** (`!invites`, `!i`)
- Tracks who invited whom (invite_tracker table)
- Shows: total invites, joins, leaves, bonus
- Auto-role assignment at milestones
- Commands:
  - `!invites [user]` - View invite stats
  - `!inviter [user]` - Who invited this member
  - `!invited [user]` - Members invited by user
  - `!inviteinfo [user]` - Detailed info
  - `!addinvites user amount` - Add bonus invites
  - `!removeinvites user amount` - Remove invites
  - `!clearinvites [user]` - Clear all invites
  - `!resetmyinvites` - Self-clear

### 2. **Message Tracking** (`!messages`, `!m`)
- Counts messages across all channels (unless blacklisted)
- Weekly/daily resets at configured times
- Auto-role assignment at milestones
- Commands:
  - `!messages [user]` - View message stats
  - `!addmessages user amount` - Add count
  - `!removemessages user amount` - Remove count
  - `!clearmsgs [user]` - Clear all messages
  - `!resetmymessages` - Self-clear
  - `!setmessagerole role count` - Set milestone role

### 3. **Voice Tracking** (`!vc`)
- Tracks voice channel time (join/leave events)
- Separate counters: alltime, weekly, daily
- Commands:
  - `!vc [user]` - View voice stats
  - `!addvctime user seconds` - Add voice time
  - `!reducevctime user seconds` - Remove voice time
  - `!clearvoice [user]` - Clear all

### 4. **Leaderboards** (`!leaderboard`, `!lb_*`)
- Seven types:
  - `!lb_invites` - Invite leaderboard
  - `!lb_messages` - Total messages
  - `!lb_weekly` - Weekly messages
  - `!lb_daily` - Daily messages
  - `!lb_voice` - Total voice time
  - `!lb_weeklyvoice` - Weekly voice
  - `!lb_dailyvoice` - Daily voice
- Live leaderboards: Auto-update every 30s (stored in DB)

### 5. **Giveaway System**
- Two types:
  - Standard giveaways: `!gcreate time winners "prize"`
  - Winner-role giveaways: `!gwstart time winners "prize"`
- Mechanics:
  - React with 🎉 to enter
  - Exclude bypass roles
  - Reroll with `!greroll`
  - Forced winner with `!setwin`
- Storage: msg_id tracked, reactions scanned for winners

### 6. **Auto-Role System**
- Types: `all`, `bots`, `humans`
- Assign on member join
- Multiple per guild
- Commands:
  - `!setautorole role [type]` - Add auto-role
  - `!unsetautorole role` - Remove
  - `!viewautoroles` - List all

### 7. **Welcome/Goodbye Messages**
- Custom join/leave messages with variables
- Alternative "vanity message" if joined via vanity URL
- Variables: `{user}`, `{username}`, `{server}`, `{membercount}`, `{inviter}`
- Greeting channels: Separate embed-based greets per channel
- Commands:
  - `!setjoinchannel [channel]` - Set welcome channel
  - `!setjoinmessage "message"` - Custom message
  - `!setleave [channel]` - Leave channel
  - `!setleavemessage "message"` - Leave message

### 8. **Moderation**
- `!kick member [reason]` - Kick
- `!ban member [reason]` - Ban
- `!unban user_id` - Unban
- `!mute member [duration] [reason]` - Mute (default 10m)
- `!unmute member` - Unmute
- `!erase [amount]` - Bulk delete (default 10 messages)

### 9. **Command Disabling**
- Disable commands/modules per channel or guild-wide
- Commands:
  - `!disable mode target` - Disable
  - `!enable mode target` - Enable
  - Modes: `command` or `module`

### 10. **Polling System**
- Parse custom poll syntax
- Commands:
  - `!createpoll` - Create poll (custom format)
  - `!epoll` - End poll (most recent)

### 11. **Timer System** (music-related?)
- `!tstart duration [label]` - Start timer
- `!tpause` - Pause
- `!tresume` - Resume
- `!tend` - End

### 12. **Music Player**
- Uses yt-dlp for extraction
- Commands:
  - `!play "query"` - Play song
  - `!skip` - Skip current
  - `!stop` - Stop and clear queue
  - `!queue` - Show queue
  - `!nowplaying` - Current song
- Per-guild queues

### 13. **Utility Commands**
- `!ping` - Bot latency
- `!serverinfo` - Guild stats
- `!userinfo [user]` - User details
- `!avatar [user]` - Avatar image
- `!crypto symbol` - Crypto price (API call)

### 14. **Premium System**
- Premium users/guilds with expiry dates
- `!premium add user days` - Add premium
- `!premium remove user` - Remove premium
- Features: Likely unlock extra commands/features

### 15. **No-Prefix Feature**
- Allows commands without prefix for premium/staff
- Duration-based (stored in DB with expiry)
- `!noprefix set user duration` - Enable
- `!noprefix remove user` - Disable

### 16. **Admin Commands** (Staff/Owner only)
- `!setowner user` - Add owner
- `!unsetowner user` - Remove owner
- `!setstaff user` - Add staff
- `!unsetstaff user` - Remove staff
- `!blacklist_user user reason` - Blacklist
- `!customize [action] [url]` - Custom branding
- `!bonus user amount` - Add invites (fast path)

### 17. **Help System**
- Interactive dropdown menu with categories
- Emojis per section (customizable)
- `!help` - Main help with navigation
- `!credits` - Bot credits
- Sections: Premium, Invites, Messages, Voice, Roles, LB, Giveaway, Timer, Greet, Mod, Manage, Poll, Utility, Contact

---

## 📡 Event Handlers

### 1. **on_ready()**
- Cache invites for all guilds
- Auto-apply dropdown emojis if not already set
- Print "Falcon™ Premium is live and tracking"
- Sync slash commands to Discord

### 2. **on_guild_join(guild)**
- Cache invites
- Identify who added bot (audit log)
- Auto-apply emojis if owner added the bot

### 3. **on_message(message)**
- Ignore bots
- Check user blacklist
- Run automod checks (anti-link/invite/spam)
- Check blacklisted channels/categories
- Update message counters (global, weekly, daily)
- Assign message-role milestones
- Process commands

### 4. **on_member_join(member)**
- **Auto-roles:** Assign roles based on config
- **Invite tracking:** Detect who invited
  - Check invite use change
  - Fallback to vanity URL check
- **Invite roles:** Assign if milestone reached
- **Join channel:** Send configurable message/embed
- **Greeting channels:** Send join greet to multiple channels

### 5. **on_member_remove(member)**
- Increment "left" counter
- Send leave message to configured channel
- Track in database

### 6. **on_voice_state_update(member, before, after)**
- Detect voice join: Store timestamp
- Detect voice leave: Calculate duration, update voice time

### 7. **Antinuke Event Handlers** (Advanced)
- `on_guild_channel_delete()` - Track channel deletes
- `on_guild_channel_create()` - Track channel creates
- `on_guild_channel_update()` - Track modifications
- `on_guild_role_delete()` - Track role deletes
- `on_guild_role_create()` - Track role creates
- `on_guild_role_update()` - Track modifications
- `on_member_ban()` - Track bans
- `on_webhooks_update()` - Track webhook changes
- `on_guild_update()` - Track guild settings changes
- `_an_bot_add()` - Detect bot additions

### 8. **Antiraid** (`on_member_join_antiraid`)
- Trigger on member joins
- Check join rate within time window
- Punish if exceeds threshold

---

## 🛡️ Advanced Features

### 1. **Antinuke System (v2)**
- **Event Tracking:** Per-event enable/disable
  - channel_delete, role_delete, channel_create, member_ban, bot_add, webhook_update
- **Whitelist:** Per-user event whitelisting (can do '*' for all)
- **Response:**
  - Fetch who performed action
  - Delete unauthorized changes
  - Punish with configurable action (ban, kick, mute)
  - Log incidents
  - Optionally recreate deleted channels

**Settings:**
```sql
antinuke_v2_settings (guild_id, recreate_channels, delete_unauthorized, punish_action)
antinuke_v2_events (guild_id, event_name, enabled)
antinuke_v2_whitelist (guild_id, user_id, events)
```

**Helper Functions:**
- `_an_can_fetch()` - Check if action fetchable from audit log
- `_an_audit()` - Fetch who did the action
- `_an_event_enabled()` - Check if event monitoring enabled
- `_an_is_immune()` - Check if user whitelisted
- `_an_punish()` - Execute punishment
- `_an_log()` - Send log message
- `_an_get_status()` - Get antinuke status

### 2. **Anti-Raid System**
- **Threshold:** Configurable joins within time window
- **Default:** 5 joins in 10 seconds
- **Response:** Ban member and punish
- **Settings:** Per-guild configuration

### 3. **Automod System**
- **Features:** Anti-invite, anti-link, anti-spam
- **Per-Guild:** Toggle each independently
- **Enforcement:** Delete messages + warn user
- **Command:** `!automod [action] [setting]`

### 4. **Premium System**
- **Types:** User premium (affects access) or Guild premium (feature unlock)
- **Expiry:** Datetime-based (ISO format in DB)
- **Primary Owners:** Always premium (hardcoded)
- **Enforcement:** Commands can check `is_user_premium()` or `is_guild_premium()`

### 5. **Crypto Price Feature**
- `!crypto [symbol]` - Fetch crypto price (API integration)
- Uses external API call (likely CoinGecko or similar)

### 6. **Music System**
- Uses `yt-dlp` library for extraction
- Per-guild queues (defaultdict)
- `_ytdl_extract()` - Extract song info from query
- `_play_next()` - Auto-play next in queue
- Queue state persisted in memory (lost on restart)

### 7. **Custom Emoji Picker**
- 15 keyword sections mapped to Discord emojis
- Priority matching by section keywords
- Fallback to leftover emojis if no match
- Auto-apply on first join if owner in guild

---

## 🔐 Security & Permissions

### Permission Hierarchy
```
PRIMARY_OWNER_IDS (hardcoded, immutable)
  ↓
bot_owners (DB, managed via commands)
  ↓
bot_staff (DB, managed via commands)
  ↓
Regular users
```

### Blacklist System
- **User Blacklist:** `!blacklist_user user reason`
- **Channel Blacklist:** Exclude from message tracking
- **Category Blacklist:** Exclude entire category
- **Enforcement:** `on_message()` checks before processing

### Access Control
- Owner-only commands check `is_bot_owner()`
- Staff-only commands check `is_bot_staff()`
- Premium checks via `is_user_premium()` with expiry
- Primary owners cannot be demoted (hardcoded check)

### Audit & Logging
- Antinuke logs incidents to guild logs
- Giveaway history in database
- User blacklist tracks reason, by_user, timestamp

---

## ⚠️ Key Issues & Observations

### 1. **Code Quality Issues**
- **Bare Except Clauses:** Extensive use of bare `except: pass` (lines throughout)
  - Silently swallows all errors
  - Makes debugging difficult
  - Should catch specific exceptions

- **Inconsistent Error Handling:** No structured error logging
  - Should use logging module
  - Should report errors to admin channel

- **Hardcoded Values:** Magic numbers, emojis
  - Should use config file or environment variables
  - Makes maintenance harder

### 2. **Database Concerns**
- **No Connection Pooling:** Uses single aiosqlite connection
  - Could bottleneck under high load
  - Should implement connection pool

- **SQL Injection Risk:** Uses f-strings for column names
  - `f"UPDATE users SET {cols}"` - not parameterized
  - Should use safer methods or validated column names

- **No Transaction Management:** Mixed commit() calls
  - Should use context managers for transactions
  - Data consistency not guaranteed in failures

- **Migration Issue:** `ALTER TABLE` in setup_hook() is not idempotent
  - Should track schema version

### 3. **Performance Issues**
- **Live Leaderboard Task:** Updates every 30 seconds
  - No throttling for busy guilds
  - Could cause lag if hundreds of guilds

- **Invite Cache:** Refreshed on every member join
  - O(n) operation per member
  - With large servers, could be slow

- **Voice Time Tracking:** Uses module-level dict
  - No persistence between restarts
  - Could lose data

### 4. **Security Concerns**
- **No Rate Limiting:** Commands can be spammed
  - Should add cooldowns
  - Could be DoS vector

- **Message Content Stored:** Some contexts stored in DB
  - GDPR implications
  - No data deletion mechanism

- **Antinuke Circumvention:** Smart actors could whitelist themselves first
  - Need pre-whitelist checks

### 5. **Missing Features**
- **No Slash Commands:** Uses text commands only
  - Slash commands provide better UX
  - Already calls `self.tree.sync()` but no commands defined

- **No Configuration UI:** All setup is CLI
  - Needs web dashboard or Discord UI

- **No Help for Premium Features:** Help text doesn't distinguish premium

### 6. **Incomplete Code**
- File ends mid-function: Line 707 `async def invited_cmd` is incomplete
- Suggests file may be corrupted or truncated

### 7. **Dependency Concerns**
- **yt-dlp:** Required for music but not listed in requirements
- **aiohttp:** Imported but usage not obvious
- **No requirements.txt:** Installation instructions unclear

---

## 📊 Statistics

| Metric | Value |
|--------|-------|
| Total Lines | 3,151 |
| Classes | 6 (FalconBot, NpDurationSelect, NpDurationView, HelpDropdown, HelpView) |
| Top-Level Functions | 90+ |
| Event Handlers | 12+ |
| Database Tables | 25+ |
| Commands | 80+ |
| Emojis Defined | 15 categories |

---

## 🚀 Deployment Considerations

1. **Environment Setup:**
   - Python 3.8+
   - discord.py[voice]
   - aiosqlite, aiohttp, yt-dlp
   - Bot token in environment

2. **Database:**
   - SQLite auto-created
   - Should back up `falcon_data.db` regularly
   - May need migration strategy for production

3. **Permissions:**
   - Bot needs: message content, manage roles, manage channels, manage messages, etc.
   - Should use OAuth2 scopes for fine-grained permissions

4. **Scaling:**
   - Single bot instance
   - Should implement clustering for large deployments
   - Invite cache could become memory bottleneck

---

## 🔍 Recommendations

1. **Immediate Fixes:**
   - Replace bare `except: pass` with specific exception handling
   - Use logging module for error tracking
   - Add rate limiting to commands

2. **Code Improvements:**
   - Extract database queries to separate module
   - Create command groups (invites, messages, voice, etc.)
   - Add configuration file (YAML/JSON)
   - Implement proper transaction management

3. **Features:**
   - Migrate to slash commands
   - Add web dashboard
   - Implement proper logging system
   - Add command cooldowns

4. **Security:**
   - Add rate limiting
   - Review whitelist logic for antinuke
   - Implement data retention policy
   - Add audit logging

---

**End of Analysis**
