import discord
from discord.ext import commands
import datetime
import asyncio
import re
import random
import aiosqlite
import io
import aiohttp
from collections import defaultdict, deque

# Required for tracking invites, reading messages, and force-fetching reactions
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.invites = True
intents.presences = True

# Immutable primary owners — cannot be removed via commands
PRIMARY_OWNER_IDS = [
    1447574490900070523,
    1386405999144992818,
    1411017995819552802,
]
PRIMARY_OWNER_ID = PRIMARY_OWNER_IDS[0]  # backward compat

class FalconBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=self.get_prefix, intents=intents, help_command=None)
        self.inv_cache = {}
        self.db = None
        self.owner_id = PRIMARY_OWNER_ID
        self.owner_ids = set(PRIMARY_OWNER_IDS)
        # In-memory anti-raid / anti-nuke trackers
        self.recent_joins = defaultdict(lambda: deque(maxlen=50))
        self.recent_channel_deletes = defaultdict(lambda: deque(maxlen=50))
        self.recent_role_deletes = defaultdict(lambda: deque(maxlen=50))
        self.recent_bans = defaultdict(lambda: deque(maxlen=50))
        # Music: per-guild queues
        self.music_queues = defaultdict(list)
        self.now_playing = {}
        # Color scheme
        self.color = 0xffdd00

    async def get_prefix(self, message):
        if self.db:
            async with self.db.execute("SELECT expiry FROM noprefix WHERE user_id = ?", (message.author.id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    expiry = datetime.datetime.fromisoformat(row[0])
                    if datetime.datetime.now() < expiry:
                        return [",", ""]
        return [","]

    async def setup_hook(self):
        self.db = await aiosqlite.connect("falcon_data.db")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, joins INTEGER DEFAULT 0,
                left INTEGER DEFAULT 0, bonus INTEGER DEFAULT 0,
                total_msgs INTEGER DEFAULT 0, weekly_msgs INTEGER DEFAULT 0, today_msgs INTEGER DEFAULT 0,
                voice_alltime INTEGER DEFAULT 0, voice_weekly INTEGER DEFAULT 0, voice_daily INTEGER DEFAULT 0
            )""")
        # Migration: add voice columns to existing databases
        for col, default in [("voice_alltime", 0), ("voice_weekly", 0), ("voice_daily", 0)]:
            try:
                await self.db.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT {default}")
                await self.db.commit()
            except Exception:
                pass  # Column already exists

        await self.db.execute("CREATE TABLE IF NOT EXISTS giveaways (msg_id INTEGER PRIMARY KEY, forced_winner INTEGER, prize TEXT, host_id INTEGER)")
        await self.db.execute("CREATE TABLE IF NOT EXISTS noprefix (user_id INTEGER PRIMARY KEY, expiry TEXT)")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS invite_tracker (
                invitee_id INTEGER PRIMARY KEY,
                inviter_id INTEGER,
                joined_at TEXT
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                join_channel_id INTEGER,
                leave_channel_id INTEGER,
                join_message TEXT,
                leave_message TEXT,
                vanity_message TEXT,
                alt_threshold INTEGER,
                msg_weekly_reset TEXT,
                msg_daily_reset TEXT,
                voice_daily_reset TEXT,
                voice_weekly_reset TEXT
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS invite_roles (
                guild_id INTEGER,
                role_id INTEGER,
                required_invites INTEGER,
                PRIMARY KEY (guild_id, role_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS message_roles (
                guild_id INTEGER,
                role_id INTEGER,
                required_msgs INTEGER,
                PRIMARY KEY (guild_id, role_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS blacklisted_channels (
                guild_id INTEGER,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, channel_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS blacklisted_categories (
                guild_id INTEGER,
                category_id INTEGER,
                PRIMARY KEY (guild_id, category_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS greet_channels (
                guild_id INTEGER,
                channel_id INTEGER,
                greet_type TEXT DEFAULT 'embed',
                PRIMARY KEY (guild_id, channel_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS autoroles (
                guild_id INTEGER,
                role_id INTEGER,
                role_type TEXT DEFAULT 'all',
                PRIMARY KEY (guild_id, role_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS live_leaderboards (
                guild_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                lb_type TEXT,
                PRIMARY KEY (guild_id, lb_type)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS disabled_commands (
                guild_id INTEGER,
                command_name TEXT,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, command_name, channel_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS disabled_modules (
                guild_id INTEGER,
                module_name TEXT,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, module_name, channel_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                msg_id INTEGER PRIMARY KEY,
                question TEXT,
                options TEXT,
                channel_id INTEGER,
                active INTEGER DEFAULT 1
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS premium_guilds (
                guild_id INTEGER PRIMARY KEY,
                expiry TEXT
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS premium_users (
                user_id INTEGER PRIMARY KEY,
                expiry TEXT
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_help_emojis (
                guild_id INTEGER PRIMARY KEY,
                emojis TEXT
            )""")
        await self.db.execute("CREATE TABLE IF NOT EXISTS bot_owners (user_id INTEGER PRIMARY KEY)")
        await self.db.execute("CREATE TABLE IF NOT EXISTS bot_staff (user_id INTEGER PRIMARY KEY)")
        await self.db.execute("CREATE TABLE IF NOT EXISTS user_blacklist (user_id INTEGER PRIMARY KEY, reason TEXT, by_user INTEGER, at TEXT)")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS automod_settings (
                guild_id INTEGER PRIMARY KEY,
                anti_invite INTEGER DEFAULT 0,
                anti_link INTEGER DEFAULT 0,
                anti_spam INTEGER DEFAULT 0
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                ch_del_limit INTEGER DEFAULT 3,
                role_del_limit INTEGER DEFAULT 3,
                ban_limit INTEGER DEFAULT 3,
                whitelist TEXT DEFAULT ''
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antiraid_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                join_limit INTEGER DEFAULT 5,
                window_seconds INTEGER DEFAULT 10
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_v2_events (
                guild_id INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, event_name)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_v2_whitelist (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                events TEXT DEFAULT '*',
                PRIMARY KEY (guild_id, user_id)
            )""")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_v2_settings (
                guild_id INTEGER PRIMARY KEY,
                recreate_channels INTEGER DEFAULT 1,
                delete_unauthorized INTEGER DEFAULT 1,
                punish_action TEXT DEFAULT 'ban'
            )""")
        await self.db.commit()
        await self.tree.sync()
        self.loop.create_task(self.daily_reset_task())
        self.loop.create_task(self.live_lb_update_task())

    async def daily_reset_task(self):
        while True:
            now = datetime.datetime.now()
            tomorrow = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time(0, 0))
            await asyncio.sleep((tomorrow - now).total_seconds())
            await self.db.execute("UPDATE users SET today_msgs = 0, voice_daily = 0")
            await self.db.commit()

    async def live_lb_update_task(self):
        while True:
            await asyncio.sleep(30)
            try:
                async with self.db.execute("SELECT guild_id, channel_id, message_id, lb_type FROM live_leaderboards") as cur:
                    rows = await cur.fetchall()
                for guild_id, channel_id, message_id, lb_type in rows:
                    guild = self.get_guild(guild_id)
                    if not guild: continue
                    channel = guild.get_channel(channel_id)
                    if not channel: continue
                    try:
                        msg = await channel.fetch_message(message_id)
                        embed = await build_lb_embed(guild, lb_type)
                        await msg.edit(embed=embed)
                    except: pass
            except: pass

bot = FalconBot()

@bot.event
async def on_command_error(ctx, error):
    error = getattr(error, 'original', error)
    
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(color=0xffdd00, title="❌ Missing Arguments")
        embed.description = f"**Command:** `,{ctx.command.name}`\n\n**Missing:** `{error.param.name}`"
        embed.add_field(name="Usage:", value=f"`{ctx.prefix}{ctx.command.name} {ctx.command.signature}`", inline=False)
        embed.add_field(name="Help:", value=f"{ctx.command.help or 'No description available.'}", inline=False)
        return await ctx.send(embed=embed)
    if isinstance(error, commands.BadArgument):
        embed = discord.Embed(color=0xffdd00, title="❌ Invalid Argument")
        embed.description = f"**Command:** `,{ctx.command.name}`\n\n**Error:** {str(error)}"
        embed.add_field(name="Usage:", value=f"`{ctx.prefix}{ctx.command.name} {ctx.command.signature}`", inline=False)
        return await ctx.send(embed=embed)
    
    # Silently ignore other errors
    return

# ─── Emoji Constants ───────────────────────────────────────────────
TADA_GIF    = "<:tada:1532075669901541437>"
DOT         = "<:dot:1532417520219197641>"
GIFT        = "<:wvay:1532417486954303629> "
BLACK_TADA  = "<:tada:1532075669901541437>"
ARROW       = "<:fp_arrow:1532073102580646070>"

# Category emojis
E_NEWS      = "<:news:1532075439563079690>"
E_PREMIUM   = "<:fp_premium:1532074078264103063> "
E_INVITE    = "<:fp_invite:1532074030692045042> "
E_MSG       = "<:ms:1532075752504295748> "
E_VOICE     = "<:vc:1532075722141597798> "
E_ROLE      = "<:fp_premium:1532074078264103063> "
E_LB        = "<:lb:1532075699018530937>"
E_GW        = "<:tada:1532075669901541437>"
E_TIMER     = "<:timer:1532075644169617568>"
E_GREET     = "<:wlcm:1532075618735362179> "
E_MOD       = "<:mods:1532075594756653186> "
E_MANAGE    = "<:fp_invite:1532074030692045042>"
E_POLL      = "<:polls:1532075571503300739> "
E_UTILITY   = "<:utlity:1532075545985286377> "
E_CONTACT   = "<:support:1532075466490642594> "

# Status Emojis
ONLINE  = "🟢"
OFFLINE = "⚫"
DND     = "🔴"
IDLE    = "🟡"

def get_status_emoji(member):
    if member is None: return OFFLINE
    s = member.status
    if s == discord.Status.online: return ONLINE
    elif s == discord.Status.dnd: return DND
    elif s == discord.Status.idle: return IDLE
    else: return OFFLINE

# ─── DB Helpers ────────────────────────────────────────────────────
async def update_user(user_id, **kwargs):
    cols = ", ".join([f"{k} = {k} + ?" for k in kwargs.keys()])
    vals = list(kwargs.values())
    await bot.db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    await bot.db.execute(f"UPDATE users SET {cols} WHERE user_id = ?", vals + [user_id])
    await bot.db.commit()

async def get_user_data(user_id):
    async with bot.db.execute(
        "SELECT joins, left, bonus, total_msgs, weekly_msgs, today_msgs, voice_alltime, voice_weekly, voice_daily FROM users WHERE user_id = ?",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row if row else (0, 0, 0, 0, 0, 0, 0, 0, 0)

async def build_lb_embed(guild, lb_type):
    members_ids = [m.id for m in guild.members]
    placeholders = ",".join("?" * len(members_ids))
    col_map = {
        "invites": ("joins - left + bonus", "🏆 Invite Leaderboard"),
        "messages": ("total_msgs", "💬 Message Leaderboard"),
        "weeklymessages": ("weekly_msgs", "📅 Weekly Message Leaderboard"),
        "dailymessages": ("today_msgs", "☀️ Daily Message Leaderboard"),
        "voice": ("voice_alltime", "🎙️ Voice Leaderboard"),
        "weeklyvoice": ("voice_weekly", "📅 Weekly Voice Leaderboard"),
        "dailyvoice": ("voice_daily", "☀️ Daily Voice Leaderboard"),
    }
    col, title = col_map.get(lb_type, ("total_msgs", "Leaderboard"))
    async with bot.db.execute(
        f"SELECT user_id, {col} FROM users WHERE user_id IN ({placeholders}) ORDER BY {col} DESC LIMIT 10",
        members_ids
    ) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title=title)
    if not rows:
        embed.description = f"{DOT} No data yet."
    else:
        lines = []
        for uid, val in rows:
            m = guild.get_member(uid)
            name = m.name if m else f"Unknown ({uid})"
            lines.append(f"{DOT} **{name}** • **{val}**")
        embed.description = "\n".join(lines)
    embed.set_footer(text=f"Updated at {datetime.datetime.now().strftime('%I:%M %p')}")
    return embed

# ─── Owner / Staff Permission Helpers ──────────────────────────────
async def is_bot_owner(uid):
    if uid in PRIMARY_OWNER_IDS:
        return True
    async with bot.db.execute("SELECT 1 FROM bot_owners WHERE user_id = ?", (uid,)) as cur:
        return (await cur.fetchone()) is not None

async def is_bot_blacklisted(uid):
    if uid in PRIMARY_OWNER_IDS:
        return False
    async with bot.db.execute("SELECT 1 FROM user_blacklist WHERE user_id = ?", (uid,)) as cur:
        return (await cur.fetchone()) is not None

async def is_user_premium(uid):
    if uid in PRIMARY_OWNER_IDS:
        return True
    async with bot.db.execute("SELECT expiry FROM premium_users WHERE user_id = ?", (uid,)) as cur:
        row = await cur.fetchone()
    if not row:
        return False
    try:
        return datetime.datetime.fromisoformat(row[0]) > datetime.datetime.now()
    except Exception:
        return False

async def is_bot_staff(uid):
    if await is_bot_owner(uid):
        return True
    async with bot.db.execute("SELECT 1 FROM bot_staff WHERE user_id = ?", (uid,)) as cur:
        return (await cur.fetchone()) is not None

# ─── Owner-only Auto Emoji Feature ─────────────────────────────────
async def get_guild_dropdown_emojis(guild_id):
    if guild_id is None:
        return None
    async with bot.db.execute("SELECT emojis FROM guild_help_emojis WHERE guild_id = ?", (guild_id,)) as cur:
        row = await cur.fetchone()
        if row and row[0]:
            return row[0].split("|")
    return None

SECTION_KEYWORDS = [
    # premium
    ["premium", "vip", "crown", "diamond", "gem", "star", "sparkle", "gold", "rich"],
    # invites
    ["invite", "invites", "envelope", "mail", "letter", "join", "member", "add", "plus", "people"],
    # messages
    ["message", "msg", "chat", "talk", "speech", "bubble", "comment", "text", "say", "type"],
    # voice
    ["voice", "vc", "mic", "microphone", "audio", "sound", "speak", "headphone", "music"],
    # autoroles
    ["role", "autorole", "tag", "badge", "label", "rank"],
    # liveleaderboards
    ["leaderboard", "lb", "trophy", "top", "winner", "first", "medal", "rank", "podium"],
    # giveaway
    ["giveaway", "gift", "gw", "present", "tada", "party", "celebrate", "confetti"],
    # timer
    ["timer", "time", "clock", "alarm", "hourglass", "stopwatch", "watch"],
    # greet
    ["greet", "welcome", "wave", "hello", "hi", "hey", "handshake"],
    # moderation
    ["mod", "ban", "hammer", "shield", "gavel", "kick", "lock", "staff", "police", "guard", "admin"],
    # managecommands
    ["gear", "setting", "settings", "manage", "config", "tool", "wrench", "cog", "system"],
    # poll
    ["poll", "vote", "chart", "bar", "stats", "graph", "ballot", "survey"],
    # utility
    ["util", "utility", "tool", "wrench", "ping", "info", "search", "lens", "magnify"],
    # credits
    ["contact", "support", "credit", "credits", "link", "owner", "heart", "team", "crew", "thanks", "love"],
]

def _smart_pick_emojis(guild_emojis):
    chosen = []
    used_ids = set()
    available = list(guild_emojis)
    for keywords in SECTION_KEYWORDS:
        match = None
        for kw in keywords:
            for e in available:
                if e.id in used_ids:
                    continue
                if kw in e.name.lower():
                    match = e
                    break
            if match:
                break
        if match:
            used_ids.add(match.id)
            chosen.append(str(match))
        else:
            chosen.append("")  # fallback to default later
    # Fill any empty slots with leftover unused emojis (in order)
    leftovers = [e for e in available if e.id not in used_ids]
    li = 0
    for i in range(len(chosen)):
        if not chosen[i] and li < len(leftovers):
            chosen[i] = str(leftovers[li])
            used_ids.add(leftovers[li].id)
            li += 1
    return chosen

async def store_guild_dropdown_emojis(guild):
    pool = [e for e in guild.emojis if not e.animated]
    if not pool:
        pool = list(guild.emojis)
    if not pool:
        return False
    chosen = _smart_pick_emojis(pool)
    if not any(chosen):
        return False
    await bot.db.execute(
        "INSERT OR REPLACE INTO guild_help_emojis (guild_id, emojis) VALUES (?, ?)",
        (guild.id, "|".join(chosen))
    )
    await bot.db.commit()
    return True

# ─── Events ────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=",help"))
    for guild in bot.guilds:
        try:
            invs = await guild.invites()
            bot.inv_cache[guild.id] = {i.code: i.uses for i in invs}
        except: pass
        # Auto-apply emojis on existing servers if any owner is a member and not already set
        try:
            existing = await get_guild_dropdown_emojis(guild.id)
            if not existing:
                async with bot.db.execute("SELECT user_id FROM bot_owners") as cur:
                    extra_owners = {r[0] for r in await cur.fetchall()}
                owner_ids = extra_owners | set(PRIMARY_OWNER_IDS)
                if any(guild.get_member(oid) for oid in owner_ids):
                    await store_guild_dropdown_emojis(guild)
        except: pass
    print(f"Falcon™ Premium is live and tracking.")

@bot.event
async def on_guild_join(guild):
    try:
        invs = await guild.invites()
        bot.inv_cache[guild.id] = {i.code: i.uses for i in invs}
    except: pass
    inviter = None
    try:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=10):
            if entry.target and entry.target.id == bot.user.id:
                inviter = entry.user
                break
    except: pass
    if inviter and await is_bot_owner(inviter.id):
        await store_guild_dropdown_emojis(guild)
    
    # Check if guild owner has premium
    owner_id = guild.owner_id
    has_premium = await is_user_premium(owner_id)
    
    if not has_premium:
        # Send DM to bot owner asking for approval
        try:
            owner = await bot.fetch_user(1447574490900070523)
            
            # Create Yes/Leave buttons
            class PremiumView(discord.ui.View):
                def __init__(self, guild_obj):
                    super().__init__(timeout=3600)
                    self.guild_obj = guild_obj
                    self.approved = False
                
                @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
                async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await bot.db.execute("INSERT OR REPLACE INTO premium_guilds (guild_id, expiry) VALUES (?, ?)",
                                       (self.guild_obj.id, (datetime.datetime.now() + datetime.timedelta(days=365)).isoformat()))
                    await bot.db.commit()
                    embed = discord.Embed(color=0xffdd00, description=f"✅ Guild **{self.guild_obj.name}** approved for premium!")
                    await interaction.response.edit_message(embed=embed, view=None)
                    self.approved = True
                
                @discord.ui.button(label="Leave", style=discord.ButtonStyle.red)
                async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    embed = discord.Embed(color=0xffdd00, description=f"❌ Bot left **{self.guild_obj.name}**")
                    await interaction.response.edit_message(embed=embed, view=None)
                    await self.guild_obj.leave()
            
            embed = discord.Embed(color=0xffdd00, title="🆕 New Guild Request")
            embed.description = f"**Guild:** {guild.name}\n**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n**Members:** {guild.member_count}\n\nGuild owner doesn't have premium. Approve?"
            
            view = PremiumView(guild)
            await owner.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error sending premium check DM: {e}")

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # Check if bot is mentioned at the start
    if bot.user.mentioned_in(message) and message.content.startswith(bot.user.mention):
        return await message.reply("My Prefix Here Is `,`", mention_author=False)
    
    if await is_bot_blacklisted(message.author.id):
        return  # User is bot-blacklisted; ignore entirely
    # Automod (anti-link / anti-invite) — runs before command processing
    if message.guild:
        await _automod_check(message)
    async with bot.db.execute("SELECT channel_id FROM blacklisted_channels WHERE guild_id = ? AND channel_id = ?",
                              (message.guild.id if message.guild else 0, message.channel.id)) as cur:
        if await cur.fetchone():
            return await bot.process_commands(message)
    if message.guild and message.channel.category_id:
        async with bot.db.execute("SELECT category_id FROM blacklisted_categories WHERE guild_id = ? AND category_id = ?",
                                  (message.guild.id, message.channel.category_id)) as cur:
            if await cur.fetchone():
                return await bot.process_commands(message)
    await update_user(message.author.id, total_msgs=1, weekly_msgs=1, today_msgs=1)
    if message.guild:
        _, _, _, total_msgs, _, _, _, _, _ = await get_user_data(message.author.id)
        async with bot.db.execute("SELECT role_id, required_msgs FROM message_roles WHERE guild_id = ?",
                                  (message.guild.id,)) as cur:
            rows = await cur.fetchall()
        for role_id, req in rows:
            if total_msgs >= req:
                role = message.guild.get_role(role_id)
                if role and role not in message.author.roles:
                    try: await message.author.add_roles(role)
                    except: pass
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    async def replace_message_variables(text, member, inviter, guild):
        """Replace all message variables"""
        from dateutil.relativedelta import relativedelta
        
        # Member counts
        text = text.replace("{member_count}", str(guild.member_count))
        
        # Ordinal member count
        ordinal = {1: "st", 2: "nd", 3: "rd"}.get(guild.member_count % 10 if guild.member_count % 100 not in [11, 12, 13] else 0, "th")
        text = text.replace("{ordinal_member_count}", f"{guild.member_count}{ordinal}")
        
        # Member variables
        text = text.replace("{member_name}", member.name)
        text = text.replace("{member}", f"{member.name}#{member.discriminator}")
        text = text.replace("{member_mention}", member.mention)
        text = text.replace("{member_avatar}", member.display_avatar.url)
        text = text.replace("{member_banner}", member.banner.url if member.banner else "None")
        text = text.replace("{member_created_at}", member.created_at.strftime("%Y-%m-%d %H:%M:%S"))
        
        # Member relative time
        now = datetime.datetime.now(datetime.timezone.utc)
        created_ago = relativedelta(now, member.created_at.replace(tzinfo=datetime.timezone.utc))
        ago_text = f"{created_ago.years}y {created_ago.months}m {created_ago.days}d ago" if created_ago.years else f"{created_ago.months}m {created_ago.days}d ago"
        text = text.replace("{member_created_ago}", ago_text)
        
        # Join time
        text = text.replace("{join_time}", member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else "Unknown")
        
        # Guild variables
        text = text.replace("{guild_name}", guild.name)
        text = text.replace("{guild_icon}", guild.icon.url if guild.icon else "None")
        text = text.replace("{guild_banner}", guild.banner.url if guild.banner else "None")
        
        if inviter:
            # Inviter name and mentions
            text = text.replace("{inviter_name}", inviter.name)
            text = text.replace("{inviter_mention}", inviter.mention)
            text = text.replace("{inviter_avatar}", inviter.display_avatar.url)
            text = text.replace("{inviter_banner}", inviter.banner.url if inviter.banner else "None")
            text = text.replace("{inviter_created_at}", inviter.created_at.strftime("%Y-%m-%d %H:%M:%S"))
            
            # Inviter relative time
            inviter_created_ago = relativedelta(now, inviter.created_at.replace(tzinfo=datetime.timezone.utc))
            inviter_ago_text = f"{inviter_created_ago.years}y {inviter_created_ago.months}m {inviter_created_ago.days}d ago" if inviter_created_ago.years else f"{inviter_created_ago.months}m {inviter_created_ago.days}d ago"
            text = text.replace("{inviter_created_ago}", inviter_ago_text)
            
            # Inviter joined at
            inviter_in_guild = guild.get_member(inviter.id)
            if inviter_in_guild and inviter_in_guild.joined_at:
                text = text.replace("{inviter_joined_at}", inviter_in_guild.joined_at.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                text = text.replace("{inviter_joined_at}", "Unknown")
            
            # Inviter stats
            joins, left, bonus, _, _, _, _, _, _ = await get_user_data(inviter.id)
            total_invites = joins - left + bonus
            text = text.replace("{invites}", str(total_invites))
            text = text.replace("{inviter_reg_invites}", str(joins))
            text = text.replace("{fake_invites}", str(left))
            text = text.replace("{left_invites}", str(left))
        
        return text
    
@bot.event
async def on_member_join(member):
    try:
        # Auto roles
        async with bot.db.execute("SELECT role_id, role_type FROM autoroles WHERE guild_id=?", (member.guild.id,)) as cur:
            ar_rows = await cur.fetchall()
        for role_id, role_type in ar_rows:
            if role_type == "bots" and not member.bot: continue
            if role_type == "humans" and member.bot: continue
            role = member.guild.get_role(role_id)
            if role:
                try: await member.add_roles(role)
                except: pass

        invs_after = await member.guild.invites()
        old_invs = bot.inv_cache.get(member.guild.id, {})
        inviter = None
        used_vanity = False
        for inv in invs_after:
            if inv.uses > old_invs.get(inv.code, 0):
                inviter = inv.inviter
                await update_user(inv.inviter.id, joins=1)
                break
        if not inviter:
            try:
                vanity = await member.guild.vanity_invite()
                if vanity: used_vanity = True
            except: pass
        bot.inv_cache[member.guild.id] = {i.code: i.uses for i in invs_after}

        if inviter:
            joined_at = datetime.datetime.now().isoformat()
            await bot.db.execute(
                "INSERT OR REPLACE INTO invite_tracker (invitee_id, inviter_id, joined_at) VALUES (?, ?, ?)",
                (member.id, inviter.id, joined_at)
            )
            await bot.db.commit()
            joins, left, bonus, _, _, _, _, _, _ = await get_user_data(inviter.id)
            net = joins - left + bonus
            async with bot.db.execute("SELECT role_id, required_invites FROM invite_roles WHERE guild_id = ?",
                                      (member.guild.id,)) as cur:
                rows = await cur.fetchall()
            inv_member = member.guild.get_member(inviter.id)
            if inv_member:
                for role_id, req in rows:
                    if net >= req:
                        role = member.guild.get_role(role_id)
                        if role and role not in inv_member.roles:
                            try: await inv_member.add_roles(role)
                            except: pass

        async with bot.db.execute("SELECT join_channel_id, join_message, vanity_message FROM guild_settings WHERE guild_id = ?",
                                  (member.guild.id,)) as cur:
            row = await cur.fetchone()
        if row:
            ch_id, join_msg, vanity_msg = row
            channel = member.guild.get_channel(ch_id) if ch_id else None
            if channel:
                raw = vanity_msg if used_vanity and vanity_msg else join_msg
                if raw:
                    text = await replace_message_variables(raw, member, inviter, member.guild)
                    await channel.send(text)
                else:
                    inviter_text = inviter.mention if inviter else ("Vanity invite" if used_vanity else "Unknown")
                    embed = discord.Embed(
                        description=f"Welcome {member.mention} to **{member.guild.name}**!\n{DOT} Invited by: {inviter_text}\n{DOT} You are member **#{member.guild.member_count}**",
                        color=0xffdd00
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await channel.send(embed=embed)

        async with bot.db.execute("SELECT channel_id, greet_type FROM greet_channels WHERE guild_id = ?",
                                  (member.guild.id,)) as cur:
            greet_rows = await cur.fetchall()
        for (g_ch_id, g_type) in greet_rows:
            g_ch = member.guild.get_channel(g_ch_id)
            if not g_ch: continue
            if g_type == "embed":
                embed = discord.Embed(description=f"👋 Welcome {member.mention} to **{member.guild.name}**!", color=0xffdd00)
                embed.set_thumbnail(url=member.display_avatar.url)
                await g_ch.send(embed=embed)
            else:
                await g_ch.send(f"👋 Welcome {member.mention} to **{member.guild.name}**!")
    except: pass

@bot.event
async def on_member_remove(member):
    await update_user(member.id, left=1)
    try:
        async with bot.db.execute("SELECT leave_channel_id, leave_message FROM guild_settings WHERE guild_id = ?",
                                  (member.guild.id,)) as cur:
            row = await cur.fetchone()
        if row:
            ch_id, leave_msg = row
            channel = member.guild.get_channel(ch_id) if ch_id else None
            if channel:
                if leave_msg:
                    text = leave_msg.replace("{user}", member.mention)\
                                    .replace("{username}", member.name)\
                                    .replace("{server}", member.guild.name)\
                                    .replace("{membercount}", str(member.guild.member_count))
                    await channel.send(text)
                else:
                    embed = discord.Embed(
                        description=f"**{member.name}** has left **{member.guild.name}**.\n{DOT} Members: **{member.guild.member_count}**",
                        color=0xFF0000
                    )
                    await channel.send(embed=embed)
    except: pass

# Voice state tracking
voice_join_times = {}

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    uid = member.id
    if before.channel is None and after.channel is not None:
        voice_join_times[uid] = datetime.datetime.now()
    elif before.channel is not None and after.channel is None:
        if uid in voice_join_times:
            duration = int((datetime.datetime.now() - voice_join_times.pop(uid)).total_seconds())
            await update_user(uid, voice_alltime=duration, voice_weekly=duration, voice_daily=duration)

# ─── INVITE COMMANDS ──────────────────────────────────────────────

@bot.command(name="invites")
async def invites_cmd(ctx, user: discord.Member = None):
    user = user or ctx.author
    joins, left, bonus, _, _, _, _, _, _ = await get_user_data(user.id)
    total = joins - left + bonus
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name=f"{user.name}'s Invites Stats", icon_url=user.display_avatar.url)
    embed.description = f"{user.name} currently has **{total}** invites."
    embed.add_field(name="Total:", value=f"<:fp_arrow:1532073102580646070> ・ **Joins : {joins}**\n<:fp_arrow:1532073102580646070> ・ **Left : {left}**\n<:fp_arrow:1532073102580646070> ・ **Bonus : {bonus}**", inline=False)
    embed.add_field(name="Other:", value=f"<:fp_arrow:1532073102580646070> ・ **Fake : 0**\n<:fp_arrow:1532073102580646070> ・ **Rejoins : 0**", inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.name} • Today at {datetime.datetime.now().strftime('%I:%M %p')}", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="i")
async def i_cmd(ctx, user: discord.Member = None):
    await invites_cmd(ctx, user)

@bot.command(name="inviter")
async def inviter_cmd(ctx, user: discord.Member = None):
    user = user or ctx.author
    async with bot.db.execute("SELECT inviter_id, joined_at FROM invite_tracker WHERE invitee_id = ?", (user.id,)) as cursor:
        row = await cursor.fetchone()
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name="Inviter information")
    if row:
        inviter_id, joined_at_str = row
        inviter = ctx.guild.get_member(inviter_id)
        inviter_mention = f"<@!{inviter_id}>"
        try:
            joined_dt = datetime.datetime.fromisoformat(joined_at_str)
            delta = datetime.datetime.now() - joined_dt
            days = delta.days
            joined_str = "Today" if days == 0 else ("1 day ago" if days == 1 else f"{days} days ago")
        except:
            joined_str = "Unknown"
        embed.description = (f"**! {user.name}** was invited by {inviter_mention}\nJoined : {joined_str}")
    else:
        embed.description = f"**! {user.name}** — No inviter data found.\nThey may have joined before tracking started."
    embed.set_footer(text=f"Today at {datetime.datetime.now().strftime('%I:%M %p')}", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="invited")
async def invited_cmd(ctx, user: discord.Member = None):
    user = user or ctx.author
    async with bot.db.execute("SELECT invitee_id, joined_at FROM invite_tracker WHERE inviter_id = ?", (user.id,)) as cursor:
        rows = await cursor.fetchall()
    if not rows:
        embed = discord.Embed(color=0xffdd00)
        embed.set_author(name=f"Invited list of ! {user.name}")
        embed.description = "This user has not invited anyone yet."
        embed.set_footer(text=f"Page 1/1", icon_url=bot.user.display_avatar.url)
        return await ctx.send(embed=embed)
    entries = []
    for idx, (invitee_id, _) in enumerate(rows, start=1):
        member = ctx.guild.get_member(invitee_id)
        name = member.name if member else f"Unknown ({invitee_id})"
        status_emoji = get_status_emoji(member)
        entries.append((idx, name, status_emoji))
    page_size = 10
    pages = [entries[i:i+page_size] for i in range(0, len(entries), page_size)]
    total_pages = len(pages)
    current_page = [0]

    def build_embed(page_idx):
        embed = discord.Embed(color=0xffdd00)
        embed.set_author(name=f"Invited list of ! {user.name}", icon_url=user.display_avatar.url)
        lines = [f"**#{idx}** •! **{name}** • {status}" for idx, name, status in pages[page_idx]]
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {page_idx + 1}/{total_pages}", icon_url=bot.user.display_avatar.url)
        return embed

    class PaginationView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            self.update_buttons()
        def update_buttons(self):
            self.first_btn.disabled = current_page[0] == 0
            self.prev_btn.disabled = current_page[0] == 0
            self.next_btn.disabled = current_page[0] == total_pages - 1
            self.last_btn.disabled = current_page[0] == total_pages - 1
        @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
        async def first_btn(self, interaction, button):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not your command!", ephemeral=True)
            current_page[0] = 0; self.update_buttons()
            await interaction.response.edit_message(embed=build_embed(current_page[0]), view=self)
        @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary)
        async def prev_btn(self, interaction, button):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not your command!", ephemeral=True)
            current_page[0] = max(0, current_page[0] - 1); self.update_buttons()
            await interaction.response.edit_message(embed=build_embed(current_page[0]), view=self)
        @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
        async def stop_btn(self, interaction, button):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not your command!", ephemeral=True)
            for child in self.children: child.disabled = True
            await interaction.response.edit_message(view=self); self.stop()
        @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary)
        async def next_btn(self, interaction, button):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not your command!", ephemeral=True)
            current_page[0] = min(total_pages - 1, current_page[0] + 1); self.update_buttons()
            await interaction.response.edit_message(embed=build_embed(current_page[0]), view=self)
        @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
        async def last_btn(self, interaction, button):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not your command!", ephemeral=True)
            current_page[0] = total_pages - 1; self.update_buttons()
            await interaction.response.edit_message(embed=build_embed(current_page[0]), view=self)

    view = PaginationView() if total_pages > 1 else discord.ui.View()
    await ctx.send(embed=build_embed(0), view=view)

@bot.command(name="inviteinfo")
async def inviteinfo(ctx, user: discord.Member = None):
    user = user or ctx.author
    try: guild_invites = await ctx.guild.invites()
    except: return await ctx.send("❌ I don't have permission to view invites.")
    user_invites = [inv for inv in guild_invites if inv.inviter and inv.inviter.id == user.id]
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name=f"Invite codes for {user.name}", icon_url=user.display_avatar.url)
    if not user_invites:
        embed.description = f"{DOT} {user.mention} has no active invite codes."
    else:
        lines = []
        for inv in user_invites:
            exp = f"<t:{int(inv.expires_at.timestamp())}:R>" if inv.expires_at else "Never"
            lines.append(f"{DOT} `{inv.code}` — **{inv.uses}** uses — Expires: {exp}")
        embed.description = "\n".join(lines)
    embed.set_footer(text=f"Today at {datetime.datetime.now().strftime('%I:%M %p')}", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="setjoinchannel")
@commands.has_permissions(manage_guild=True)
async def setjoinchannel(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await bot.db.execute("INSERT INTO guild_settings (guild_id, join_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET join_channel_id=excluded.join_channel_id",
                         (ctx.guild.id, channel.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Welcome channel set to {channel.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="unsetwelcomechannel")
@commands.has_permissions(manage_guild=True)
async def unsetwelcomechannel(ctx):
    await bot.db.execute("UPDATE guild_settings SET join_channel_id=NULL WHERE guild_id=?", (ctx.guild.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Welcome channel unset. Join messages are now **disabled**.")
    await ctx.send(embed=embed)

@bot.command(name="setleave")
@commands.has_permissions(manage_guild=True)
async def setleave(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await bot.db.execute("INSERT INTO guild_settings (guild_id, leave_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET leave_channel_id=excluded.leave_channel_id",
                         (ctx.guild.id, channel.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Leave channel set to {channel.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="unsetleavechannel")
@commands.has_permissions(manage_guild=True)
async def unsetleavechannel(ctx):
    await bot.db.execute("UPDATE guild_settings SET leave_channel_id=NULL WHERE guild_id=?", (ctx.guild.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Leave channel unset. Leave messages are now **disabled**.")
    await ctx.send(embed=embed)

@bot.command(name="addinvites")
@commands.has_permissions(administrator=True)
async def addinvites(ctx, user: discord.Member, amount: int):
    """Add invites to a user
    
    Usage: ,addinvites <user> <amount>
    Example: ,addinvites @John 5"""
    await update_user(user.id, bonus=amount)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Added **{amount}** invites to {user.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="removeinvites")
@commands.has_permissions(administrator=True)
async def removeinvites(ctx, user: discord.Member, amount: int):
    """Remove invites from a user
    
    Usage: ,removeinvites <user> <amount>
    Example: ,removeinvites @John 3"""
    await update_user(user.id, bonus=-amount)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Removed **{amount}** invites from {user.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="clearinvites")
@commands.has_permissions(administrator=True)
async def clearinvites(ctx, user: discord.Member = None):
    if user:
        await bot.db.execute("UPDATE users SET joins=0, left=0, bonus=0 WHERE user_id=?", (user.id,))
        await bot.db.commit()
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Successfully reset invites for {user.mention}.")
    else:
        await bot.db.execute("UPDATE users SET joins=0, left=0, bonus=0")
        await bot.db.commit()
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Successfully reset **all** members' invites in this guild.")
    await ctx.send(embed=embed)

@bot.command(name="resetmyinvites")
async def resetmyinvites(ctx):
    await bot.db.execute("UPDATE users SET joins=0, left=0, bonus=0 WHERE user_id=?", (ctx.author.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Your invite stats have been reset, {ctx.author.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="setaltthreshold")
@commands.has_permissions(manage_guild=True)
async def setaltthreshold(ctx, days: int):
    await bot.db.execute("INSERT INTO guild_settings (guild_id, alt_threshold) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET alt_threshold=excluded.alt_threshold",
                         (ctx.guild.id, days))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Alt threshold set to **{days} days**.")
    await ctx.send(embed=embed)

@bot.command(name="unsetaltthreshold")
@commands.has_permissions(manage_guild=True)
async def unsetaltthreshold(ctx):
    await bot.db.execute("UPDATE guild_settings SET alt_threshold=NULL WHERE guild_id=?", (ctx.guild.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Alt threshold disabled.")
    await ctx.send(embed=embed)

@bot.command(name="setinviterole")
@commands.has_permissions(manage_guild=True)
async def setinviterole(ctx, role: discord.Role, invites: int):
    """Set role reward at invite milestone
    
    Usage: ,setinviterole <role> <invites>
    Example: ,setinviterole @Gold 10"""
    await bot.db.execute("INSERT OR REPLACE INTO invite_roles (guild_id, role_id, required_invites) VALUES (?, ?, ?)",
                         (ctx.guild.id, role.id, invites))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Members will receive {role.mention} when they reach **{invites}** invites.")
    await ctx.send(embed=embed)

@bot.command(name="unsetinviterole")
@commands.has_permissions(manage_guild=True)
async def unsetinviterole(ctx, role: discord.Role):
    await bot.db.execute("DELETE FROM invite_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Invite role reward for {role.mention} removed.")
    await ctx.send(embed=embed)

@bot.command(name="viewinviteroles")
async def viewinviteroles(ctx):
    async with bot.db.execute("SELECT role_id, required_invites FROM invite_roles WHERE guild_id=? ORDER BY required_invites ASC",
                              (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title="🏆 Invite Role Rewards")
    if not rows:
        embed.description = f"{DOT} No invite role rewards configured."
    else:
        embed.description = "\n".join([f"{DOT} <@&{r[0]}> — **{r[1]}** invites required" for r in rows])
    await ctx.send(embed=embed)

@bot.command(name="setjoinmessage")
@commands.has_permissions(manage_guild=True)
async def setjoinmessage(ctx, *, message: str):
    await bot.db.execute("INSERT INTO guild_settings (guild_id, join_message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET join_message=excluded.join_message",
                         (ctx.guild.id, message))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Custom join message set!\n\n**Preview:**\n{message}")
    await ctx.send(embed=embed)

@bot.command(name="unsetjoinmessage")
@commands.has_permissions(manage_guild=True)
async def unsetjoinmessage(ctx):
    await bot.db.execute("UPDATE guild_settings SET join_message=NULL WHERE guild_id=?", (ctx.guild.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Custom join message deleted.")
    await ctx.send(embed=embed)

@bot.command(name="setleavemessage")
@commands.has_permissions(manage_guild=True)
async def setleavemessage(ctx, *, message: str):
    await bot.db.execute("INSERT INTO guild_settings (guild_id, leave_message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET leave_message=excluded.leave_message",
                         (ctx.guild.id, message))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Custom leave message set!\n\n**Preview:**\n{message}")
    await ctx.send(embed=embed)

@bot.command(name="unsetleavemessage")
@commands.has_permissions(manage_guild=True)
async def unsetleavemessage(ctx):
    await bot.db.execute("UPDATE guild_settings SET leave_message=NULL WHERE guild_id=?", (ctx.guild.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Custom leave message deleted.")
    await ctx.send(embed=embed)

@bot.command(name="setvanitymessage")
@commands.has_permissions(manage_guild=True)
async def setvanitymessage(ctx, *, message: str):
    await bot.db.execute("INSERT INTO guild_settings (guild_id, vanity_message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET vanity_message=excluded.vanity_message",
                         (ctx.guild.id, message))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Custom vanity message set!\n\n**Preview:**\n{message}")
    await ctx.send(embed=embed)

@bot.command(name="unsetvanitymessage")
@commands.has_permissions(manage_guild=True)
async def unsetvanitymessage(ctx):
    await bot.db.execute("UPDATE guild_settings SET vanity_message=NULL WHERE guild_id=?", (ctx.guild.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Custom vanity message deleted.")
    await ctx.send(embed=embed)

@bot.command(name="variables")
async def variables(ctx):
    embed = discord.Embed(color=0xffdd00, title="📋 Message Variables")
    embed.description = (
        f"{DOT} `{{user}}` — Mentions the user\n"
        f"{DOT} `{{username}}` — User's name\n"
        f"{DOT} `{{server}}` — Server name\n"
        f"{DOT} `{{membercount}}` — Total member count\n"
        f"{DOT} `{{inviter}}` — Who invited the user\n"
    )
    await ctx.send(embed=embed)

@bot.command(name="testmsg")
@commands.has_permissions(manage_guild=True)
async def testmsg(ctx, *, message: str):
    text = message.replace("{user}", ctx.author.mention)\
                  .replace("{username}", ctx.author.name)\
                  .replace("{server}", ctx.guild.name)\
                  .replace("{membercount}", str(ctx.guild.member_count))\
                  .replace("{inviter}", ctx.author.mention)
    embed = discord.Embed(color=0xffdd00, title="🧪 Message Preview")
    embed.description = text
    await ctx.send(embed=embed)

# ─── MESSAGES COMMANDS ─────────────────────────────────────────────

@bot.command(name="messages")
async def messages_cmd(ctx, user: discord.Member = None):
    user = user or ctx.author
    _, _, _, total, weekly, today, _, _, _ = await get_user_data(user.id)
    embed = discord.Embed(color=0xffdd00, title=f"{user.name}'s Messages")
    embed.description = f"**All time • {total}** messages\n**Weekly • {weekly}** messages\n**Today • {today}** messages\n\n*Updated in real-time*"
    await ctx.send(embed=embed)

@bot.command(name="m")
async def m_cmd(ctx, user: discord.Member = None):
    await messages_cmd(ctx, user)

@bot.command(name="addmessages")
@commands.has_permissions(administrator=True)
async def addmessages(ctx, user: discord.Member, amount: int):
    await update_user(user.id, total_msgs=amount)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Added **{amount}** messages to {user.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="removemessages")
@commands.has_permissions(administrator=True)
async def removemessages(ctx, user: discord.Member, amount: int):
    await update_user(user.id, total_msgs=-amount)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Removed **{amount}** messages from {user.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="blacklistchannel")
@commands.has_permissions(manage_guild=True)
async def blacklistchannel(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await bot.db.execute("INSERT OR IGNORE INTO blacklisted_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, channel.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} {channel.mention} is now blacklisted.")
    await ctx.send(embed=embed)

@bot.command(name="unblacklistchannel")
@commands.has_permissions(manage_guild=True)
async def unblacklistchannel(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await bot.db.execute("DELETE FROM blacklisted_channels WHERE guild_id=? AND channel_id=?", (ctx.guild.id, channel.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} {channel.mention} has been unblacklisted.")
    await ctx.send(embed=embed)

@bot.command(name="blacklistedchannels")
async def blacklistedchannels(ctx):
    async with bot.db.execute("SELECT channel_id FROM blacklisted_channels WHERE guild_id=?", (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title="🚫 Blacklisted Channels")
    embed.description = "\n".join([f"{DOT} <#{r[0]}>" for r in rows]) if rows else f"{DOT} No blacklisted channels."
    await ctx.send(embed=embed)

@bot.command(name="blacklistcategory")
@commands.has_permissions(manage_guild=True)
async def blacklistcategory(ctx, *, category_name: str):
    cat = discord.utils.get(ctx.guild.categories, name=category_name)
    if not cat: return await ctx.send(f"❌ Category `{category_name}` not found.")
    await bot.db.execute("INSERT OR IGNORE INTO blacklisted_categories (guild_id, category_id) VALUES (?, ?)", (ctx.guild.id, cat.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Category **{cat.name}** is now blacklisted.")
    await ctx.send(embed=embed)

@bot.command(name="unblacklistcategory")
@commands.has_permissions(manage_guild=True)
async def unblacklistcategory(ctx, *, category_name: str):
    cat = discord.utils.get(ctx.guild.categories, name=category_name)
    if not cat: return await ctx.send(f"❌ Category `{category_name}` not found.")
    await bot.db.execute("DELETE FROM blacklisted_categories WHERE guild_id=? AND category_id=?", (ctx.guild.id, cat.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Category **{cat.name}** has been unblacklisted.")
    await ctx.send(embed=embed)

@bot.command(name="blacklistedcategories")
async def blacklistedcategories(ctx):
    async with bot.db.execute("SELECT category_id FROM blacklisted_categories WHERE guild_id=?", (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title="🚫 Blacklisted Categories")
    if not rows:
        embed.description = f"{DOT} No blacklisted categories."
    else:
        lines = []
        for (cat_id,) in rows:
            cat = ctx.guild.get_channel(cat_id)
            lines.append(f"{DOT} **{cat.name if cat else f'Unknown ({cat_id})'}**")
        embed.description = "\n".join(lines)
    await ctx.send(embed=embed)

@bot.command(name="setmessagerole")
@commands.has_permissions(manage_guild=True)
async def setmessagerole(ctx, role: discord.Role, count: int):
    await bot.db.execute("INSERT OR REPLACE INTO message_roles (guild_id, role_id, required_msgs) VALUES (?, ?, ?)",
                         (ctx.guild.id, role.id, count))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Members will receive {role.mention} when they reach **{count}** messages.")
    await ctx.send(embed=embed)

@bot.command(name="unsetmessagerole")
@commands.has_permissions(manage_guild=True)
async def unsetmessagerole(ctx, role: discord.Role):
    await bot.db.execute("DELETE FROM message_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Message role reward for {role.mention} removed.")
    await ctx.send(embed=embed)

@bot.command(name="viewmessageroles")
async def viewmessageroles(ctx):
    async with bot.db.execute("SELECT role_id, required_msgs FROM message_roles WHERE guild_id=? ORDER BY required_msgs ASC",
                              (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title="📨 Message Role Rewards")
    embed.description = "\n".join([f"{DOT} <@&{r[0]}> — **{r[1]}** messages required" for r in rows]) if rows else f"{DOT} No message role rewards configured."
    await ctx.send(embed=embed)

@bot.command(name="clearmsgs")
@commands.has_permissions(administrator=True)
async def clearmsgs(ctx, user: discord.Member = None):
    if user:
        await bot.db.execute("UPDATE users SET total_msgs=0, weekly_msgs=0, today_msgs=0 WHERE user_id=?", (user.id,))
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Cleared messages for {user.mention}.")
    else:
        await bot.db.execute("UPDATE users SET total_msgs=0, weekly_msgs=0, today_msgs=0")
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Cleared **all** members' messages in this guild.")
    await bot.db.commit()
    await ctx.send(embed=embed)

@bot.command(name="resetmymessages")
async def resetmymessages(ctx):
    await bot.db.execute("UPDATE users SET total_msgs=0, weekly_msgs=0, today_msgs=0 WHERE user_id=?", (ctx.author.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Your message stats have been reset, {ctx.author.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="setresettime")
@commands.has_permissions(manage_guild=True)
async def setresettime(ctx, mode: str, *, time: str):
    """Set weekly/daily message or voice reset time. e.g. ,setresettime weeklymessage 00:00"""
    col_map = {
        "weeklymessage": "msg_weekly_reset",
        "dailymessage": "msg_daily_reset",
        "dailyvoice": "voice_daily_reset",
        "weeklyvoice": "voice_weekly_reset",
    }
    col = col_map.get(mode.lower())
    if not col: return await ctx.send(f"❌ Mode must be one of: `weeklymessage`, `dailymessage`, `dailyvoice`, `weeklyvoice`")
    await bot.db.execute(f"INSERT INTO guild_settings (guild_id, {col}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {col}=excluded.{col}",
                         (ctx.guild.id, time))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Reset time for **{mode}** set to `{time}`.")
    await ctx.send(embed=embed)

# ─── VOICE COMMANDS ────────────────────────────────────────────────

@bot.command(name="vc")
async def vc_cmd(ctx, user: discord.Member = None):
    user = user or ctx.author
    _, _, _, _, _, _, alltime, weekly, daily = await get_user_data(user.id)
    def fmt(s): return f"{s//3600}h {(s%3600)//60}m {s%60}s"
    embed = discord.Embed(color=0xffdd00, title=f"{user.name}'s Voice Stats")
    embed.description = f"**All time • {fmt(alltime)}**\n**Weekly • {fmt(weekly)}**\n**Daily • {fmt(daily)}**\n\n*Updated in real-time*"
    await ctx.send(embed=embed)

@bot.command(name="addvctime")
@commands.has_permissions(administrator=True)
async def addvctime(ctx, user: discord.Member, amount: int):
    """Add voice time in seconds to a user's all time, daily and weekly fields."""
    await update_user(user.id, voice_alltime=amount, voice_weekly=amount, voice_daily=amount)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Added **{amount}s** of voice time to {user.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="reducevctime")
@commands.has_permissions(administrator=True)
async def reducevctime(ctx, user: discord.Member, amount: int):
    """Reduce voice time from all time, daily and weekly fields."""
    await update_user(user.id, voice_alltime=-amount, voice_weekly=-amount, voice_daily=-amount)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Reduced **{amount}s** of voice time from {user.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="clearvoice")
@commands.has_permissions(administrator=True)
async def clearvoice(ctx, user: discord.Member = None):
    if user:
        await bot.db.execute("UPDATE users SET voice_alltime=0, voice_weekly=0, voice_daily=0 WHERE user_id=?", (user.id,))
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Cleared voice stats for {user.mention}.")
    else:
        await bot.db.execute("UPDATE users SET voice_alltime=0, voice_weekly=0, voice_daily=0")
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Cleared **all** members' voice stats in this guild.")
    await bot.db.commit()
    await ctx.send(embed=embed)

@bot.command(name="resetmyvoice")
async def resetmyvoice(ctx):
    await bot.db.execute("UPDATE users SET voice_alltime=0, voice_weekly=0, voice_daily=0 WHERE user_id=?", (ctx.author.id,))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Your voice stats have been reset, {ctx.author.mention}.")
    await ctx.send(embed=embed)

# ─── LEADERBOARDS ──────────────────────────────────────────────────

@bot.group(name="leaderboard", aliases=["lb"], invoke_without_command=True)
async def leaderboard(ctx):
    embed = discord.Embed(color=0xffdd00, title="📊 Leaderboard Commands")
    embed.description = (
        f"{DOT} `,leaderboard invites` — Top 10 inviters\n"
        f"{DOT} `,leaderboard messages` — Top 10 all-time messengers\n"
        f"{DOT} `,leaderboard weeklymessages` — Top 10 weekly\n"
        f"{DOT} `,leaderboard dailymessages` — Top 10 daily\n"
        f"{DOT} `,leaderboard voice` — Top 10 voice (all time)\n"
        f"{DOT} `,leaderboard weeklyvoice` — Top 10 voice (weekly)\n"
        f"{DOT} `,leaderboard dailyvoice` — Top 10 voice (daily)\n"
    )
    await ctx.send(embed=embed)

@leaderboard.command(name="invites")
async def lb_invites(ctx):
    embed = await build_lb_embed(ctx.guild, "invites")
    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=bot.user.display_avatar.url)
    await ctx.send(embed=embed)

@leaderboard.command(name="messages")
async def lb_messages(ctx):
    embed = await build_lb_embed(ctx.guild, "messages")
    await ctx.send(embed=embed)

@leaderboard.command(name="weeklymessages")
async def lb_weekly(ctx):
    embed = await build_lb_embed(ctx.guild, "weeklymessages")
    await ctx.send(embed=embed)

@leaderboard.command(name="dailymessages")
async def lb_daily(ctx):
    embed = await build_lb_embed(ctx.guild, "dailymessages")
    await ctx.send(embed=embed)

@leaderboard.command(name="voice")
async def lb_voice(ctx):
    embed = await build_lb_embed(ctx.guild, "voice")
    await ctx.send(embed=embed)

@leaderboard.command(name="weeklyvoice")
async def lb_weeklyvoice(ctx):
    embed = await build_lb_embed(ctx.guild, "weeklyvoice")
    await ctx.send(embed=embed)

@leaderboard.command(name="dailyvoice")
async def lb_dailyvoice(ctx):
    embed = await build_lb_embed(ctx.guild, "dailyvoice")
    await ctx.send(embed=embed)

# ─── AUTO ROLES ────────────────────────────────────────────────────

@bot.command(name="autorole")
@commands.has_permissions(manage_guild=True)
async def autorole(ctx):
    embed = discord.Embed(color=0xffdd00, title="Auto Roles", description="Automatically assign roles to new users\n\n**Commands**")
    embed.description += (
        f"\n<:fp_arrow:1532073102580646070> `,autorole` — Get list of all autorole commands"
        f"\n<:fp_arrow:1532073102580646070> `,setautorole` — Set autorole for humans and bots"
        f"\n<:fp_arrow:1532073102580646070> `,unsetautorole` — Delete an autorole"
        f"\n<:fp_arrow:1532073102580646070> `,configscreening` — Add role after membership screening"
        f"\n<:fp_arrow:1532073102580646070> `,viewautoroles` — Displays a guild's autoroles"
    )
    await ctx.send(embed=embed)

@bot.command(name="setautorole")
@commands.has_permissions(manage_guild=True)
async def setautorole(ctx, role: discord.Role, role_type: str = "all"):
    """Set an autorole. role_type: all, humans, bots"""
    if role_type not in ("all", "humans", "bots"):
        return await ctx.send("❌ role_type must be `all`, `humans`, or `bots`.")
    await bot.db.execute("INSERT OR REPLACE INTO autoroles (guild_id, role_id, role_type) VALUES (?, ?, ?)",
                         (ctx.guild.id, role.id, role_type))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} AutoRole set: {role.mention} for **{role_type}**.")
    await ctx.send(embed=embed)

@bot.command(name="unsetautorole")
@commands.has_permissions(manage_guild=True)
async def unsetautorole(ctx, role: discord.Role):
    await bot.db.execute("DELETE FROM autoroles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} AutoRole for {role.mention} removed.")
    await ctx.send(embed=embed)

@bot.command(name="configscreening")
@commands.has_permissions(manage_guild=True)
async def configscreening(ctx, role: discord.Role):
    """This feature will add role to users after they complete membership screening."""
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Screening role set to {role.mention}. Note: Discord API handles this natively via membership screening.")
    await ctx.send(embed=embed)

@bot.command(name="viewautoroles")
async def viewautoroles(ctx):
    async with bot.db.execute("SELECT role_id, role_type FROM autoroles WHERE guild_id=?", (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title=" 🎭 Auto Roles")
    embed.description = "\n".join([f"{DOT} <@&{r[0]}> — `{r[1]}`" for r in rows]) if rows else f"{DOT} No autoroles configured."
    await ctx.send(embed=embed)

# ─── LIVE LEADERBOARDS ─────────────────────────────────────────────

@bot.command(name="createlivelb")
@commands.has_permissions(manage_guild=True)
async def createlivelb(ctx, lb_type: str = "invites"):
    """Create a live leaderboard that updates every 30 seconds. Types: invites, messages, voice"""
    embed = await build_lb_embed(ctx.guild, lb_type)
    embed.set_footer(text=f"Live • Updates every 30 seconds")
    msg = await ctx.send(embed=embed)
    await bot.db.execute(
        "INSERT OR REPLACE INTO live_leaderboards (guild_id, channel_id, message_id, lb_type) VALUES (?, ?, ?, ?)",
        (ctx.guild.id, ctx.channel.id, msg.id, lb_type)
    )
    await bot.db.commit()
    confirm = discord.Embed(color=0xffdd00, description=f"{DOT} Live leaderboard (`{lb_type}`) created! It will update every 30 seconds.")
    await ctx.send(embed=confirm, delete_after=5)

@bot.command(name="deletelivelb")
@commands.has_permissions(manage_guild=True)
async def deletelivelb(ctx, lb_type: str = "invites"):
    await bot.db.execute("DELETE FROM live_leaderboards WHERE guild_id=? AND lb_type=?", (ctx.guild.id, lb_type))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Live leaderboard (`{lb_type}`) deleted.")
    await ctx.send(embed=embed)

@bot.command(name="showlivelbs")
async def showlivelbs(ctx):
    async with bot.db.execute("SELECT lb_type, channel_id, message_id FROM live_leaderboards WHERE guild_id=?", (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title="📊 Live Leaderboards")
    if not rows:
        embed.description = f"{DOT} No live leaderboards configured."
    else:
        lines = [f"{DOT} `{lb_type}` — <#{ch_id}> ([Jump](https://discord.com/channels/{ctx.guild.id}/{ch_id}/{msg_id}))" for lb_type, ch_id, msg_id in rows]
        embed.description = "\n".join(lines)
    await ctx.send(embed=embed)

# ─── GIVEAWAY ──────────────────────────────────────────────────────

async def resolve_giveaway(msg_id, channel_id, reroll=False):
    async with bot.db.execute("SELECT forced_winner, prize, host_id FROM giveaways WHERE msg_id = ?", (msg_id,)) as cursor:
        row = await cursor.fetchone()
    if not row and not reroll: return
    forced_id, prize, host_id = row if row else (None, "Unknown Prize", bot.user.id)
    channel = bot.get_channel(channel_id)
    try: msg = await channel.fetch_message(msg_id)
    except: return
    users = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == BLACK_TADA or (isinstance(reaction.emoji, discord.Emoji) and reaction.emoji.id == 1473964312107421697):
            async for user in reaction.users():
                if not user.bot: users.append(user)
    winner = None
    if forced_id and not reroll:
        winner = channel.guild.get_member(forced_id)
    if not winner and users:
        winner = random.choice(users)
    e = discord.Embed(
        description=f"**{GIFT} {prize} {GIFT}**\n\n{DOT} Hosted by: <@{host_id}>\n{DOT} Valid participant(s) : {len(users)}\n\n{DOT} **Winner :**\n{winner.mention if winner else 'No one'}",
        color=0xffdd00
    )
    e.set_footer(text=f"Ended • {datetime.datetime.now().strftime('%m/%d/%y, %I:%M %p')}")
    await msg.edit(content=f"{TADA_GIF} **Giveaway Ended** {TADA_GIF}", embed=e)
    if winner:
        v = discord.ui.View().add_item(discord.ui.Button(label="Giveaway Link", url=msg.jump_url))
        prefix = "New Winner!" if reroll else "Congrats,"
        await channel.send(f"{prefix} {winner.mention} you have won **{prize}**, hosted by <@{host_id}>", view=v)
    if not reroll:
        await bot.db.execute("DELETE FROM giveaways WHERE msg_id = ?", (msg_id,))
        await bot.db.commit()

@bot.command(name="gcreate")
@commands.has_permissions(administrator=True)
async def gcreate(ctx, time: str, winners: int, *, prize: str):
    """Create giveaway with requirements. Usage: ,gcreate 10m 1 Prize Name"""
    match = re.search(r'(\d+)([smhd])', time.lower())
    if not match: return await ctx.send("❌ Invalid time format. Use formats like `30s`, `5m`, `3h`, `1d`.")
    amount, unit = match.groups()
    sec = int(amount) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    end = datetime.datetime.now() + datetime.timedelta(seconds=sec)
    e = discord.Embed(
        description=f"**{GIFT} {prize} {GIFT}**\n\n{DOT} Winners: **{winners}**\n{DOT} Ends: <t:{int(end.timestamp())}:R> ( <t:{int(end.timestamp())}:F> )\n{DOT} Hosted by: {ctx.author.mention}\n\n{DOT} React with {BLACK_TADA} to participate!",
        color=0xffdd00
    )
    e.set_footer(text=f"Ends at • {end.strftime('%m/%d/%y')}")
    msg = await ctx.send(content=f"{TADA_GIF} **New Giveaway** {TADA_GIF}", embed=e)
    await msg.add_reaction(BLACK_TADA)
    await bot.db.execute("INSERT INTO giveaways (msg_id, prize, host_id) VALUES (?, ?, ?)", (msg.id, prize, ctx.author.id))
    await bot.db.commit()
    await asyncio.sleep(sec)
    await resolve_giveaway(msg.id, ctx.channel.id)

@bot.command(name="gstart")
@commands.has_permissions(administrator=True)
async def gstart(ctx, time: str, winners: int, *, prize: str):
    """Creates a giveaway. Alias for gcreate."""
    await gcreate(ctx, time, winners, prize=prize)

@bot.command(name="greroll")
@commands.has_permissions(administrator=True)
async def greroll(ctx):
    """Rerolls an ended giveaway."""
    if ctx.message.reference:
        await resolve_giveaway(ctx.message.reference.message_id, ctx.channel.id, reroll=True)
    else:
        await ctx.send("❌ Reply to a giveaway message to reroll.")

@bot.command(name="gend")
@commands.has_permissions(administrator=True)
async def gend(ctx):
    """Ends an active giveaway."""
    if ctx.message.reference:
        await resolve_giveaway(ctx.message.reference.message_id, ctx.channel.id)
    else:
        await ctx.send("❌ Reply to a giveaway message to end it.")

@bot.command(name="setgiveaway")
@commands.has_permissions(administrator=True)
async def setgiveaway(ctx):
    embed = discord.Embed(color=0xffdd00, title="🎉 Customize Giveaway Embed", description=f"{DOT} Giveaway customization via dashboard.")
    await ctx.send(embed=embed)

@bot.command(name="unsetgiveaway")
@commands.has_permissions(administrator=True)
async def unsetgiveaway(ctx):
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Premium giveaway features disabled.")
    await ctx.send(embed=embed)

@bot.command(name="viewwinnerrole")
async def viewwinnerrole(ctx):
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} No custom giveaway winner role configured.")
    await ctx.send(embed=embed)

@bot.command(name="viewbypassrole")
async def viewbypassrole(ctx):
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} No custom giveaway bypass role configured.")
    await ctx.send(embed=embed)

# Legacy aliases
@bot.command(name="gwstart")
@commands.has_permissions(administrator=True)
async def gwstart(ctx, time: str, winners: int, *, prize: str):
    await gcreate(ctx, time, winners, prize=prize)

@bot.command(name="setwin")
@commands.has_permissions(administrator=True)
async def setwin(ctx, user: discord.Member):
    await ctx.message.delete()
    if ctx.message.reference:
        await bot.db.execute("UPDATE giveaways SET forced_winner = ? WHERE msg_id = ?", (user.id, ctx.message.reference.message_id))
        await bot.db.commit()

@bot.command(name="finish")
@commands.has_permissions(administrator=True)
async def finish(ctx):
    await ctx.message.delete()
    if ctx.message.reference:
        await resolve_giveaway(ctx.message.reference.message_id, ctx.channel.id)

@bot.command(name="reroll")
@commands.has_permissions(administrator=True)
async def reroll(ctx):
    await ctx.message.delete()
    if ctx.message.reference:
        await resolve_giveaway(ctx.message.reference.message_id, ctx.channel.id, reroll=True)

# ─── TIMER ─────────────────────────────────────────────────────────

active_timers = {}

def parse_duration(time_str: str):
    total = 0
    matches = re.findall(r'(\d+(?:\.\d+)?)([smhd])', time_str.lower())
    if not matches: return None
    for amount, unit in matches:
        total += float(amount) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return int(total)

async def run_timer(guild_id: int, seconds: int):
    try:
        await asyncio.sleep(seconds)
        data = active_timers.get(guild_id)
        if not data: return
        channel = bot.get_channel(data["channel_id"])
        label = data.get("label", "Timer")
        if channel:
            embed = discord.Embed(color=0xffdd00, description=f"{DOT} ⏰ **{label}** has ended!")
            await channel.send(embed=embed)
        active_timers.pop(guild_id, None)
    except asyncio.CancelledError: pass

@bot.command(name="tstart")
@commands.has_permissions(manage_guild=True)
async def tstart(ctx, time_str: str, *, label: str = "Timer"):
    if ctx.guild.id in active_timers:
        return await ctx.send(f"❌ A timer is already running! Use `,tend` to end it first.")
    seconds = parse_duration(time_str)
    if not seconds: return await ctx.send(f"❌ Invalid format. Use `30s`, `5m`, `3h`, `1d`.")
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    task = bot.loop.create_task(run_timer(ctx.guild.id, seconds))
    active_timers[ctx.guild.id] = {"task": task, "end_time": end_time, "paused": False, "remaining": seconds, "channel_id": ctx.channel.id, "label": label}
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name="⏱️ Timer Started")
    embed.description = (f"{DOT} **Label:** {label}\n{DOT} **Duration:** `{time_str}`\n{DOT} **Ends:** <t:{int(end_time.timestamp())}:R> ( <t:{int(end_time.timestamp())}:F> )")
    await ctx.send(embed=embed)

@bot.command(name="tpause")
@commands.has_permissions(manage_guild=True)
async def tpause(ctx):
    data = active_timers.get(ctx.guild.id)
    if not data: return await ctx.send(f"❌ No active timer to pause.")
    if data["paused"]: return await ctx.send(f"❌ Timer is already paused.")
    remaining = int((data["end_time"] - datetime.datetime.now()).total_seconds())
    if remaining <= 0: return await ctx.send(f"❌ Timer has already ended.")
    data["task"].cancel(); data["paused"] = True; data["remaining"] = remaining
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name="⏸️ Timer Paused")
    embed.description = f"{DOT} **{data['label']}** paused with **{remaining}s** remaining."
    await ctx.send(embed=embed)

@bot.command(name="tresume")
@commands.has_permissions(manage_guild=True)
async def tresume(ctx):
    data = active_timers.get(ctx.guild.id)
    if not data: return await ctx.send(f"❌ No timer found.")
    if not data["paused"]: return await ctx.send(f"❌ Timer is not paused.")
    remaining = data["remaining"]
    new_end = datetime.datetime.now() + datetime.timedelta(seconds=remaining)
    task = bot.loop.create_task(run_timer(ctx.guild.id, remaining))
    data["task"] = task; data["end_time"] = new_end; data["paused"] = False
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name="▶️ Timer Resumed")
    embed.description = f"{DOT} **{data['label']}** resumed!\n{DOT} **Ends:** <t:{int(new_end.timestamp())}:R>"
    await ctx.send(embed=embed)

@bot.command(name="tend")
@commands.has_permissions(manage_guild=True)
async def tend(ctx):
    data = active_timers.pop(ctx.guild.id, None)
    if not data: return await ctx.send(f"❌ No active timer to end.")
    data["task"].cancel()
    embed = discord.Embed(color=0xffdd00)
    embed.set_author(name="⏹️ Timer Ended")
    embed.description = f"{DOT} **{data['label']}** has been ended early."
    await ctx.send(embed=embed)

# ─── GREET ─────────────────────────────────────────────────────────

@bot.command(name="setgreet")
@commands.has_permissions(manage_guild=True)
async def setgreet(ctx, mode: str = "embed", channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    async with bot.db.execute("SELECT COUNT(*) FROM greet_channels WHERE guild_id=?", (ctx.guild.id,)) as cur:
        count = (await cur.fetchone())[0]
    if count >= 3: return await ctx.send(f"❌ You can only have up to **3** greet channels.")
    if mode not in ("embed", "message"): return await ctx.send("❌ Mode must be `embed` or `message`.")
    await bot.db.execute("INSERT OR REPLACE INTO greet_channels (guild_id, channel_id, greet_type) VALUES (?, ?, ?)",
                         (ctx.guild.id, channel.id, mode))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Greet channel set to {channel.mention} (`{mode}` mode).")
    await ctx.send(embed=embed)

@bot.command(name="disablegreet")
@commands.has_permissions(manage_guild=True)
async def disablegreet(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await bot.db.execute("DELETE FROM greet_channels WHERE guild_id=? AND channel_id=?", (ctx.guild.id, channel.id))
    await bot.db.commit()
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Greet system disabled for {channel.mention}.")
    await ctx.send(embed=embed)

@bot.command(name="greetchannels")
async def greetchannels(ctx):
    async with bot.db.execute("SELECT channel_id, greet_type FROM greet_channels WHERE guild_id=?", (ctx.guild.id,)) as cur:
        rows = await cur.fetchall()
    embed = discord.Embed(color=0xffdd00, title="👋 Greet Channels")
    embed.description = "\n".join([f"{DOT} <#{r[0]}> — `{r[1]}` mode" for r in rows]) if rows else f"{DOT} No greet channels configured."
    await ctx.send(embed=embed)

@bot.command(name="greetvariables")
async def greetvariables(ctx):
    embed = discord.Embed(color=0xffdd00, title="📋 Greet Variables")
    embed.description = (
        f"{DOT} `{{user}}` — Mentions the user\n"
        f"{DOT} `{{username}}` — User's name\n"
        f"{DOT} `{{server}}` — Server name\n"
        f"{DOT} `{{membercount}}` — Total members\n"
    )
    await ctx.send(embed=embed)

# ─── MODERATION ────────────────────────────────────────────────────

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Kick a member from server
    
    Usage: ,kick <member> [reason]
    Example: ,kick @John Spam"""
    await member.kick(reason=reason)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} **{member.name}** has been kicked.\n{DOT} Reason: {reason}")
    await ctx.send(embed=embed)

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """Ban a member from server
    
    Usage: ,ban <member> [reason]
    Example: ,ban @John Toxic behavior"""
    await member.ban(reason=reason)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} **{member.name}** has been banned.\n{DOT} Reason: {reason}")
    await ctx.send(embed=embed)

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} **{user.name}** has been unbanned.")
        await ctx.send(embed=embed)
    except:
        await ctx.send("❌ User not found or not banned.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, time_str: str = "10m", *, reason: str = "No reason provided"):
    seconds = parse_duration(time_str)
    if not seconds: return await ctx.send("❌ Invalid time format.")
    until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} **{member.name}** has been muted for `{time_str}`.\n{DOT} Reason: {reason}")
    await ctx.send(embed=embed)

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} **{member.name}** has been unmuted.")
    await ctx.send(embed=embed)

@bot.command(name="erase")
@commands.has_permissions(manage_messages=True)
async def erase(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount + 1)
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Deleted **{amount}** messages.")
    await ctx.send(embed=embed, delete_after=3)

# ─── MANAGE COMMANDS ───────────────────────────────────────────────

@bot.command(name="disable")
@commands.has_permissions(manage_guild=True)
async def disable(ctx, mode: str, *, target: str):
    """Disable a command or module. Usage: ,disable command <name> | ,disable module <name>"""
    if mode == "command":
        await bot.db.execute(
            "INSERT OR IGNORE INTO disabled_commands (guild_id, command_name, channel_id) VALUES (?, ?, ?)",
            (ctx.guild.id, target.lower(), 0)
        )
        await bot.db.commit()
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Command `{target}` has been **disabled** in this server.")
    elif mode == "module":
        await bot.db.execute(
            "INSERT OR IGNORE INTO disabled_modules (guild_id, module_name, channel_id) VALUES (?, ?, ?)",
            (ctx.guild.id, target.lower(), 0)
        )
        await bot.db.commit()
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Module `{target}` has been **disabled** in this server.")
    else:
        embed = discord.Embed(color=0xffdd00, description=f"❌ Usage: `,disable command <name>` or `,disable module <name>`")
    await ctx.send(embed=embed)

@bot.command(name="enable")
@commands.has_permissions(manage_guild=True)
async def enable(ctx, mode: str, *, target: str):
    """Enable a command or module. Usage: ,enable command <name> | ,enable module <name>"""
    if mode == "command":
        await bot.db.execute("DELETE FROM disabled_commands WHERE guild_id=? AND command_name=?", (ctx.guild.id, target.lower()))
        await bot.db.commit()
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Command `{target}` has been **enabled**.")
    elif mode == "module":
        await bot.db.execute("DELETE FROM disabled_modules WHERE guild_id=? AND module_name=?", (ctx.guild.id, target.lower()))
        await bot.db.commit()
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Module `{target}` has been **enabled**.")
    else:
        embed = discord.Embed(color=0xffdd00, description=f"❌ Usage: `,enable command <name>` or `,enable module <name>`")
    await ctx.send(embed=embed)

# ─── POLLS ─────────────────────────────────────────────────────────

@bot.command(name="createpoll")
@commands.has_permissions(manage_guild=True)
async def createpoll(ctx, *, args: str):
    """Create a poll. Usage: ,createpoll Question | Option1 | Option2 | Option3"""
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 2:
        return await ctx.send("❌ Usage: `,createpoll Question | Option1 | Option2`")
    question = parts[0]
    options = parts[1:]
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    desc = "\n".join([f"{emojis[i]} {opt}" for i, opt in enumerate(options[:10])])
    embed = discord.Embed(color=0xffdd00, title=f"📊 {question}", description=desc)
    embed.set_footer(text=f"Poll by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    msg = await ctx.send(embed=embed)
    for i in range(min(len(options), 10)):
        await msg.add_reaction(emojis[i])
    import json
    await bot.db.execute(
        "INSERT INTO polls (msg_id, question, options, channel_id, active) VALUES (?, ?, ?, ?, 1)",
        (msg.id, question, json.dumps(options), ctx.channel.id)
    )
    await bot.db.commit()

@bot.command(name="epoll")
@commands.has_permissions(manage_guild=True)
async def epoll(ctx):
    """Ends an active poll. Reply to the poll message."""
    if not ctx.message.reference:
        return await ctx.send("❌ Reply to a poll message to end it.")
    msg_id = ctx.message.reference.message_id
    async with bot.db.execute("SELECT question, options, channel_id FROM polls WHERE msg_id=? AND active=1", (msg_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No active poll found.")
    import json
    question, options_json, ch_id = row
    options = json.loads(options_json)
    channel = ctx.guild.get_channel(ch_id)
    try:
        poll_msg = await channel.fetch_message(msg_id)
    except:
        return await ctx.send("❌ Could not fetch poll message.")
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    results = []
    for i, opt in enumerate(options[:10]):
        for r in poll_msg.reactions:
            if str(r.emoji) == emojis[i]:
                results.append((opt, r.count - 1))
                break
        else:
            results.append((opt, 0))
    results.sort(key=lambda x: x[1], reverse=True)
    desc = "\n".join([f"{DOT} **{opt}** — {votes} vote(s)" for opt, votes in results])
    embed = discord.Embed(color=0xffdd00, title=f"📊 Poll Ended: {question}", description=desc)
    embed.set_footer(text="Poll ended")
    await poll_msg.edit(embed=embed)
    await bot.db.execute("UPDATE polls SET active=0 WHERE msg_id=?", (msg_id,))
    await bot.db.commit()
    await ctx.send(embed=discord.Embed(color=0xffdd00, description=f"{DOT} Poll ended successfully."), delete_after=5)

# ─── UTILITY ───────────────────────────────────────────────────────

@bot.command(name="ping")
async def ping(ctx):
    embed = discord.Embed(color=0xffdd00, description=f"{DOT} Pong! **{round(bot.latency * 1000)}ms**")
    await ctx.send(embed=embed)

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    g = ctx.guild
    embed = discord.Embed(color=0xffdd00, title=g.name)
    embed.set_thumbnail(url=g.icon.url if g.icon else "")
    embed.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown", inline=True)
    embed.add_field(name="Members", value=str(g.member_count), inline=True)
    embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
    embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
    embed.add_field(name="Boosts", value=str(g.premium_subscription_count), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="userinfo")
async def userinfo(ctx, user: discord.Member = None):
    user = user or ctx.author
    embed = discord.Embed(color=0xffdd00, title=f"{user.name}#{user.discriminator}")
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=str(user.id), inline=True)
    embed.add_field(name="Status", value=get_status_emoji(user), inline=True)
    embed.add_field(name="Joined", value=f"<t:{int(user.joined_at.timestamp())}:R>" if user.joined_at else "Unknown", inline=True)
    embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="Roles", value=str(len(user.roles) - 1), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="avatar")
async def avatar(ctx, user: discord.Member = None):
    user = user or ctx.author
    embed = discord.Embed(color=0xffdd00, title=f"{user.name}'s Avatar")
    embed.set_image(url=user.display_avatar.url)
    await ctx.send(embed=embed)

# ─── PREMIUM COMMANDS ──────────────────────────────────────────────

@bot.command(name="premium")
async def premium_cmd(ctx, action: str = None, *, target: str = None):
    embed = discord.Embed(color=0xffdd00, title="Premium", description="Displays premium command usage\n\n**Commands**")
    embed.description += (
        f"\n<:fp_arrow:1532073102580646070> `,premium activate`"
        f"\n<:fp_arrow:1532073102580646070> `,premium gift`"
        f"\n<:fp_arrow:1532073102580646070> `,premium view user`"
        f"\n<:fp_arrow:1532073102580646070> `,premium view guild`"
    )
    if action == "activate":
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} To activate premium, please visit our dashboard or support server.")
    elif action == "gift":
        embed = discord.Embed(color=0xffdd00, description=f"{DOT} Use `,premium gift @user` to gift premium.")
    elif action == "view":
        if target == "user":
            async with bot.db.execute("SELECT expiry FROM premium_users WHERE user_id=?", (ctx.author.id,)) as cur:
                row = await cur.fetchone()
            if row:
                embed = discord.Embed(color=0xffdd00, description=f"{DOT} You have premium until `{row[0][:10]}`.")
            else:
                embed = discord.Embed(color=0xffdd00, description=f"{DOT} You do not have a premium subscription.")
        elif target == "guild":
            async with bot.db.execute("SELECT expiry FROM premium_guilds WHERE guild_id=?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
            if row:
                embed = discord.Embed(color=0xffdd00, description=f"{DOT} This guild has premium until `{row[0][:10]}`.")
            else:
                embed = discord.Embed(color=0xffdd00, description=f"{DOT} This guild does not have premium.")
        else:
            pass
    await ctx.send(embed=embed)

# ─── NO-PREFIX MANAGEMENT ──────────────────────────────────────────

NP_DURATIONS = [
    ("10 Minutes",  "Trial for 10 minutes",       datetime.timedelta(minutes=10),  "10m"),
    ("1 Week",      "No prefix for 1 week",       datetime.timedelta(weeks=1),     "1w"),
    ("3 Weeks",     "No prefix for 3 weeks",      datetime.timedelta(weeks=3),     "3w"),
    ("1 Month",     "No prefix for 1 month",      datetime.timedelta(days=30),     "1mo"),
    ("3 Months",    "No prefix for 3 months.",    datetime.timedelta(days=90),     "3mo"),
    ("6 Months",    "No prefix for 6 months.",    datetime.timedelta(days=180),    "6mo"),
    ("1 Year",      "No prefix for 1 year.",      datetime.timedelta(days=365),    "1y"),
    ("3 Years",     "No prefix for 3 years.",     datetime.timedelta(days=365*3),  "3y"),
    ("Lifetime",    "No prefix permanently.",     None,                            "life"),
]

class NpDurationSelect(discord.ui.Select):
    def __init__(self, target: discord.Member, invoker_id: int):
        self.target = target
        self.invoker_id = invoker_id
        options = [
            discord.SelectOption(label=label, description=desc, value=code)
            for (label, desc, _td, code) in NP_DURATIONS
        ]
        super().__init__(placeholder="Select the duration", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            return await interaction.response.send_message("Only the command invoker can use this.", ephemeral=True)
        code = self.values[0]
        match = next((d for d in NP_DURATIONS if d[3] == code), None)
        if not match:
            return await interaction.response.send_message("Invalid selection.", ephemeral=True)
        label, _desc, td, _code = match
        if td is None:
            expiry_dt = datetime.datetime(9999, 12, 31)
            human = "**Lifetime**"
        else:
            expiry_dt = datetime.datetime.now() + td
            human = f"**{label}** (until <t:{int(expiry_dt.timestamp())}:F>)"
        await bot.db.execute(
            "INSERT OR REPLACE INTO noprefix (user_id, expiry) VALUES (?, ?)",
            (self.target.id, expiry_dt.isoformat())
        )
        await bot.db.commit()
        embed = discord.Embed(
            color=0xffdd00,
            description=f"{DOT} Added {self.target.mention} to **No-Prefix** for {human}."
        )
        for child in self.view.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self.view)

class NpDurationView(discord.ui.View):
    def __init__(self, target: discord.Member, invoker_id: int):
        super().__init__(timeout=120)
        self.add_item(NpDurationSelect(target, invoker_id))

@bot.command(name="np")
async def noprefix_cmd(ctx, action: str = None, *, rest: str = None):
    if not (await is_bot_owner(ctx.author.id) or await is_bot_staff(ctx.author.id)):
        return
    action = (action or "").lower()

    # ── ADD: ,np add @user  →  duration dropdown ──
    if action == "add":
        user = None
        if ctx.message.mentions:
            user = ctx.message.mentions[0]
        elif rest:
            try:
                user = await commands.MemberConverter().convert(ctx, rest.strip().split()[0])
            except Exception:
                user = None
        if not user:
            return await ctx.send(embed=discord.Embed(
                color=0xffdd00,
                description=f"{DOT} Usage: `,np add @user`"
            ))
        embed = discord.Embed(
            color=0xffdd00,
            title="Select No Prefix Duration",
            description=f"Choose the duration for how long no-prefix should be enabled for {user.mention}:"
        )
        view = NpDurationView(user, ctx.author.id)
        await ctx.send(embed=embed, view=view)
        return

    # ── REMOVE: ,np remove @user ──
    if action == "remove":
        user = None
        if ctx.message.mentions:
            user = ctx.message.mentions[0]
        elif rest:
            try:
                user = await commands.MemberConverter().convert(ctx, rest.strip().split()[0])
            except Exception:
                user = None
        if not user:
            return await ctx.send(embed=discord.Embed(
                color=0xffdd00, description=f"{DOT} Usage: `,np remove @user`"
            ))
        await bot.db.execute("DELETE FROM noprefix WHERE user_id = ?", (user.id,))
        await bot.db.commit()
        await ctx.send(embed=discord.Embed(
            color=0xffdd00, description=f"{DOT} Removed {user.mention} from **No-Prefix**."
        ))
        return

    # ── LIST: ,np list ──
    if action == "list":
        async with bot.db.execute("SELECT user_id, expiry FROM noprefix") as cursor:
            rows = await cursor.fetchall()
        if not rows:
            return await ctx.send(embed=discord.Embed(
                color=0xffdd00, description=f"{DOT} No no-prefix users found."
            ))
        lines = []
        for uid, expiry in rows:
            try:
                exp_dt = datetime.datetime.fromisoformat(expiry)
                if exp_dt.year >= 9999:
                    when = "Lifetime"
                else:
                    when = f"<t:{int(exp_dt.timestamp())}:R>"
            except Exception:
                when = expiry[:10]
            lines.append(f"• <@{uid}> — {when}")
        embed = discord.Embed(
            color=0xffdd00,
            title="No-Prefix Users",
            description="\n".join(lines)
        )
        return await ctx.send(embed=embed)

    # ── CHECK: ,np check @user ──
    if action == "check":
        user = None
        if ctx.message.mentions:
            user = ctx.message.mentions[0]
        elif rest:
            try:
                user = await commands.MemberConverter().convert(ctx, rest.strip().split()[0])
            except Exception:
                user = None
        if not user:
            return await ctx.send(embed=discord.Embed(
                color=0xffdd00, description=f"{DOT} Usage: `,np check @user`"
            ))
        async with bot.db.execute("SELECT expiry FROM noprefix WHERE user_id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return await ctx.send(embed=discord.Embed(
                color=0xffdd00, description=f"{DOT} {user.mention} does not have no-prefix."
            ))
        try:
            exp_dt = datetime.datetime.fromisoformat(row[0])
            if exp_dt.year >= 9999:
                when = "**Lifetime**"
            elif exp_dt < datetime.datetime.now():
                when = "expired"
            else:
                when = f"<t:{int(exp_dt.timestamp())}:F> (<t:{int(exp_dt.timestamp())}:R>)"
        except Exception:
            when = row[0]
        return await ctx.send(embed=discord.Embed(
            color=0xffdd00, description=f"{DOT} {user.mention} no-prefix: {when}"
        ))

    # ── HELP / fallback ──
    embed = discord.Embed(
        color=0xffdd00,
        title="Np Add Command",
        description=(
            "Add user to no-prefix with time options\n\n"
            "**Alt cmd**\nNo Alt cmd\n\n"
            "**Usage**\n`<user>`\n\n"
            "<[] = optional | <> = required • Use Prefix Before Commands."
        )
    )
    embed.add_field(
        name="Subcommands",
        value="`,np add @user`\n`,np remove @user`\n`,np check @user`\n`,np list`",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="bonus")
@commands.has_permissions(administrator=True)
async def bonus(ctx, user: discord.Member, amount: int):
    await update_user(user.id, bonus=amount)

# ─── HELP COMMAND (1:1 Dropdown Clone) ────────────────────────────

HELP_SECTIONS = {
    "premium": {
        "emoji": E_PREMIUM,
        "label": "Premium utility",
        "title": "Premium",
        "description": "Displays premium command usage",
        "commands": [
            (",premium activate", None),
            (",premium gift", None),
            (",premium view user", None),
            (",premium view guild", None),
        ]
    },
    "invites": {
        "emoji": E_INVITE,
        "label": "Invite tracking",
        "title": "Invite logger/ Invite tracker",
        "description": "Tracks server invites",
        "commands": [
            (",invites", "Displays the invites stats of a user in this guild"),
            (",inviter", "Displays the inviter of a server member"),
            (",invited", "Displays the invited list of a member"),
            (",inviteinfo", "Displays the active invite code(s) of a user in this guild"),
            (",setjoinchannel", "Set the welcome channel! All invites welcome message will appear there"),
            (",addinvites", "Adds a number of invites to a user !"),
            (",removeinvites", "Removes a number of invites from a user !"),
            (",unsetwelcomechannel", "Unset the welcome channel! Note that this command will disable the welcome messages"),
            (",setleave", "Sets the member leave channel"),
            (",unsetleavechannel", "Unsets the member leave channel! Note that this will disable member leave messages"),
            (",setaltthreshold", "Customize fake invites count duration"),
            (",unsetaltthreshold", "Disable custom alt threshold"),
            (",setinviterole", "Setup invite role reward, the bot will give roles to inviters when reaching specified invites count"),
            (",unsetinviterole", "Remove your customized invite role configuration"),
            (",viewinviteroles", "View you customized invite role configuration"),
            (",clearinvites", "Resets everyone's invites or a user's invites statistics in this guild"),
            (",resetmyinvites", "Clears your own invites in this guild (no permissions required)"),
            (",setjoinmessage", "Set a custom join message"),
            (",setleavemessage", "Set a custom leave message"),
            (",setvanitymessage", "Set a custom vanity join message"),
            (",unsetjoinmessage", "Deletes your custom join message"),
            (",unsetleavemessage", "Deletes your custom leave message"),
            (",unsetvanitymessage", "Deletes your custom vanity message"),
            (",variables", "Displays the variables so that you can use them in custom welcome message"),
            (",testmsg", "Displays your custom join message which you enter as an argument!"),
            (",leaderboard invites", "Displays the top 10 inviters in this guild"),
        ]
    },
    "messages": {
        "emoji": E_MSG,
        "label": "Messages",
        "title": "Messages",
        "description": "Tracks user message counts",
        "commands": [
            (",messages", "Displays the number of messages sent by you or a user"),
            (",addmessages", "Adds the specified number of messages to a user"),
            (",removemessages", "Removes the specified number of messages to a user"),
            (",blacklistchannel", "Blacklists a channel , I wont count messages from that channel"),
            (",unblacklistchannel", "Unblacklists a channel"),
            (",blacklistedchannels", "Displays the blacklisted channels of a guild"),
            (",blacklistcategory", "Blacklists a category, I wont count messages sent in that category"),
            (",unblacklistcategory", "Unblacklists a category"),
            (",blacklistedcategories", "Displays the blacklisted categories of a guild"),
            (",setmessagerole", "Setup messages role, the bot will give roles to members when reaching specified messages count"),
            (",unsetmessagerole", "Remove your customized message role configuration"),
            (",viewmessageroles", "View you customized message role configuration"),
            (",clearmsgs", "Resets everyone's messages or a user's messages in this guild"),
            (",resetmymessages", "Resets your own messages that you sent in this guild (no permissions required)"),
            (",setresettime weeklymessage", "Customize your weekly messages reset time"),
            (",setresettime dailymessage", "Customize your daily messages reset time"),
            (",leaderboard weeklymessages", "Displays the top 10 active messengers in this guild"),
            (",leaderboard messages", "Displays the top 10 messengers in this guild"),
            (",leaderboard dailymessages", "Displays the top 10 active messengers in this guild"),
        ]
    },
    "voice": {
        "emoji": E_VOICE,
        "label": "Voice",
        "title": "Voice state tracking",
        "description": "Logs voice channel durations",
        "commands": [
            (",vc", "Displays the voice state stats of a user"),
            (",addvctime", "Add voice time to All time, daily and weekly fields of a user"),
            (",reducevctime", "Reduce voice time from All time, daily and weekly fields to a user"),
            (",clearvoice", "Resets everyone's voice state stats or a user's voice state stats in this guild"),
            (",resetmyvoice", "Resets your own voice state record in this guild (no permissions required)"),
            (",setresettime dailyvoice", "Customize your daily voice state reset time"),
            (",setresettime weeklyvoice", "Customize your weekly voice state reset time"),
            (",leaderboard weeklyvoice", "Displays the top 10 voice state members in this guild"),
            (",leaderboard voice", "Displays the top 10 voice state members in this guild"),
            (",leaderboard dailyvoice", "Displays the top 10 voice state members in this guild"),
        ]
    },
    "autoroles": {
        "emoji": "<:fp_premium:1532074078264103063>",
        "label": "Auto Roles",
        "title": "Auto Roles",
        "description": "Automatically assign roles to new users",
        "commands_with_header": True,
        "commands": [
            (",autorole", "Get list of all autorole commands"),
            (",setautorole", "Set autorole for humans and bots"),
            (",unsetautorole", "Delete an autorole"),
            (",configscreening", "This feature will add role to users after they complete membership screening"),
            (",viewautoroles", "Displays a guild's autoroles"),
        ]
    },
    "liveleaderboards": {
        "emoji": E_LB,
        "label": "Live Leaderboards",
        "title": "Live leaderboards",
        "description": None,
        "commands": [
            (",createlivelb", "Create a live leaderboard of invites, messages, voice updated every 30 seconds"),
            (",deletelivelb", "Delete a live leaderboard"),
            (",showlivelbs", "Shows the live leaderboards information of your server"),
        ]
    },
    "giveaway": {
        "emoji": E_GW,
        "label": "Giveaways",
        "title": "Giveaway",
        "description": "Create giveaways",
        "commands_with_header": True,
        "commands": [
            (",gcreate", "Create giveaways with requirements"),
            (",gstart", "Creates a giveaway"),
            (",greroll", "Rerolls an ended giveaway"),
            (",gend", "Ends an active giveaway"),
            (",setgiveaway", "customize giveaway embed"),
            (",unsetgiveaway", "Disable premium giveaway features"),
            (",viewwinnerrole", "Shows your custom giveaway winner role"),
            (",viewbypassrole", "Shows your custom giveaway bypass role"),
        ]
    },
    "timer": {
        "emoji": E_TIMER,
        "label": "Timer",
        "title": "Timer",
        "description": None,
        "commands": [
            (",tstart <time> [label]", "Start a timer (30s, 5m, 3h, 1d)"),
            (",tpause", "Pause the active timer"),
            (",tresume", "Resume a paused timer"),
            (",tend", "End the active timer early"),
        ]
    },
    "greet": {
        "emoji": E_GREET,
        "label": "Greet",
        "title": "Set greet message",
        "description": "Welcome new users in up to 3 channels",
        "commands_with_header": True,
        "commands": [
            (",setgreet", "Greet configuration commands"),
            (",setgreet embed", "Sets a greet to welcome new members"),
            (",setgreet message", "Sets a greet to welcome new members"),
            (",disablegreet", "Disables the greet welcome system of a channel"),
            (",greetchannels", "Displays the total channels set for greet welcome system"),
            (",greetvariables", "Displays the variables that you can use them in greet welcome message"),
        ]
    },
    "moderation": {
        "emoji": E_MOD,
        "label": "Moderation",
        "title": "Moderation",
        "description": None,
        "commands": [
            (",kick", "Kicks a user from a guild"),
            (",erase", "Delete a number of messages from a channel"),
            (",ban", "Bans a user from a guild"),
            (",unban", "Unbans a banned user from a Discord server"),
            (",mute", "Mutes a server member for a specified amount of time"),
            (",unmute", "Unmutes a server member"),
        ]
    },
    "managecommands": {
        "emoji": E_MANAGE,
        "label": "Manage Commands",
        "title": "Manage Commands",
        "description": None,
        "commands": [
            (",disable command", "Disables a specific command"),
            (",disable module", "Disable a module in a channel or in the server"),
            (",enable module", "Remove module from the blacklist"),
            (",enable command", "Remove command from the blacklist"),
        ]
    },
    "poll": {
        "emoji": E_POLL,
        "label": "Poll",
        "title": "Polls",
        "description": "Creates a poll",
        "commands_with_header": True,
        "commands": [
            (",createpoll", "Create a poll"),
            (",epoll", "Ends an active poll"),
        ]
    },
    "utility": {
        "emoji": E_UTILITY,
        "label": "Utility",
        "title": "Utility",
        "description": None,
        "commands": [
            (",ping", "Check bot latency"),
            (",serverinfo", "Displays server information"),
            (",userinfo", "Displays user information"),
            (",avatar", "Displays a user's avatar"),
        ]
    },
    "credits": {
        "emoji": E_CONTACT,
        "label": "Credits",
        "title": "Credits",
        "description": None,
        "contact": True,
    },
}

def build_main_help_embed(custom_emojis=None):
    # Map section index -> emoji (custom takes precedence, else section default)
    keys = list(HELP_SECTIONS.keys())
    def em(i):
        if custom_emojis and i < len(custom_emojis) and custom_emojis[i]:
            return custom_emojis[i]
        return HELP_SECTIONS[keys[i]]["emoji"]
    embed = discord.Embed(color=0xffdd00)
    embed.description = (
        f"Hey there, my prefix is `,`\n\n"
        f"{E_NEWS} **News:**\n"
        f"> <:fp_arrow:1532073102580646070> Access the new Falcon Premium Dashboard to configure your server!\n"
        f"> <:fp_arrow:1532073102580646070> Upgrade your Discord server with Falcon Premium now to enjoy feature rich Discord bot!\n\n"
        f"I can do invite tracking, message tracking, voice state tracking, can manage your server events with giveaways, greet system ,timers, polls and much more! "
        f"You can checkout my other commands in the context menu!\n\n"
        f"{em(0)} • **Premium utility**\n"
        f"{em(1)} • **Invite tracking**\n"
        f"{em(2)} • **Messages**\n"
        f"{em(3)} • **Voice**\n"
        f"{em(4)} • **Auto Roles**\n"
        f"{em(5)} • **Live Leaderboards**\n"
        f"{em(6)} • **Giveaways**\n"
        f"{em(7)} • **Timer**\n"
        f"{em(8)} • **Greet**\n"
        f"{em(9)} • **Moderation**\n"
        f"{em(10)} • **Manage Commands**\n"
        f"{em(11)} • **Poll**\n"
        f"{em(12)} • **Utility**\n"
        f"{em(13)} • **Credits**"
    )
    return embed

def build_section_embed(section_key: str):
    s = HELP_SECTIONS[section_key]
    embed = discord.Embed(color=0xffdd00)
    embed.title = s["title"]

    if s.get("contact"):
        embed.description = (
            f"<:fp_arrow:1532073102580646070> **Support server:** [Join here](https://discord.gg/winterlove)\n"
            f"<:fp_arrow:1532073102580646070> **Owner:** <@1360160381754015825>\n"
            f"<:fp_arrow:1532073102580646070> **Owner ID:** `1360160381754015825`"
        )
        return embed

    if s.get("description"):
        embed.description = s["description"] + "\n"
    else:
        embed.description = ""

    has_header = s.get("commands_with_header", False)
    if has_header:
        embed.description += "\n**Commands**"

    lines = []
    for item in s["commands"]:
        if isinstance(item, tuple):
            cmd, desc = item
        else:
            cmd, desc = item, None
        if desc:
            lines.append(f"<:fp_arrow:1532073102580646070> `{cmd}` - {desc}")
        else:
            lines.append(f"<:fp_arrow:1532073102580646070> `{cmd}`")

    embed.description += "\n" + "\n".join(lines)
    return embed

class HelpDropdown(discord.ui.Select):
    def __init__(self, custom_emojis=None):
        options = [
            discord.SelectOption(label="Select a category...", value="main", default=True),
        ]
        keys = list(HELP_SECTIONS.keys())
        for i, key in enumerate(keys):
            data = HELP_SECTIONS[key]
            emoji_str = data["emoji"]
            if custom_emojis and i < len(custom_emojis) and custom_emojis[i]:
                emoji_str = custom_emojis[i]
            emoji_obj = None
            try:
                emoji_obj = discord.PartialEmoji.from_str(emoji_str)
            except Exception:
                emoji_obj = None
            try:
                options.append(discord.SelectOption(label=data["label"], value=key, emoji=emoji_obj or emoji_str))
            except Exception:
                options.append(discord.SelectOption(label=data["label"], value=key))
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        gid = interaction.guild.id if interaction.guild else None
        custom = await get_guild_dropdown_emojis(gid)
        if val == "main":
            embed = build_main_help_embed(custom_emojis=custom)
        else:
            embed = build_section_embed(val)
        for opt in self.options:
            opt.default = (opt.value == val)
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, custom_emojis=None):
        super().__init__(timeout=120)
        self.add_item(HelpDropdown(custom_emojis=custom_emojis))
        
        # Add URL buttons
        self.add_item(discord.ui.Button(label="Go to Dashboard", url="https://premium.falconbot.xyz", style=discord.ButtonStyle.url))
        self.add_item(discord.ui.Button(label="Terms of service", url="https://tos.falconbot.xyz", style=discord.ButtonStyle.url))
        self.add_item(discord.ui.Button(label="Privacy Policy", url="https://privacy.falconbot.xyz", style=discord.ButtonStyle.url))
        self.add_item(discord.ui.Button(label="Invite me", url="https://discord.com/oauth2/authorize?client_id=1532062484041826314&permissions=8&integration_type=0&scope=bot", style=discord.ButtonStyle.url))
        self.add_item(discord.ui.Button(label="Support server", url="https://discord.gg/45P9GscbCf", style=discord.ButtonStyle.url))
        self.add_item(discord.ui.Button(label="Vote me", url="https://top.gg/bot/899899858981371935", style=discord.ButtonStyle.url))

@bot.command(name="help")
async def help_cmd(ctx):
    embed = build_main_help_embed(custom_emojis=None)
    view = HelpView(custom_emojis=None)
    await ctx.send(embed=embed, view=view)

@bot.command(name="credits")
async def credits_cmd(ctx):
    custom = await get_guild_dropdown_emojis(ctx.guild.id if ctx.guild else None)
    embed = build_section_embed("credits")
    view = HelpView(custom_emojis=custom)
    for opt in view.children[0].options:
        opt.default = (opt.value == "credits")
    await ctx.send(embed=embed, view=view)

@bot.hybrid_command(name="refreshemojis", description="(Owner) Use this server's emojis in the help dropdown")
async def refresh_emojis(ctx):
    if not await is_bot_owner(ctx.author.id):
        return
    if not ctx.guild:
        return await ctx.send(f"{DOT} Run this inside a server.")
    ok = await store_guild_dropdown_emojis(ctx.guild)
    if ok:
        await ctx.send(f"{DOT} Dropdown emojis updated using **{ctx.guild.name}**'s emojis. Try `,help`.")
    else:
        await ctx.send(f"{DOT} This server has no custom emojis to use.")

@bot.hybrid_command(name="resetemojis", description="(Owner) Reset help dropdown emojis to defaults")
async def reset_emojis(ctx):
    if not await is_bot_owner(ctx.author.id):
        return
    if not ctx.guild:
        return
    await bot.db.execute("DELETE FROM guild_help_emojis WHERE guild_id = ?", (ctx.guild.id,))
    await bot.db.commit()
    await ctx.send(f"{DOT} Dropdown emojis reset to defaults.")

# ─── Owner / Staff Management ──────────────────────────────────────
@bot.hybrid_command(name="setowner", description="(Primary owner) Promote a user to bot owner")
async def setowner_cmd(ctx, user: discord.User):
    if ctx.author.id != PRIMARY_OWNER_ID:
        return await ctx.send(f"{DOT} Only the primary owner can do that.")
    if user.id == PRIMARY_OWNER_ID:
        return await ctx.send(f"{DOT} That user is already the primary owner.")
    await bot.db.execute("INSERT OR IGNORE INTO bot_owners (user_id) VALUES (?)", (user.id,))
    await bot.db.commit()
    await ctx.send(f"{DOT} **{user}** is now a bot owner.")

@bot.hybrid_command(name="unsetowner", description="(Primary owner) Remove an owner")
async def unsetowner_cmd(ctx, user: discord.User):
    if ctx.author.id not in PRIMARY_OWNER_IDS:
        return await ctx.send(f"{DOT} Only a primary owner can do that.")
    if user.id in PRIMARY_OWNER_IDS:
        return await ctx.send(f"{DOT} A primary owner cannot be removed.")
    await bot.db.execute("DELETE FROM bot_owners WHERE user_id = ?", (user.id,))
    await bot.db.commit()
    await ctx.send(f"{DOT} **{user}** is no longer a bot owner.")

@bot.hybrid_command(name="owners", description="List all bot owners")
async def owners_cmd(ctx):
    async with bot.db.execute("SELECT user_id FROM bot_owners") as cur:
        rows = await cur.fetchall()
    lines = [f"<:fp_arrow:1532073102580646070> <@{oid}> — `{oid}` (Primary)" for oid in PRIMARY_OWNER_IDS]
    for (uid,) in rows:
        if uid in PRIMARY_OWNER_IDS: continue
        lines.append(f"<:fp_arrow:1532073102580646070> <@{uid}> — `{uid}`")
    embed = discord.Embed(color=0xffdd00, title="Bot Owners", description="\n".join(lines))
    await ctx.send(embed=embed)

@bot.hybrid_command(name="setstaff", description="(Owner) Promote a user to bot staff")
async def setstaff_cmd(ctx, user: discord.User):
    if not await is_bot_owner(ctx.author.id):
        return await ctx.send(f"{DOT} Owner only.")
    await bot.db.execute("INSERT OR IGNORE INTO bot_staff (user_id) VALUES (?)", (user.id,))
    await bot.db.commit()
    await ctx.send(f"{DOT} **{user}** is now bot staff.")

@bot.hybrid_command(name="unsetstaff", description="(Owner) Remove a staff member")
async def unsetstaff_cmd(ctx, user: discord.User):
    if not await is_bot_owner(ctx.author.id):
        return await ctx.send(f"{DOT} Owner only.")
    await bot.db.execute("DELETE FROM bot_staff WHERE user_id = ?", (user.id,))
    await bot.db.commit()
    await ctx.send(f"{DOT} **{user}** is no longer bot staff.")

@bot.hybrid_command(name="staff", description="List all bot staff")
async def staff_cmd(ctx):
    async with bot.db.execute("SELECT user_id FROM bot_staff") as cur:
        rows = await cur.fetchall()
    if not rows:
        desc = f"{DOT} No staff members."
    else:
        desc = "\n".join([f"<:fp_arrow:1532073102580646070> <@{uid}> — `{uid}`" for (uid,) in rows])
    embed = discord.Embed(color=0xffdd00, title="Bot Staff", description=desc)
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
# ─── ABOUT ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
@bot.hybrid_command(name="about", description="About Falcon")
async def about_cmd(ctx):
    async with bot.db.execute("SELECT user_id FROM bot_owners") as cur:
        extra_owners = [r[0] for r in await cur.fetchall() if r[0] not in PRIMARY_OWNER_IDS]
    async with bot.db.execute("SELECT user_id FROM bot_staff") as cur:
        staff = [r[0] for r in await cur.fetchall()]

    primary_lines = "\n".join([f"<:fp_arrow:1532073102580646070> <@{oid}> (`{oid}`)" for oid in PRIMARY_OWNER_IDS])
    owner_lines = "\n".join([f"<:fp_arrow:1532073102580646070> <@{oid}>" for oid in extra_owners]) if extra_owners else f"{DOT} *(none)*"
    staff_lines = "\n".join([f"<:fp_arrow:1532073102580646070> <@{sid}>" for sid in staff]) if staff else f"{DOT} *(none)*"

    embed = discord.Embed(color=0xffdd00, title="About Falcon Premium")
    embed.description = (
        f"A multipurpose Discord bot featuring moderation, automod, anti-nuke, anti-raid, "
        f"music, crypto tools, utility commands, and more.\n"
    )
    embed.add_field(name="Primary Owners", value=primary_lines, inline=False)
    embed.add_field(name="Owners", value=owner_lines, inline=False)
    embed.add_field(name="Staff", value=staff_lines, inline=False)
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Users", value=str(sum(g.member_count or 0 for g in bot.guilds)), inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency*1000)} ms", inline=True)
    embed.set_footer(text="Falcon Premium • Multi-purpose")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
# ─── INVITE ────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
@bot.hybrid_command(name="invite", description="Get Falcon Premium invite links")
async def invite_cmd(ctx):
    embed = discord.Embed(
        color=0xffdd00,
        title="Falcon Premium bot Invite",
        description="Invite Falcon Premium by clicking on this link:\nWith sufficient permissions [Click here to invite](https://discord.com/oauth2/authorize?client_id=1532062484041826314&permissions=268823806&scope=bot%20applications.commands)\n\nInvite Falcon Premium by clicking on this link:\nWith admin permissions [Click here to invite](https://discord.com/oauth2/authorize?client_id=1532062484041826314&permissions=8&scope=bot%20applications.commands)"
    )
    embed.set_footer(text=f"Requested by - {ctx.author}")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
# ─── CUSTOMIZATION (Owner only): ,c a <url>  ,c b <url> ────────────
# ═══════════════════════════════════════════════════════════════════
@bot.command(name="c")
async def customize_cmd(ctx, action: str = None, *, url: str = None):
    if not await is_bot_owner(ctx.author.id):
        return
    if not action:
        return await ctx.send(embed=discord.Embed(
            color=0xffdd00,
            description=(f"{DOT} Customization\n"
                         f"<:fp_arrow:1532073102580646070> `,c a <url|attachment>` — change bot avatar\n"
                         f"<:fp_arrow:1532073102580646070> `,c b <url|attachment>` — change bot banner")
        ))
    action = action.lower()
    if action not in ("a", "avatar", "b", "banner"):
        return await ctx.send(f"{DOT} Use `a` (avatar) or `b` (banner).")
    # Get image bytes from URL or attachment
    img_url = url
    if not img_url and ctx.message.attachments:
        img_url = ctx.message.attachments[0].url
    if not img_url:
        return await ctx.send(f"{DOT} Provide an image URL or attach an image.")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as resp:
                if resp.status != 200:
                    return await ctx.send(f"{DOT} Failed to download image (HTTP {resp.status}).")
                data = await resp.read()
        if action in ("a", "avatar"):
            await bot.user.edit(avatar=data)
            kind = "avatar"
        else:
            await bot.user.edit(banner=data)
            kind = "banner"
        await ctx.send(embed=discord.Embed(
            color=0xffdd00, description=f"{DOT} Bot {kind} updated successfully."
        ))
    except discord.HTTPException as e:
        await ctx.send(f"{DOT} Discord error: {e}")
    except Exception as e:
        await ctx.send(f"{DOT} Error: {e}")

# ═══════════════════════════════════════════════════════════════════
# ─── EMOJI STEAL / INFO ────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
EMOJI_RE = re.compile(r"<(a)?:(\w+):(\d+)>")

@bot.command(name="emoji", aliases=["steal", "einfo"])
async def emoji_cmd(ctx, *, arg: str = None):
    if not arg and not ctx.message.attachments:
        return await ctx.send(f"{DOT} Send an emoji: `,emoji <emoji>`")
    target = arg or ""
    m = EMOJI_RE.search(target)
    if m:
        animated = m.group(1) == "a"
        name = m.group(2)
        eid = m.group(3)
        ext = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{eid}.{ext}?size=512&quality=lossless"
        embed = discord.Embed(color=0xffdd00, title=f":{name}:")
        embed.add_field(name="Name", value=f"`{name}`", inline=True)
        embed.add_field(name="ID",   value=f"`{eid}`",  inline=True)
        embed.add_field(name="Animated", value="Yes" if animated else "No", inline=True)
        embed.add_field(name="URL", value=f"[Click]({url})", inline=False)
        embed.set_image(url=url)
        return await ctx.send(embed=embed)
    # Plain unicode emoji or unknown
    embed = discord.Embed(color=0xffdd00, title="Emoji Info")
    embed.description = (
        f"{DOT} Raw: `{target}`\n"
        f"{DOT} Codepoints: `{' '.join(f'U+{ord(c):04X}' for c in target if c.strip())}`"
    )
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════
# ─── BOT-WIDE USER BLACKLIST (Staff+) ──────────────────────────────
# ═══════════════════════════════════════════════════════════════════
@bot.command(name="blacklist", aliases=["bl"])
async def blacklist_user_cmd(ctx, action: str = None, *, rest: str = None):
    if not await is_bot_staff(ctx.author.id):
        return
    action = (action or "").lower()
    if action == "add":
        user = ctx.message.mentions[0] if ctx.message.mentions else None
        if not user:
            return await ctx.send(f"{DOT} Usage: `,blacklist add @user [reason]`")
        if user.id in PRIMARY_OWNER_IDS:
            return await ctx.send(f"{DOT} Cannot blacklist a primary owner.")
        reason = (rest or "").split(maxsplit=1)
        reason = reason[1] if len(reason) > 1 else "No reason"
        await bot.db.execute(
            "INSERT OR REPLACE INTO user_blacklist (user_id, reason, by_user, at) VALUES (?, ?, ?, ?)",
            (user.id, reason, ctx.author.id, datetime.datetime.now().isoformat())
        )
        await bot.db.commit()
        await ctx.send(embed=discord.Embed(
            color=0xffdd00,
            description=f"{DOT} {user.mention} has been **blacklisted** from the bot.\n<:fp_arrow:1532073102580646070> Reason: {reason}"
        ))
    elif action == "remove":
        user = ctx.message.mentions[0] if ctx.message.mentions else None
        if not user:
            return await ctx.send(f"{DOT} Usage: `,blacklist remove @user`")
        await bot.db.execute("DELETE FROM user_blacklist WHERE user_id = ?", (user.id,))
        await bot.db.commit()
        await ctx.send(embed=discord.Embed(
            color=0xffdd00, description=f"{DOT} {user.mention} has been removed from the blacklist."
        ))
    elif action == "list":
        async with bot.db.execute("SELECT user_id, reason FROM user_blacklist") as cur:
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(f"{DOT} No blacklisted users.")
        desc = "\n".join([f"<:fp_arrow:1532073102580646070> <@{uid}> — {reason}" for uid, reason in rows])
        await ctx.send(embed=discord.Embed(color=0xffdd00, title="Bot Blacklist", description=desc))
    else:
        await ctx.send(embed=discord.Embed(
            color=0xffdd00,
            description=f"{DOT} Usage:\n<:fp_arrow:1532073102580646070> `,blacklist add @user [reason]`\n<:fp_arrow:1532073102580646070> `,blacklist remove @user`\n<:fp_arrow:1532073102580646070> `,blacklist list`"
        ))

# ═══════════════════════════════════════════════════════════════════
# ─── PREMIUM ADD/REMOVE (Owner) ────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
@bot.command(name="premiumadd", aliases=["padd"])
async def premium_add_cmd(ctx, user: discord.Member = None, days: int = 30):
    if not await is_bot_owner(ctx.author.id):
        return
    if not user:
        return await ctx.send(f"{DOT} Usage: `,premiumadd @user [days=30]`")
    expiry = datetime.datetime.now() + datetime.timedelta(days=days)
    await bot.db.execute(
        "INSERT OR REPLACE INTO premium_users (user_id, expiry) VALUES (?, ?)",
        (user.id, expiry.isoformat())
    )
    await bot.db.commit()
    await ctx.send(embed=discord.Embed(
        color=0xffdd00,
        description=f"{DOT} {user.mention} now has **Premium** for **{days} days** (until <t:{int(expiry.timestamp())}:F>)."
    ))

@bot.command(name="premiumremove", aliases=["premrm"])
async def premium_remove_cmd(ctx, user: discord.Member = None):
    if not await is_bot_owner(ctx.author.id):
        return
    if not user:
        return await ctx.send(f"{DOT} Usage: `,premiumremove @user`")
    await bot.db.execute("DELETE FROM premium_users WHERE user_id = ?", (user.id,))
    await bot.db.commit()
    await ctx.send(embed=discord.Embed(
        color=0xffdd00, description=f"{DOT} Removed Premium from {user.mention}."
    ))

# ═══════════════════════════════════════════════════════════════════
# ─── AUTOMOD (anti-link / anti-invite) ─────────────────────────────
# ═══════════════════════════════════════════════════════════════════
INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+", re.I)
LINK_RE   = re.compile(r"https?://\S+", re.I)
_spam_buckets = defaultdict(lambda: deque(maxlen=10))

async def _automod_check(message):
    try:
        if message.author.guild_permissions.manage_messages: return
    except Exception: return
    async with bot.db.execute(
        "SELECT anti_invite, anti_link, anti_spam FROM automod_settings WHERE guild_id = ?",
        (message.guild.id,)
    ) as cur:
        row = await cur.fetchone()
    if not row: return
    anti_invite, anti_link, anti_spam = row
    content = message.content or ""
    deleted = False
    reason = None
    if anti_invite and INVITE_RE.search(content):
        reason = "Invite link not allowed"
    elif anti_link and LINK_RE.search(content):
        reason = "Links not allowed"
    if reason:
        try:
            await message.delete()
            deleted = True
        except Exception: pass
        try:
            await message.channel.send(
                embed=discord.Embed(color=0xffdd00,
                    description=f"{DOT} {message.author.mention}, your message was removed: **{reason}**"),
                delete_after=5
            )
        except Exception: pass
        return
    if anti_spam:
        bucket = _spam_buckets[(message.guild.id, message.author.id)]
        now = datetime.datetime.now().timestamp()
        bucket.append(now)
        # 5 messages within 5 seconds → spam
        if len(bucket) >= 5 and (now - bucket[0]) <= 5:
            bucket.clear()
            try:
                until = discord.utils.utcnow() + datetime.timedelta(minutes=5)
                await message.author.timeout(until, reason="Automod: spam")
                await message.channel.send(
                    embed=discord.Embed(color=0xffdd00,
                        description=f"{DOT} {message.author.mention} timed out for **5 minutes** (spam)."),
                    delete_after=8
                )
            except Exception: pass

@bot.command(name="automod")
@commands.has_permissions(manage_guild=True)
async def automod_cmd(ctx, action: str = None, setting: str = None):
    valid = {"invite": "anti_invite", "link": "anti_link", "spam": "anti_spam"}
    if not action or action.lower() == "status":
        async with bot.db.execute(
            "SELECT anti_invite, anti_link, anti_spam FROM automod_settings WHERE guild_id = ?",
            (ctx.guild.id,)
        ) as cur:
            row = await cur.fetchone()
        ai, al, asp = row if row else (0, 0, 0)
        embed = discord.Embed(color=0xffdd00, title="Automod Status")
        embed.description = (
            f"<:fp_arrow:1532073102580646070> Anti-Invite: {'**ON**' if ai else 'OFF'}\n"
            f"<:fp_arrow:1532073102580646070> Anti-Link:   {'**ON**' if al else 'OFF'}\n"
            f"<:fp_arrow:1532073102580646070> Anti-Spam:   {'**ON**' if asp else 'OFF'}\n\n"
            f"Use `,automod enable invite|link|spam` or `,automod disable invite|link|spam`"
        )
        return await ctx.send(embed=embed)
    if action.lower() in ("enable", "disable") and setting and setting.lower() in valid:
        col = valid[setting.lower()]
        val = 1 if action.lower() == "enable" else 0
        await bot.db.execute(
            f"INSERT INTO automod_settings (guild_id, {col}) VALUES (?, ?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {col}=excluded.{col}",
            (ctx.guild.id, val)
        )
        await bot.db.commit()
        return await ctx.send(embed=discord.Embed(
            color=0xffdd00, description=f"{DOT} Automod **{setting}** {'enabled' if val else 'disabled'}."
        ))
    await ctx.send(f"{DOT} Usage: `,automod enable|disable invite|link|spam` or `,automod status`")

# ═══════════════════════════════════════════════════════════════════
# ─── ANTI-NUKE V2 (Olympus-style engine) ───────────────────────────
# ═══════════════════════════════════════════════════════════════════
# Per-event audit log rate limit state (in-memory)
_AN_AUDIT_TS = {}        # {(guild_id, event_name): [timestamp...]}
_AN_AUDIT_COOLDOWN = {}  # {(guild_id, event_name): expiry_ts}

ANTINUKE_EVENTS = {
    "channel_delete":  "Channel Deletion",
    "channel_create":  "Channel Creation",
    "channel_update":  "Channel Update",
    "role_delete":     "Role Deletion",
    "role_create":     "Role Creation",
    "role_update":     "Role Update",
    "ban":             "Member Ban",
    "kick":            "Member Kick",
    "bot_add":         "Bot Add",
    "webhook_create":  "Webhook Create",
    "webhook_delete":  "Webhook Delete",
    "everyone":        "@everyone Mention",
    "guild_update":    "Server Edit",
}

def _an_can_fetch(guild_id, event_name, max_req=5, interval=10, cooldown=300):
    key = (guild_id, event_name)
    now = datetime.datetime.now().timestamp()
    until = _AN_AUDIT_COOLDOWN.get(key)
    if until and now < until:
        return False
    elif until:
        _AN_AUDIT_COOLDOWN.pop(key, None)
    ts = _AN_AUDIT_TS.setdefault(key, [])
    ts.append(now)
    ts[:] = [t for t in ts if now - t <= interval]
    if len(ts) > max_req:
        _AN_AUDIT_COOLDOWN[key] = now + cooldown
        return False
    return True

async def _an_audit(guild, action, target_id=None, perm="ban_members"):
    if not getattr(guild.me.guild_permissions, perm, False):
        return None
    try:
        async for entry in guild.audit_logs(action=action, limit=3):
            if target_id is not None and getattr(entry.target, "id", None) != target_id:
                continue
            age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if age >= 3600:
                return None
            return entry
    except Exception:
        return None
    return None

async def _an_event_enabled(guild_id, event_name):
    async with bot.db.execute(
        "SELECT enabled FROM antinuke_settings WHERE guild_id=?", (guild_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row or not row[0]:
        return False
    async with bot.db.execute(
        "SELECT enabled FROM antinuke_v2_events WHERE guild_id=? AND event_name=?",
        (guild_id, event_name)
    ) as cur:
        e = await cur.fetchone()
    if e is not None and not e[0]:
        return False
    return True

async def _an_is_immune(guild, user_id, event_name):
    if user_id == bot.user.id: return True
    if user_id == guild.owner_id: return True
    if user_id in PRIMARY_OWNER_IDS: return True
    if is_bot_owner(user_id): return True
    async with bot.db.execute(
        "SELECT events FROM antinuke_v2_whitelist WHERE guild_id=? AND user_id=?",
        (guild.id, user_id)
    ) as cur:
        row = await cur.fetchone()
    if row:
        ev = (row[0] or "").strip()
        if ev == "*" or event_name in [x.strip() for x in ev.split(",") if x.strip()]:
            return True
    # legacy v1 whitelist still respected
    async with bot.db.execute(
        "SELECT whitelist FROM antinuke_settings WHERE guild_id=?", (guild.id,)
    ) as cur:
        row = await cur.fetchone()
    if row and row[0]:
        wl = {int(x) for x in row[0].split(",") if x.strip().isdigit()}
        if user_id in wl:
            return True
    return False

async def _an_punish(guild, executor, reason, retries=3):
    member = guild.get_member(executor.id) if hasattr(executor, "id") else None
    while retries > 0:
        try:
            await guild.ban(executor, reason=f"Anti-Nuke V2: {reason}")
            return True
        except discord.Forbidden:
            if member:
                try:
                    for r in list(member.roles):
                        if r.is_default(): continue
                        try: await member.remove_roles(r, reason=f"Anti-Nuke V2: {reason}")
                        except Exception: pass
                except Exception: pass
            return False
        except discord.HTTPException as e:
            if e.status == 429:
                try: ra = float(e.response.headers.get("Retry-After", "1"))
                except Exception: ra = 1.0
                await asyncio.sleep(ra)
                retries -= 1
            else:
                return False
        except Exception:
            return False
    return False

async def _an_log(guild, title, executor, reason):
    ch = guild.system_channel
    if not ch: return
    try:
        embed = discord.Embed(
            color=0xffdd00,
            title=f"🛡️ Anti-Nuke V2 — {title}",
            description=f"<:fp_arrow:1532073102580646070> Offender: {executor.mention} (`{executor.id}`)\n<:fp_arrow:1532073102580646070> Action: **{reason}**"
        )
        await ch.send(embed=embed)
    except Exception: pass

# ─── HANDLERS ──────────────────────────────────────────────────────
@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    if not await _an_event_enabled(guild.id, "channel_delete"): return
    if not _an_can_fetch(guild.id, "channel_delete"): return
    entry = await _an_audit(guild, discord.AuditLogAction.channel_delete, channel.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "channel_delete"): return
    # Restore channel via clone
    async with bot.db.execute(
        "SELECT recreate_channels FROM antinuke_v2_settings WHERE guild_id=?", (guild.id,)
    ) as cur:
        s = await cur.fetchone()
    recreate = (s[0] if s else 1)
    if recreate:
        retries = 3
        while retries > 0:
            try:
                new_ch = await channel.clone(reason="Anti-Nuke V2: channel restore")
                try: await new_ch.edit(position=channel.position)
                except Exception: pass
                break
            except discord.HTTPException as e:
                if getattr(e, "status", None) == 429:
                    try: await asyncio.sleep(float(e.response.headers.get("Retry-After","1")))
                    except: await asyncio.sleep(1)
                    retries -= 1
                else: break
            except Exception: break
    await _an_punish(guild, entry.user, "channel deletion")
    await _an_log(guild, "Channel Deleted", entry.user, "Channel restored & offender banned")

@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    if not await _an_event_enabled(guild.id, "channel_create"): return
    if not _an_can_fetch(guild.id, "channel_create"): return
    entry = await _an_audit(guild, discord.AuditLogAction.channel_create, channel.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "channel_create"): return
    try: await channel.delete(reason="Anti-Nuke V2: unauthorized channel create")
    except Exception: pass
    await _an_punish(guild, entry.user, "channel creation")
    await _an_log(guild, "Channel Created", entry.user, "Channel removed & offender banned")

@bot.event
async def on_guild_channel_update(before, after):
    guild = after.guild
    if not await _an_event_enabled(guild.id, "channel_update"): return
    if not _an_can_fetch(guild.id, "channel_update"): return
    entry = await _an_audit(guild, discord.AuditLogAction.channel_update, after.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "channel_update"): return
    try: await after.edit(name=before.name, reason="Anti-Nuke V2: channel update reverted")
    except Exception: pass
    await _an_punish(guild, entry.user, "channel update")

@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    if not await _an_event_enabled(guild.id, "role_delete"): return
    if not _an_can_fetch(guild.id, "role_delete"): return
    entry = await _an_audit(guild, discord.AuditLogAction.role_delete, role.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "role_delete"): return
    await _an_punish(guild, entry.user, "role deletion")
    await _an_log(guild, "Role Deleted", entry.user, "Offender banned")

@bot.event
async def on_guild_role_create(role):
    guild = role.guild
    if not await _an_event_enabled(guild.id, "role_create"): return
    if not _an_can_fetch(guild.id, "role_create"): return
    entry = await _an_audit(guild, discord.AuditLogAction.role_create, role.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "role_create"): return
    try: await role.delete(reason="Anti-Nuke V2: unauthorized role create")
    except Exception: pass
    await _an_punish(guild, entry.user, "role creation")

@bot.event
async def on_guild_role_update(before, after):
    guild = after.guild
    if not await _an_event_enabled(guild.id, "role_update"): return
    if not _an_can_fetch(guild.id, "role_update"): return
    entry = await _an_audit(guild, discord.AuditLogAction.role_update, after.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "role_update"): return
    # Revert dangerous permission additions
    try:
        if after.permissions.administrator and not before.permissions.administrator:
            await after.edit(permissions=before.permissions, reason="Anti-Nuke V2: role perm revert")
    except Exception: pass
    await _an_punish(guild, entry.user, "role update")

@bot.event
async def on_member_ban(guild, user):
    if not await _an_event_enabled(guild.id, "ban"): return
    if not _an_can_fetch(guild.id, "ban"): return
    entry = await _an_audit(guild, discord.AuditLogAction.ban, user.id)
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "ban"): return
    try: await guild.unban(user, reason="Anti-Nuke V2: unauthorized ban reverted")
    except Exception: pass
    await _an_punish(guild, entry.user, "unauthorized ban")
    await _an_log(guild, "Member Banned", entry.user, "Ban reverted & offender banned")

@bot.event
async def on_member_remove(member):
    guild = member.guild
    if not await _an_event_enabled(guild.id, "kick"): return
    if not _an_can_fetch(guild.id, "kick"): return
    entry = await _an_audit(guild, discord.AuditLogAction.kick, member.id, perm="kick_members")
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "kick"): return
    await _an_punish(guild, entry.user, "unauthorized kick")
    await _an_log(guild, "Member Kicked", entry.user, "Offender banned")

@bot.listen("on_member_join")
async def _an_bot_add(member):
    if not member.bot: return
    guild = member.guild
    if not await _an_event_enabled(guild.id, "bot_add"): return
    if not _an_can_fetch(guild.id, "bot_add"): return
    entry = await _an_audit(guild, discord.AuditLogAction.bot_add, member.id, perm="kick_members")
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "bot_add"): return
    try: await guild.kick(member, reason="Anti-Nuke V2: unauthorized bot add")
    except Exception: pass
    await _an_punish(guild, entry.user, "unauthorized bot add")
    await _an_log(guild, "Bot Added", entry.user, "Bot kicked & inviter banned")

@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild
    if not await _an_event_enabled(guild.id, "webhook_create"): return
    if not _an_can_fetch(guild.id, "webhook_create"): return
    entry = await _an_audit(guild, discord.AuditLogAction.webhook_create, perm="manage_webhooks")
    if not entry:
        entry = await _an_audit(guild, discord.AuditLogAction.webhook_delete, perm="manage_webhooks")
    if not entry: return
    if await _an_is_immune(guild, entry.user.id, "webhook_create"): return
    # Delete recent webhooks created by offender
    try:
        hooks = await channel.webhooks()
        for h in hooks:
            if h.user and h.user.id == entry.user.id:
                try: await h.delete(reason="Anti-Nuke V2: unauthorized webhook")
                except Exception: pass
    except Exception: pass
    await _an_punish(guild, entry.user, "unauthorized webhook")

@bot.event
async def on_guild_update(before, after):
    if not await _an_event_enabled(after.id, "guild_update"): return
    if not _an_can_fetch(after.id, "guild_update"): return
    entry = await _an_audit(after, discord.AuditLogAction.guild_update, perm="manage_guild")
    if not entry: return
    if await _an_is_immune(after, entry.user.id, "guild_update"): return
    try:
        if before.name != after.name:
            await after.edit(name=before.name, reason="Anti-Nuke V2: revert server name")
    except Exception: pass
    await _an_punish(after, entry.user, "server edit")

@bot.listen("on_message")
async def _an_everyone(message):
    if message.guild is None or not message.mention_everyone: return
    if message.author.bot: return
    guild = message.guild
    if not await _an_event_enabled(guild.id, "everyone"): return
    if await _an_is_immune(guild, message.author.id, "everyone"): return
    if not _an_can_fetch(guild.id, "everyone", max_req=3, interval=5, cooldown=60): return
    try:
        await message.author.timeout(datetime.timedelta(hours=1), reason="Anti-Nuke V2: @everyone abuse")
    except Exception: pass
    try: await message.delete()
    except Exception: pass
    await _an_log(guild, "@everyone Abuse", message.author, "Timed out 1h")

# ─── ANTINUKE COMMAND (V2) ─────────────────────────────────────────
async def _an_get_status(gid):
    async with bot.db.execute(
        "SELECT enabled FROM antinuke_settings WHERE guild_id=?", (gid,)
    ) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])

@bot.command(name="antinuke", aliases=["an"])
@commands.has_permissions(administrator=True)
async def antinuke_cmd(ctx, *args):
    if not args:
        en = await _an_get_status(ctx.guild.id)
        # collect per-event toggles
        async with bot.db.execute(
            "SELECT event_name, enabled FROM antinuke_v2_events WHERE guild_id=?", (ctx.guild.id,)
        ) as cur:
            rows = await cur.fetchall()
        ev_map = {n: e for n, e in rows}
        lines = [f"<:fp_arrow:1532073102580646070> Status: {'**ENABLED ✅**' if en else '**DISABLED ❌**'}", "", "**Events** (default: all on):"]
        for k, label in ANTINUKE_EVENTS.items():
            on = ev_map.get(k, 1)
            lines.append(f"{DOT} `{k}` — {label}: {'✅' if on else '❌'}")
        # whitelist
        async with bot.db.execute(
            "SELECT user_id, events FROM antinuke_v2_whitelist WHERE guild_id=?", (ctx.guild.id,)
        ) as cur:
            wl = await cur.fetchall()
        lines.append("")
        lines.append(f"**Whitelist:** {len(wl)} user(s)")
        lines.append("")
        lines.append("**Commands:**")
        lines.append("`,antinuke enable` / `,antinuke disable`")
        lines.append("`,antinuke event <name> on|off`")
        lines.append("`,antinuke wl add @user [events,csv|*]`")
        lines.append("`,antinuke wl remove @user`")
        lines.append("`,antinuke wl list`")
        lines.append("`,antinuke config recreate on|off`")
        embed = discord.Embed(color=0xffdd00, title="🛡️ Anti-Nuke V2", description="\n".join(lines))
        return await ctx.send(embed=embed)

    sub = args[0].lower()

    if sub == "enable":
        await bot.db.execute(
            "INSERT INTO antinuke_settings (guild_id, enabled) VALUES (?, 1) "
            "ON CONFLICT(guild_id) DO UPDATE SET enabled=1", (ctx.guild.id,))
        await bot.db.commit()
        return await ctx.send(embed=discord.Embed(color=0xffdd00,
            description=f"{DOT} Anti-Nuke V2 **enabled**. All event guards active."))

    if sub == "disable":
        await bot.db.execute(
            "INSERT INTO antinuke_settings (guild_id, enabled) VALUES (?, 0) "
            "ON CONFLICT(guild_id) DO UPDATE SET enabled=0", (ctx.guild.id,))
        await bot.db.commit()
        return await ctx.send(embed=discord.Embed(color=0xffdd00,
            description=f"{DOT} Anti-Nuke V2 **disabled**."))

    if sub == "event":
        if len(args) < 3:
            return await ctx.send(f"{DOT} Usage: `,antinuke event <name> on|off`. Names: " + ", ".join(f"`{k}`" for k in ANTINUKE_EVENTS))
        ev = args[1].lower()
        state = args[2].lower()
        if ev not in ANTINUKE_EVENTS:
            return await ctx.send(f"{DOT} Unknown event. Valid: " + ", ".join(f"`{k}`" for k in ANTINUKE_EVENTS))
        val = 1 if state in ("on","enable","true","1","yes") else 0
        await bot.db.execute(
            "INSERT INTO antinuke_v2_events (guild_id, event_name, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, event_name) DO UPDATE SET enabled=excluded.enabled",
            (ctx.guild.id, ev, val))
        await bot.db.commit()
        return await ctx.send(embed=discord.Embed(color=0xffdd00,
            description=f"{DOT} Event `{ev}` {'enabled ✅' if val else 'disabled ❌'}."))

    if sub == "wl":
        if len(args) < 2:
            return await ctx.send(f"{DOT} Usage: `,antinuke wl add|remove|list ...`")
        op = args[1].lower()
        if op == "list":
            async with bot.db.execute(
                "SELECT user_id, events FROM antinuke_v2_whitelist WHERE guild_id=?", (ctx.guild.id,)
            ) as cur:
                rows = await cur.fetchall()
            if not rows:
                return await ctx.send(f"{DOT} No users whitelisted.")
            lines = []
            for uid, ev in rows:
                u = ctx.guild.get_member(uid) or await bot.fetch_user(uid).__anext__() if False else ctx.guild.get_member(uid)
                name = u.mention if u else f"`{uid}`"
                lines.append(f"<:fp_arrow:1532073102580646070> {name} — `{ev or '*'}`")
            return await ctx.send(embed=discord.Embed(color=0xffdd00, title="Anti-Nuke V2 Whitelist", description="\n".join(lines)))
        if not ctx.message.mentions:
            return await ctx.send(f"{DOT} Mention a user.")
        target = ctx.message.mentions[0]
        if op == "add":
            ev = args[3] if len(args) >= 4 else "*"
            await bot.db.execute(
                "INSERT INTO antinuke_v2_whitelist (guild_id, user_id, events) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET events=excluded.events",
                (ctx.guild.id, target.id, ev))
            await bot.db.commit()
            return await ctx.send(embed=discord.Embed(color=0xffdd00,
                description=f"{DOT} {target.mention} whitelisted for events: `{ev}`."))
        if op == "remove":
            await bot.db.execute(
                "DELETE FROM antinuke_v2_whitelist WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, target.id))
            await bot.db.commit()
            return await ctx.send(embed=discord.Embed(color=0xffdd00,
                description=f"{DOT} {target.mention} removed from whitelist."))
        return await ctx.send(f"{DOT} Unknown wl op. Use add/remove/list.")

    if sub == "config":
        if len(args) < 3:
            return await ctx.send(f"{DOT} Usage: `,antinuke config recreate on|off`")
        key = args[1].lower()
        val = 1 if args[2].lower() in ("on","enable","true","1","yes") else 0
        if key == "recreate":
            await bot.db.execute(
                "INSERT INTO antinuke_v2_settings (guild_id, recreate_channels) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET recreate_channels=excluded.recreate_channels",
                (ctx.guild.id, val))
            await bot.db.commit()
            return await ctx.send(embed=discord.Embed(color=0xffdd00,
                description=f"{DOT} Channel recreate {'enabled ✅' if val else 'disabled ❌'}."))
        return await ctx.send(f"{DOT} Unknown config key. Available: `recreate`")

    await ctx.send(f"{DOT} Unknown sub-command. Use `,antinuke` to see options.")

# ═══════════════════════════════════════════════════════════════════
# ─── ANTI-RAID ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
@bot.event
async def on_member_join_antiraid(member):
    pass  # placeholder — actual hook is via existing on_member_join in main file

# Hook into on_member_join via a second listener
@bot.listen("on_member_join")
async def _antiraid_listener(member):
    async with bot.db.execute(
        "SELECT enabled, join_limit, window_seconds FROM antiraid_settings WHERE guild_id=?",
        (member.guild.id,)
    ) as cur:
        row = await cur.fetchone()
    if not row or not row[0]: return
    _, limit, window = row
    dq = bot.recent_joins[member.guild.id]
    now = datetime.datetime.now().timestamp()
    dq.append((now, member.id))
    recent = [m for t, m in dq if now - t <= window]
    if len(recent) >= limit:
        # Kick the recent joiners (best-effort) and notify
        for uid in recent:
            m = member.guild.get_member(uid)
            if m and not m.bot:
                try: await m.kick(reason="Anti-Raid: mass join")
                except Exception: pass
        dq.clear()
        # Try to log
        ch = member.guild.system_channel
        if ch:
            try:
                await ch.send(embed=discord.Embed(
                    color=0xffdd00,
                    description=f"{DOT} **Anti-Raid triggered** — kicked {len(recent)} recent joiners."
                ))
            except Exception: pass

@bot.command(name="antiraid")
@commands.has_permissions(administrator=True)
async def antiraid_cmd(ctx, action: str = None, limit: int = None, window: int = None):
    if not action:
        async with bot.db.execute(
            "SELECT enabled, join_limit, window_seconds FROM antiraid_settings WHERE guild_id=?",
            (ctx.guild.id,)
        ) as cur:
            row = await cur.fetchone()
        en, lim, win = row if row else (0, 5, 10)
        embed = discord.Embed(color=0xffdd00, title="Anti-Raid")
        embed.description = (
            f"<:fp_arrow:1532073102580646070> Status: {'**ENABLED**' if en else 'DISABLED'}\n"
            f"<:fp_arrow:1532073102580646070> Joins threshold: **{lim}**\n"
            f"<:fp_arrow:1532073102580646070> Window: **{win}** seconds\n\n"
            f"Use `,antiraid enable [limit] [window]` or `,antiraid disable`"
        )
        return await ctx.send(embed=embed)
    if action.lower() == "enable":
        lim = limit or 5
        win = window or 10
        await bot.db.execute(
            "INSERT INTO antiraid_settings (guild_id, enabled, join_limit, window_seconds) "
            "VALUES (?, 1, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET enabled=1, join_limit=excluded.join_limit, window_seconds=excluded.window_seconds",
            (ctx.guild.id, lim, win)
        )
        await bot.db.commit()
        return await ctx.send(embed=discord.Embed(color=0xffdd00,
            description=f"{DOT} Anti-Raid **enabled** ({lim} joins / {win}s)."))
    if action.lower() == "disable":
        await bot.db.execute(
            "INSERT INTO antiraid_settings (guild_id, enabled) VALUES (?, 0) "
            "ON CONFLICT(guild_id) DO UPDATE SET enabled=0", (ctx.guild.id,)
        )
        await bot.db.commit()
        return await ctx.send(embed=discord.Embed(color=0xffdd00,
            description=f"{DOT} Anti-Raid **disabled**."))

# ═══════════════════════════════════════════════════════════════════
# ─── CRYPTO TOOLS (CoinGecko, no key) ──────────────────────────────
# ═══════════════════════════════════════════════════════════════════
COIN_ALIAS = {
    "btc":"bitcoin","eth":"ethereum","sol":"solana","doge":"dogecoin",
    "xrp":"ripple","ada":"cardano","bnb":"binancecoin","ltc":"litecoin",
    "matic":"matic-network","dot":"polkadot","trx":"tron","shib":"shiba-inu",
    "avax":"avalanche-2","link":"chainlink","atom":"cosmos","ton":"the-open-network",
}

@bot.command(name="crypto", aliases=["price"])
async def crypto_cmd(ctx, symbol: str = None):
    if not symbol:
        return await ctx.send(f"{DOT} Usage: `,crypto <symbol>`  e.g. `,crypto btc`")
    coin_id = COIN_ALIAS.get(symbol.lower(), symbol.lower())
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&community_data=false&developer_data=false"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return await ctx.send(f"{DOT} Coin `{symbol}` not found.")
                data = await resp.json()
        md = data.get("market_data", {})
        price = md.get("current_price", {}).get("usd", "?")
        change_24h = md.get("price_change_percentage_24h", 0) or 0
        mcap = md.get("market_cap", {}).get("usd", 0) or 0
        vol = md.get("total_volume", {}).get("usd", 0) or 0
        embed = discord.Embed(
            color=0xffdd00,
            title=f"{data.get('name','?')} ({data.get('symbol','').upper()})",
            url=f"https://www.coingecko.com/en/coins/{coin_id}"
        )
        thumb = (data.get("image") or {}).get("large")
        if thumb: embed.set_thumbnail(url=thumb)
        sign = "▲" if change_24h >= 0 else "▼"
        embed.add_field(name="Price (USD)", value=f"${price:,}", inline=True)
        embed.add_field(name="24h Change", value=f"{sign} {change_24h:.2f}%", inline=True)
        embed.add_field(name="Market Cap", value=f"${mcap:,.0f}", inline=True)
        embed.add_field(name="24h Volume", value=f"${vol:,.0f}", inline=True)
        rank = md.get("market_cap_rank")
        if rank: embed.add_field(name="Rank", value=f"#{rank}", inline=True)
        await ctx.send(embed=embed)
    except asyncio.TimeoutError:
        await ctx.send(f"{DOT} CoinGecko timeout.")
    except Exception as e:
        await ctx.send(f"{DOT} Error: {e}")

# ═══════════════════════════════════════════════════════════════════
# ─── MUSIC (yt-dlp + FFmpeg, basic queue) ──────────────────────────
# ═══════════════════════════════════════════════════════════════════
try:
    import yt_dlp
    YTDL_AVAILABLE = True
except Exception:
    YTDL_AVAILABLE = False

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

def _ytdl_extract(query):
    with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return {
            "title": info.get("title", "Unknown"),
            "url": info.get("url"),
            "webpage_url": info.get("webpage_url"),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader", "?"),
        }

async def _play_next(guild):
    queue = bot.music_queues[guild.id]
    if not queue:
        bot.now_playing.pop(guild.id, None)
        return
    track, requester_id = queue.pop(0)
    bot.now_playing[guild.id] = (track, requester_id)
    vc = guild.voice_client
    if not vc:
        return
    try:
        source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS)
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(_play_next(guild), bot.loop))
    except Exception:
        await _play_next(guild)

@bot.command(name="play", aliases=["p"])
async def play_cmd(ctx, *, query: str = None):
    if not YTDL_AVAILABLE:
        return await ctx.send(f"{DOT} Music library not installed.")
    if not query:
        return await ctx.send(f"{DOT} Usage: `,play <song name or URL>`")
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send(f"{DOT} Join a voice channel first.")
    vc = ctx.guild.voice_client
    if not vc:
        try:
            vc = await ctx.author.voice.channel.connect()
        except Exception as e:
            return await ctx.send(f"{DOT} Cannot join voice: {e}")
    msg = await ctx.send(f"{DOT} Searching...")
    try:
        track = await asyncio.to_thread(_ytdl_extract, query)
    except Exception as e:
        return await msg.edit(content=f"{DOT} Search failed: {e}")
    bot.music_queues[ctx.guild.id].append((track, ctx.author.id))
    if not vc.is_playing():
        await _play_next(ctx.guild)
        await msg.edit(content=None, embed=discord.Embed(
            color=0xffdd00, description=f"{DOT} Now playing: **{track['title']}**"
        ))
    else:
        await msg.edit(content=None, embed=discord.Embed(
            color=0xffdd00,
            description=f"{DOT} Queued: **{track['title']}** (position #{len(bot.music_queues[ctx.guild.id])})"
        ))

@bot.command(name="skip", aliases=["s"])
async def skip_cmd(ctx):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send(embed=discord.Embed(color=0xffdd00, description=f"{DOT} Skipped."))
    else:
        await ctx.send(f"{DOT} Nothing playing.")

@bot.command(name="stop")
async def stop_cmd(ctx):
    vc = ctx.guild.voice_client
    if vc:
        bot.music_queues[ctx.guild.id].clear()
        bot.now_playing.pop(ctx.guild.id, None)
        await vc.disconnect()
        await ctx.send(embed=discord.Embed(color=0xffdd00, description=f"{DOT} Stopped and disconnected."))

@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx):
    queue = bot.music_queues[ctx.guild.id]
    np = bot.now_playing.get(ctx.guild.id)
    embed = discord.Embed(color=0xffdd00, title="Music Queue")
    desc = ""
    if np:
        desc += f"**Now Playing:** {np[0]['title']} • <@{np[1]}>\n\n"
    if not queue:
        desc += f"{DOT} Queue is empty."
    else:
        desc += "\n".join([f"`{i+1}.` {t['title']} • <@{rid}>" for i,(t,rid) in enumerate(queue[:15])])
        if len(queue) > 15:
            desc += f"\n…and {len(queue)-15} more"
    embed.description = desc
    await ctx.send(embed=embed)

@bot.command(name="nowplaying", aliases=["nowp"])
async def nowplaying_cmd(ctx):
    np = bot.now_playing.get(ctx.guild.id)
    if not np:
        return await ctx.send(f"{DOT} Nothing playing.")
    track, rid = np
    is_premium = await is_user_premium(rid) or await is_user_premium(ctx.author.id)
    embed = discord.Embed(color=0xffdd00, title="Now Playing")
    if is_premium:
        embed.description = (
            f"**[{track['title']}]({track.get('webpage_url','')})**\n"
            f"<:fp_arrow:1532073102580646070> Uploader: `{track.get('uploader','?')}`\n"
            f"<:fp_arrow:1532073102580646070> Duration: `{track.get('duration',0)}s`\n"
            f"<:fp_arrow:1532073102580646070> Requested by: <@{rid}>"
        )
        if track.get("thumbnail"):
            embed.set_image(url=track["thumbnail"])
        embed.set_footer(text="✨ Premium NP+")
    else:
        embed.description = f"{DOT} **{track['title']}** — requested by <@{rid}>"
    await ctx.send(embed=embed)

# ─── RUN ───────────────────────────────────────────────────────────
bot.run("BOT TOKEN")



