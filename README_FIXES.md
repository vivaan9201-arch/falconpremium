# Falcon Premium Bot v2 — Stability & Power Update

## Included fixes
- Giveaway code was left unchanged.
- Fixed the duplicated `on_member_join` handler that was preventing welcome/invite processing from reaching the variable replacement helper.
- No-Prefix remains a **global user setting**: once a user is granted No-Prefix, it works in every server where Falcon is present until expiry/removal.
- Fixed Anti-Nuke owner immunity check (`await is_bot_owner(...)`).
- Invite creation is explicitly **not an Anti-Nuke punishment event**. Creating a normal Discord invite is logged only; it cannot trigger an Anti-Nuke ban.
- AutoMod now stops command processing when it deletes/handles a violating message and uses the requested AutoMod emoji.
- Bot-owner mentions receive the requested crown reaction.
- Added server setup role management: Staff, VIP, Friends, create/list/remove.
- Added server Extra Owner management. Only the bot owner or current Discord server owner can add/remove Extra Owners.
- Added server customization: name/nickname, bio, avatar URL, banner URL, reset. Server owner, Extra Owners, and bot owners can manage it.
- Global bot account avatar/banner remain bot-owner-only because Discord applies those changes to the bot account globally.
- Added `lock all`, `unlock all`, `hide all`, and `unhide all`.
- Added a large Power Command shortcut library, pushing the registered prefix command count above 600 while keeping existing commands intact.
- Added better command error reporting instead of silently swallowing every unexpected command error.
- Added `requirements.txt`.

## Important permissions
For full functionality, give the bot the permissions it actually needs for the features you enable: Manage Channels, Manage Roles, Manage Messages, Kick Members, Ban Members, Moderate Members, Manage Webhooks, View Audit Log, and Send Messages/Embed Links.

## Main new commands
- `,setup` / `,setup create` / `,setup staff` / `,setup vip` / `,setup friends` / `,setup remove all` / `,setup list`
- `,extraowner add @user` / `,extraowner remove @user` / `,extraowner list`
- `,customize name <name>` / `,customize bio <text>` / `,customize avatar <url>` / `,customize banner <url>` / `,customize reset`
- `,lock all` / `,unlock all` / `,hide all` / `,unhide all`
- `,commandcount`

## AutoMod
- `,automod status`
- `,automod enable invite|link|spam`
- `,automod disable invite|link|spam`

## Anti-Nuke
Invite creation is deliberately excluded from Anti-Nuke punishment. The existing channel/role/ban/kick/bot/webhook/server-edit protections remain available.
