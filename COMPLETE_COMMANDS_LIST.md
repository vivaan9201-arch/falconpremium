# Falcon Premium Bot - Complete Commands List

**Total Commands:** 600+ registered prefix commands (core commands + Power Command shortcuts)  
**Last Updated:** July 29, 2026

---

## 📑 Quick Navigation

- [Invite Commands](#invite-commands) (8)
- [Message Commands](#message-commands) (13)
- [Voice Commands](#voice-commands) (5)
- [Leaderboard Commands](#leaderboard-commands) (8)
- [Auto-Role Commands](#auto-role-commands) (4)
- [Giveaway Commands](#giveaway-commands) (8)
- [Timer Commands](#timer-commands) (4)
- [Greeting Commands](#greeting-commands) (4)
- [Moderation Commands](#moderation-commands) (6)
- [Poll Commands](#poll-commands) (2)
- [Music Commands](#music-commands) (5)
- [Utility Commands](#utility-commands) (5)
- [Premium Commands](#premium-commands) (3)
- [Admin Commands](#admin-commands) (12)
- [Help & Info Commands](#help--info-commands) (4)

---

## 👥 Invite Commands

Track invitations and who invited members.

| Command | Alias | Parameters | Permission | Description |
|---------|-------|-----------|-----------|-------------|
| `!invites` | `!i` | `[user]` | Anyone | View invite stats for a user (self if not specified) |
| `!inviter` | - | `[user]` | Anyone | See who invited a user |
| `!invited` | - | `[user]` | Anyone | View members invited by a user |
| `!inviteinfo` | - | `[user]` | Anyone | Detailed invite information for a user |
| `!addinvites` | - | `<user> <amount>` | Administrator | Add bonus invites to a user |
| `!removeinvites` | - | `<user> <amount>` | Administrator | Remove invites from a user |
| `!clearinvites` | - | `[user]` | Administrator | Clear all invites (for all users if not specified) |
| `!resetmyinvites` | - | None | Anyone | Reset your own invite stats |

### Invite Configuration Commands

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!setinviterole` | `<role> <invites>` | Manage Guild | Set auto-role at invite milestone |
| `!unsetinviterole` | `<role>` | Manage Guild | Remove invite role requirement |
| `!viewinviteroles` | None | Anyone | List all invite role requirements |
| `!setaltthreshold` | `<days>` | Manage Guild | Set account age threshold |
| `!unsetaltthreshold` | None | Manage Guild | Remove account age threshold |

---

## 💬 Message Commands

Track message counts across the guild.

| Command | Alias | Parameters | Permission | Description |
|---------|-------|-----------|-----------|-------------|
| `!messages` | `!m` | `[user]` | Anyone | View message stats for a user (self if not specified) |
| `!addmessages` | - | `<user> <amount>` | Administrator | Add messages to a user |
| `!removemessages` | - | `<user> <amount>` | Administrator | Remove messages from a user |
| `!clearmsgs` | - | `[user]` | Administrator | Clear all messages (for all users if not specified) |
| `!resetmymessages` | - | None | Anyone | Reset your own message stats |
| `!setmessagerole` | - | `<role> <count>` | Manage Guild | Set auto-role at message milestone |
| `!unsetmessagerole` | - | `<role>` | Manage Guild | Remove message role requirement |
| `!viewmessageroles` | - | None | Anyone | List all message role requirements |

### Blacklist Commands (exclude channels from tracking)

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!blacklistchannel` | `[channel]` | Manage Guild | Exclude channel from message tracking |
| `!unblacklistchannel` | `[channel]` | Manage Guild | Include channel in message tracking |
| `!blacklistedchannels` | None | Anyone | View all blacklisted channels |
| `!blacklistcategory` | `<category_name>` | Manage Guild | Exclude entire category from tracking |
| `!unblacklistcategory` | `<category_name>` | Manage Guild | Include category in tracking |
| `!blacklistedcategories` | None | Anyone | View all blacklisted categories |

### Message Configuration

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!setresettime` | `<mode> <time>` | Manage Guild | Set weekly/daily message reset time |
| `!variables` | None | Anyone | Show message variable placeholders |
| `!testmsg` | `<message>` | Manage Guild | Test join/leave message variables |

---

## 🎙️ Voice Commands

Track voice channel time.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!vc` | - | `[user]` | Anyone | View voice time stats for a user (self if not specified) |
| `!addvctime` | - | `<user> <seconds>` | Administrator | Add voice time to a user |
| `!reducevctime` | - | `<user> <seconds>` | Administrator | Remove voice time from a user |
| `!clearvoice` | - | `[user]` | Administrator | Clear all voice time (for all users if not specified) |
| `!resetmyvoice` | - | None | Anyone | Reset your own voice stats |

---

## 🏆 Leaderboard Commands

View and manage leaderboards.

| Command | Subcommand | Parameters | Description |
|---------|-----------|-----------|-------------|
| `!leaderboard` / `!lb` | (main) | None | Main leaderboard view (invites) |
| `!lb` | `invites` / `!lb_invites` | None | View invite leaderboard |
| `!lb` | `messages` / `!lb_messages` | None | View total message leaderboard |
| `!lb` | `weekly` / `!lb_weekly` | None | View weekly message leaderboard |
| `!lb` | `daily` / `!lb_daily` | None | View daily message leaderboard |
| `!lb` | `voice` / `!lb_voice` | None | View total voice leaderboard |
| `!lb` | `weeklyvoice` / `!lb_weeklyvoice` | None | View weekly voice leaderboard |
| `!lb` | `dailyvoice` / `!lb_dailyvoice` | None | View daily voice leaderboard |

### Live Leaderboard Commands

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!createlivelb` | `[lb_type]` | Manage Guild | Create auto-updating leaderboard |
| `!deletelivelb` | `[lb_type]` | Manage Guild | Delete live leaderboard |
| `!showlivelbs` | None | Anyone | View all active live leaderboards |

---

## 🎭 Auto-Role Commands

Automatically assign roles on events.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!autorole` | None | Manage Guild | Show auto-role configuration menu |
| `!setautorole` | `<role> [type]` | Manage Guild | Add auto-role (type: all/bots/humans) |
| `!unsetautorole` | `<role>` | Manage Guild | Remove auto-role |
| `!viewautoroles` | None | Anyone | List all auto-roles |

---

## 🎉 Giveaway Commands

Create and manage giveaways.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!gcreate` | `<time> <winners> <prize>` | Manager+ | Create giveaway (react with 🎉 to enter) |
| `!gstart` | `<time> <winners> <prize>` | Manager+ | Start giveaway (alias for gcreate) |
| `!gwstart` | `<time> <winners> <prize>` | Manager+ | Start winner-role giveaway |
| `!greroll` | None | Manager+ | Reroll most recent giveaway |
| `!gend` | None | Manager+ | End active giveaway |
| `!setwin` | `<user>` | Manager+ | Force-set giveaway winner |
| `!finish` | None | Manager+ | Finish and announce giveaway winner |
| `!reroll` | None | Manager+ | Reroll last giveaway |

### Giveaway Configuration

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!setgiveaway` | None | Manager+ | Set giveaway winner role |
| `!unsetgiveaway` | None | Manager+ | Unset giveaway winner role |
| `!viewwinnerrole` | None | Anyone | View giveaway winner role |
| `!viewbypassrole` | None | Anyone | View bypass role (exclude from giveaway) |

---

## ⏱️ Timer Commands

Create countdowns and timers.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!tstart` | `<duration> [label]` | Anyone | Start a timer (e.g., "5m", "2h") |
| `!tpause` | None | Anyone | Pause active timer |
| `!tresume` | None | Anyone | Resume paused timer |
| `!tend` | None | Anyone | End active timer |

**Duration Format:** `10s`, `5m`, `1h`, `2d`

---

## 👋 Greeting Commands

Configure join/leave messages.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!setjoinchannel` | `[channel]` | Manage Guild | Set join message channel |
| `!unsetwelcomechannel` | None | Manage Guild | Remove join channel |
| `!setleave` | `[channel]` | Manage Guild | Set leave message channel |
| `!unsetleavechannel` | None | Manage Guild | Remove leave channel |
| `!setjoinmessage` | `<message>` | Manage Guild | Set custom join message |
| `!unsetjoinmessage` | None | Manage Guild | Remove custom join message |
| `!setleavemessage` | `<message>` | Manage Guild | Set custom leave message |
| `!unsetleavemessage` | None | Manage Guild | Remove custom leave message |
| `!setvanitymessage` | `<message>` | Manage Guild | Alternative message for vanity invites |
| `!unsetvanitymessage` | None | Manage Guild | Remove vanity message |

### Greeting Channel Commands

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!setgreet` | `[mode] [channel]` | Manage Guild | Add greeting channel (mode: embed/text) |
| `!disablegreet` | `[channel]` | Manage Guild | Remove greeting channel |
| `!greetchannels` | None | Anyone | List all greeting channels |
| `!greetvariables` | None | Anyone | Show greeting message variables |

**Message Variables:** `{user}`, `{username}`, `{server}`, `{membercount}`, `{inviter}`

---

## 🛡️ Moderation Commands

Manage members and messages.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!kick` | `<member> [reason]` | Kick Members | Kick member from guild |
| `!ban` | `<member> [reason]` | Ban Members | Ban member from guild |
| `!unban` | `<user_id>` | Ban Members | Unban user |
| `!mute` | `<member> [duration] [reason]` | Moderate Members | Mute member (default 10m) |
| `!unmute` | `<member>` | Moderate Members | Unmute member |
| `!erase` | `[amount]` | Manage Messages | Delete messages (default 10) |

### Command/Module Disabling

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!disable` | `<mode> <target>` | Administrator | Disable command/module in channel |
| `!enable` | `<mode> <target>` | Administrator | Enable command/module in channel |

**Modes:** `command` or `module`

### Automod Commands

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!automod` | `[action] [setting]` | Manage Guild | Configure automod (anti-link, anti-invite, anti-spam) |

---

## 📊 Poll Commands

Create and manage polls.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!createpoll` | `<args>` | Anyone | Create poll (custom format) |
| `!epoll` | None | Anyone | End most recent poll |

---

## 🎵 Music Commands

Queue and play music.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!play` | `<query>` | Anyone | Play song (search or YouTube URL) |
| `!skip` | None | Anyone | Skip current song |
| `!stop` | None | Anyone | Stop playback and clear queue |
| `!queue` | None | Anyone | View music queue |
| `!nowplaying` | None | Anyone | Show currently playing song |

---

## 🔧 Utility Commands

General bot utilities.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!ping` | None | Anyone | Check bot latency |
| `!serverinfo` | None | Anyone | View guild information |
| `!userinfo` | `[user]` | Anyone | View user details (self if not specified) |
| `!avatar` | `[user]` | Anyone | View user avatar (self if not specified) |
| `!crypto` | `[symbol]` | Anyone | Get crypto price (e.g., BTC, ETH) |

---

## ⭐ Premium Commands

Manage premium status.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!premium` | `<action> [target]` | Owner | Manage premium (add, remove, check) |
| `!premium_add` | `[user] [days]` | Owner | Add premium to user (default 30 days) |
| `!premium_remove` | `[user]` | Owner | Remove premium from user |

### No-Prefix Feature

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!noprefix` | `<action> <user> [duration]` | Owner | Allow commands without prefix for user |

---

## 👨‍💼 Admin Commands

Bot owner and staff management.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!setowner` | `<user>` | Primary Owner | Add bot owner |
| `!unsetowner` | `<user>` | Primary Owner | Remove bot owner |
| `!owners` | None | Anyone | List all bot owners |
| `!setstaff` | `<user>` | Bot Owner | Add bot staff member |
| `!unsetstaff` | `<user>` | Bot Owner | Remove bot staff member |
| `!staff` | None | Anyone | List all bot staff |
| `!blacklist_user` | `<user> [reason]` | Bot Owner | Blacklist user from bot |
| `!customize` | `[action] [url]` | Bot Owner | Customize bot appearance |
| `!emoji` | `[arg]` | Bot Owner | Manage custom emojis |
| `!refresh_emojis` | None | Bot Owner | Refresh emoji cache |
| `!reset_emojis` | None | Bot Owner | Reset to default emojis |
| `!bonus` | `<user> <amount>` | Bot Owner | Quick add invites to user |

---

## ℹ️ Help & Info Commands

Get help and information about the bot.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!help` | None | Anyone | Open interactive help menu |
| `!credits` | None | Anyone | View bot credits and developers |
| `!about` | None | Anyone | About Falcon Premium Bot |

---

## 🛡️ Security & Anti-Raid Commands

Protect guild from raids and nukes.

| Command | Parameters | Permission | Description |
|---------|-----------|-----------|-------------|
| `!antinuke` | `[subcommand]` | Manage Guild | Configure antinuke protection |
| `!antiraid` | `[action] [limit] [window]` | Manage Guild | Configure anti-raid protection |

### Antinuke Subcommands

- `enable` - Enable antinuke
- `disable` - Disable antinuke
- `status` - Show antinuke status
- `whitelist add <user>` - Whitelist user
- `whitelist remove <user>` - Remove whitelist
- `whitelist list` - View whitelist
- `settings` - Show settings

### Anti-Raid Subcommands

- `enable` - Enable anti-raid
- `disable` - Disable anti-raid
- `set <limit> <window>` - Set join threshold
- `status` - Show status

---

## 📋 Command Groups Summary

| Category | Commands | Total |
|----------|----------|-------|
| Invites | invites, i, inviter, invited, inviteinfo, addinvites, removeinvites, clearinvites, resetmyinvites | 9 |
| Messages | messages, m, addmessages, removemessages, clearmsgs, resetmymessages, blacklistchannel, unblacklistchannel, blacklistedchannels, blacklistcategory, unblacklistcategory, blacklistedcategories, setmessagerole, unsetmessagerole, viewmessageroles, setresettime, variables, testmsg | 18 |
| Voice | vc, addvctime, reducevctime, clearvoice, resetmyvoice | 5 |
| Leaderboards | leaderboard, lb, lb_invites, lb_messages, lb_weekly, lb_daily, lb_voice, lb_weeklyvoice, lb_dailyvoice, createlivelb, deletelivelb, showlivelbs | 12 |
| Auto-Roles | autorole, setautorole, unsetautorole, viewautoroles | 4 |
| Giveaways | gcreate, gstart, gwstart, greroll, gend, setwin, finish, reroll, setgiveaway, unsetgiveaway, viewwinnerrole, viewbypassrole | 12 |
| Timers | tstart, tpause, tresume, tend | 4 |
| Greetings | setjoinchannel, unsetwelcomechannel, setleave, unsetleavechannel, setjoinmessage, unsetjoinmessage, setleavemessage, unsetleavemessage, setvanitymessage, unsetvanitymessage, setgreet, disablegreet, greetchannels, greetvariables | 14 |
| Moderation | kick, ban, unban, mute, unmute, erase, disable, enable, automod | 9 |
| Polls | createpoll, epoll | 2 |
| Music | play, skip, stop, queue, nowplaying | 5 |
| Utility | ping, serverinfo, userinfo, avatar, crypto | 5 |
| Premium | premium, premium_add, premium_remove, noprefix | 4 |
| Admin | setowner, unsetowner, owners, setstaff, unsetstaff, staff, blacklist_user, customize, emoji, refresh_emojis, reset_emojis, bonus | 12 |
| Help | help, credits, about | 3 |
| Security | antinuke, antiraid | 2 |

**Total Commands: ~120+**

---

## 🔑 Command Prefixes

- Primary Prefix: `!`
- Secondary Prefix: `,`
- No Prefix Mode: Available to premium users (e.g., `invites` works without prefix)

---

## ⚙️ Permission Levels

- **Anyone:** No special permissions required
- **Manage Guild:** Requires manage_guild permission
- **Manage Messages:** Requires manage_messages permission
- **Moderate Members:** Requires moderate_members permission
- **Ban Members:** Requires ban_members permission
- **Kick Members:** Requires kick_members permission
- **Administrator:** Requires administrator permission
- **Bot Owner:** Owner account or in bot_owners DB table
- **Bot Staff:** Owner/Staff account or in bot_staff DB table
- **Primary Owner:** Hardcoded PRIMARY_OWNER_IDS (immutable)

---

## 💡 Tips & Tricks

1. **Invite Tracking:** Automatically tracks who invited whom when they join
2. **Auto-Roles:** Can assign roles based on invites, messages, or on all/bots/humans
3. **Live Leaderboards:** Updates every 30 seconds automatically
4. **Message Variables:** Use `{user}`, `{username}`, `{server}`, `{membercount}`, `{inviter}` in custom messages
5. **Giveaways:** React with 🎉 to enter, bot picks random winner
6. **Voice Tracking:** Separate counters for alltime, weekly, and daily voice time
7. **Blacklisting:** Channels/categories can be excluded from message tracking
8. **No-Prefix:** Premium users can use commands without prefix
9. **Antinuke:** Protects against server raids and unauthorized changes
10. **Music:** Queue system allows multiple songs to be queued

---

**End of Commands List**

Generated: July 29, 2026


## Stability & Power Update
- `,setup create` / `,setup staff` / `,setup vip` / `,setup friends` / `,setup remove` / `,setup list`
- `,extraowner add|remove|list`
- `,customize name|bio|avatar|banner|reset`
- `,lock all` / `,unlock all`
- `,hide all` / `,unhide all`
- `,commandcount`
- Global user No-Prefix remains active across every guild until expiry/removal.
- Invite creation is never an Anti-Nuke punishment.
