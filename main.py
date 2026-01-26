import sqlite3
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import os
import asyncio
from datetime import datetime, timedelta
import random
from zoneinfo import ZoneInfo
from datetime import timezone

# ========================
# DATABASE SETUP
# ========================

conn = sqlite3.connect("/data/bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    rank INTEGER DEFAULT 1,
    streak INTEGER DEFAULT 0,
    last_quest_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS xp_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    xp INTEGER,
    timestamp TEXT
)
""")

# daily quest rotation (stores today's chosen quests)
cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_quest_rotation (
    rank TEXT,
    quest_key TEXT,
    quest_name TEXT,
    xp INTEGER,
    date TEXT
)
""")

# Track used quests for 7-day rotation (for _2 type quests)
cursor.execute("""
CREATE TABLE IF NOT EXISTS quest_seven_day_pool (
    quest_key TEXT,
    used_quests TEXT,
    cycle_start TEXT
)
""")

# weekly quest rotation
cursor.execute("""
CREATE TABLE IF NOT EXISTS weekly_quest_rotation (
    rank TEXT,
    quest_name TEXT,
    xp INTEGER,
    week_start TEXT
)
""")

# quest claim tracking
cursor.execute("""
CREATE TABLE IF NOT EXISTS quest_claims (
    user_id INTEGER,
    quest_key TEXT,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_quest_post_log (
    date TEXT PRIMARY KEY
)
""")

conn.commit()

# ========================
# BOT SETUP
# ========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot._ready_ran = False

# ========================
# TIMEZONE
# ========================

TZ = ZoneInfo("America/New_York")

def today_est():
    return datetime.now(TZ).date().isoformat()

def week_start_est():
    now = datetime.now(TZ)
    start = now - timedelta(days=now.weekday())
    return start.date().isoformat()

# ========================
# CHANNEL PERMISSIONS
# ========================

ALLOWED_QUEST_CHANNEL = ["quest-log"]

# ========================
# RANK DATA
# ========================

RANKS = {
    1: "Initiate",
    2: "Explorer",
    3: "Connector",
    4: "Leader",
    5: "Master"
}

RANK_ROLE_NAMES = {
    "Initiate": "Initiate",
    "Explorer": "Explorer",
    "Connector": "Connector",
    "Leader": "Leader",
    "Master": "Master"
}

RANK_COLORS = {
    "Initiate": 0x2ECC71,
    "Explorer": 0x3498DB,
    "Connector": 0x9B59B6,
    "Leader": 0xE91E63,
    "Master": 0xF1C40F
}

# XP thresholds for ranks
RANK_XP_THRESHOLDS = {
    1: (0, 150),
    2: (150, 650),
    3: (650, 1600),
    4: (1600, 3200),
    5: (3200, float("inf"))
}

# Tier thresholds within ranks
RANK_TIERS = {
    "Initiate": [],  # No tiers
    "Explorer": [150, 300, 450],
    "Connector": [650, 800, 1000, 1200, 1400],
    "Leader": [1600, 1900, 2200, 2500, 2800],
    "Master": [3200, 4200, 5200, 6200, 7200]
}

LEADERBOARD_COLORS = {
    "initiate": 0x2ECC71,
    "explorer": 0x3498DB,
    "connector": 0x9B59B6,
    "leader": 0xE91E63,
    "master": 0xF1C40F,
    "global": 0xFFFFFF
}

RANK_EMOJIS = {
    "initiate": "🟢",
    "explorer": "🔵",
    "connector": "🟣",
    "leader": ":red_circle:",
    "master": "🟡",
    "global": "🏆"
}

# ========================
# QUEST POOLS
# ========================

QUEST_POOLS = {
    "initiate_1": [
        "Smile at 5 people.",
        "Say 'Hi' or 'Good morning' to 3 people.",
        "Make eye contact with 5 strangers."
    ],
    "initiate_2": [
        "Sit in a public place for 10 minutes with no phone.",
        "Walk through a busy street for 10 minutes without headphones.",
        "Compliment someone's clothing.",
        "Read or write for 15 minutes in a public place.",
        "Write 5 sentences about how you felt being around people today.",
        "Use someone's name after they introduce themselves.",
        "Thank 3 service workers with genuine presence."
    ],
    "explorer_1": [
        "Ask a stranger for the time.",
        "Comment about your surroundings to a stranger.",
        "Ask someone how their day is going."
    ],
    "explorer_2": [
        "Have a 30-second conversation with a barista/cashier",
        "Ask someone for a food or coffee recommendation.",
        "Talk to someone in a queue.",
        "Ask someone what they're reading.",
        "Ask someone about a good place to go nearby.",
        "Ask a stranger for directions (even if you know).",
        "Ask someone their weekend plans."
    ],
    "connector_1": [
        "Learn someone's name",
        "Give 3 compliments to strangers.",
        "Catch up with an acquaintance."
    ],
    "connector_2": [
        "Insert yourself into an existing group conversation.",
        "Share a small personal truth with someone new.",
        "Sit next to a stranger and start a conversation.",
        "Invite someone for a short coffee.",
        "Give a compliment about someone's personality.",
        "Ask someone new about their passions.",
        "Tell a new short personal story to someone."
    ],
    "leader_1": [
        "Start 3 conversations.",
        "Lead a group conversation.",
        "Give 3 compliments about a person's energy or personality."
    ],
    "leader_2": [
        "Bring two people together who don't know each other.",
        "Get to know someone over coffee or a walk.",
        "Learn the names of 3 new people in one day.",
        "Stand alone in a busy place for 10 minutes with no phone.",
        "Ask a group a meaningful question.",
        "Reflect back someone's feelings in a conversation.",
        "Sit next to a stranger and start a conversation."
    ]
}

WEEKLY_QUESTS = {
    "initiate": (15, [
        "Ask someone about their day.",
        "Ask someone what the time is."
    ]),
    "explorer": (30, [
        "End a conversation early, but confidently and politely.",
        "Introduce yourself to someone new.",
        "In an awkward silence, stay present and let others fill the silence."
    ]),
    "connector": (45, [
        "Exchange contact details with someone.",
        "At a social event, talk to 3 new people.",
        "Encourage a runner or cyclist.",
        "Eat a meal alone in public without your phone."
    ]),
    "leader": (60, [
        "Invite someone to an event or activity.",
        "Have a 10 minute conversation with someone you recently met.",
        "For 30 minutes, make eye contact with everyone who enters a social space.",
        "Keep a conversation going for 15 minutes without checking your phone or escaping.",
        "Organise a group activity like a dinner walk or social event."
    ]),
    "master": (75, [
        "Support someone through a vulnerable conversation.",
        "Spend a full day saying yes to social opportunities.",
        "Be the person who welcomes newcomers into a space.",
        "Help resolve a disagreement.",
        "Help 5 people build new connections."
    ])
}

XP_VALUES = {
    "initiate_1": 5,
    "initiate_2": 10,
    "explorer_1": 15,
    "explorer_2": 20,
    "connector_1": 25,
    "connector_2": 30,
    "leader_1": 35,
    "leader_2": 40
}

# Quest channel mappings
QUEST_CHANNELS = {
    "initiate": "initiate-quests",
    "explorer": "explorer-quests",
    "connector": "connector-quests",
    "leader": "leader-quests",
    "master": "master-quests"
}

# Define which quests each rank can access
RANK_QUEST_ACCESS = {
    1: ["initiate_1", "initiate_2"],  # Initiate
    2: ["initiate_1", "explorer_1", "explorer_2"],  # Explorer
    3: ["initiate_1", "explorer_1", "connector_1", "connector_2"],  # Connector
    4: ["initiate_1", "explorer_1", "connector_1", "leader_1", "leader_2"],  # Leader
    5: ["explorer_1", "connector_1", "connector_2", "leader_1", "leader_2"]  # Master
}

# ========================
# HELPERS
# ========================

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, xp, rank, streak) VALUES (?, 0, 1, 0)",
            (user_id,)
        )
        conn.commit()
        return get_user(user_id)

    return user

def log_xp(user_id, amount):
    cursor.execute(
        "INSERT INTO xp_log (user_id, xp, timestamp) VALUES (?, ?, ?)",
        (user_id, amount, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()

def add_xp(user_id, amount):
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    log_xp(user_id, amount)

def add_bonus_xp(user_id, amount):
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def set_rank(user_id, rank):
    cursor.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank, user_id))
    conn.commit()

def get_rank_from_xp(xp):
    """Return rank number based on XP"""
    for rank, (min_xp, max_xp) in RANK_XP_THRESHOLDS.items():
        if min_xp <= xp < max_xp:
            return rank
    return 5  # Maser if XP exceeds highest threshold

def get_tier_from_xp(rank_number, xp):
    rank_name = RANKS[rank_number]
    tiers = RANK_TIERS.get(rank_name, [])

    if not tiers:
        return None

    for i, threshold in enumerate(tiers):
        if xp < threshold:
            return i + 1

    return len(tiers)

async def assign_rank_role(member, rank_number):
    guild = member.guild
    rank_name = RANKS.get(rank_number)

    rank_role = discord.utils.get(guild.roles, name=rank_name)
    unranked_role = discord.utils.get(guild.roles, name="Unranked")

    if unranked_role and unranked_role in member.roles:
        try:
            await member.remove_roles(unranked_role)
        except:
            pass

    for role in member.roles:
        if role.name in RANKS.values() and role.name != rank_name:
            try:
                await member.remove_roles(role)
            except:
                pass

    if rank_role and rank_role not in member.roles:
        try:
            await member.add_roles(rank_role)
        except:
            pass

# ========================
# QUEST ROTATION ENGINE
# ========================

def get_seven_day_quest(quest_key):
    """Get a quest from the 7-day rotation pool, ensuring no repeats until all are used"""
    today = today_est()
    
    # Check if we have an active cycle
    cursor.execute("""
        SELECT used_quests, cycle_start FROM quest_seven_day_pool
        WHERE quest_key = ?
    """, (quest_key,))
    
    result = cursor.fetchone()
    
    if result:
        used_quests_str, cycle_start = result
        used_quests = used_quests_str.split(',') if used_quests_str else []
        
        # Check if cycle needs reset (7 days have passed or all quests used)
        cycle_start_date = datetime.fromisoformat(cycle_start).date()
        days_since_start = (datetime.fromisoformat(today).date() - cycle_start_date).days
        
        if days_since_start >= 7 or len(used_quests) >= 7:
            # Reset cycle
            used_quests = []
            cycle_start = today
    else:
        # Initialize new cycle
        used_quests = []
        cycle_start = today
    
    # Get available quests (not yet used in this cycle)
    all_quests = QUEST_POOLS[quest_key]
    available_quests = [q for q in all_quests if q not in used_quests]
    
    # If no quests available, reset
    if not available_quests:
        available_quests = all_quests
        used_quests = []
        cycle_start = today
    
    # Select random quest from available
    chosen_quest = random.choice(available_quests)
    
    # Update used quests
    used_quests.append(chosen_quest)
    
    # Save to database
    cursor.execute("""
        DELETE FROM quest_seven_day_pool WHERE quest_key = ?
    """, (quest_key,))
    
    cursor.execute("""
        INSERT INTO quest_seven_day_pool (quest_key, used_quests, cycle_start)
        VALUES (?, ?, ?)
    """, (quest_key, ','.join(used_quests), cycle_start))
    
    conn.commit()
    
    return chosen_quest

def generate_daily_quests():
    today = today_est()
    
    # Check if quests already exist for today
    cursor.execute("SELECT COUNT(*) FROM daily_quest_rotation WHERE date = ?", (today,))
    if cursor.fetchone()[0] > 0:
        return  # Already generated
    
    # Delete old quests
    cursor.execute("DELETE FROM daily_quest_rotation WHERE date != ?", (today,))

    for key, pool in QUEST_POOLS.items():
        # Check if this is a _1 or _2 type quest
        if key.endswith("_1"):
            # Simple random selection from 3 quests
            chosen = random.choice(pool)
        else:  # _2 type quests
            # Use 7-day rotation logic
            chosen = get_seven_day_quest(key)
        
        xp = XP_VALUES[key]
        rank = key.split("_")[0]

        cursor.execute("""
            INSERT INTO daily_quest_rotation (rank, quest_key, quest_name, xp, date)
            VALUES (?, ?, ?, ?, ?)
        """, (rank, key, chosen, xp, today))

    conn.commit()

def generate_weekly_quests():
    week = week_start_est()
    
    # Check if quests already exist for this week
    cursor.execute("SELECT COUNT(*) FROM weekly_quest_rotation WHERE week_start = ?", (week,))
    if cursor.fetchone()[0] > 0:
        return  # Already generated
    
    # Delete old quests
    cursor.execute("DELETE FROM weekly_quest_rotation WHERE week_start != ?", (week,))

    for rank, (xp, pool) in WEEKLY_QUESTS.items():
        chosen = random.choice(pool)
        cursor.execute("""
            INSERT INTO weekly_quest_rotation (rank, quest_name, xp, week_start)
            VALUES (?, ?, ?, ?)
        """, (rank, chosen, xp, week))

    conn.commit()

def has_claimed(user_id, quest_key):
    cursor.execute("""
        SELECT 1 FROM quest_claims WHERE user_id = ? AND quest_key = ? AND date = ?
    """, (user_id, quest_key, today_est()))
    return cursor.fetchone() is not None

def claim_quest(user_id, quest_key):
    cursor.execute("""
        INSERT INTO quest_claims (user_id, quest_key, date)
        VALUES (?, ?, ?)
    """, (user_id, quest_key, today_est()))
    conn.commit()

# ========================
# POST QUESTS TO CHANNELS
# ========================

async def post_daily_quests():
    """Post daily quests to their respective channels"""
    today = today_est()

    # 🔧 NEW: prevent duplicate posting
    cursor.execute("SELECT 1 FROM daily_quest_post_log WHERE date = ?", (today,))
    if cursor.fetchone():
        return  # already posted today

    # Ensure quests exist
    cursor.execute("SELECT COUNT(*) FROM daily_quest_rotation WHERE date = ?", (today,))
    if cursor.fetchone()[0] == 0:
        return  # quests not generated yet

    week = week_start_est()

    for guild in bot.guilds:
        for rank_num, rank_name in RANKS.items():
            rank_name_lower = rank_name.lower()
            channel_name = QUEST_CHANNELS[rank_name_lower].lower()

            channel = discord.utils.find(
                lambda c: c.name.lower() == channel_name,
                guild.text_channels
            )

            if not channel:
                continue

            accessible_quests = RANK_QUEST_ACCESS[rank_num]

            role = discord.utils.get(guild.roles, name=RANK_ROLE_NAMES[rank_name])
            role_mention = role.mention if role else rank_name

            header_message = f"Here are your {role_mention} quests for today!"

            embed = discord.Embed(
                title=f"📜 Daily Quests for {rank_name}",
                description="Complete these quests today! Use the commands below to claim XP.",
                color=RANK_COLORS.get(rank_name, 0xFFFFFF),
                timestamp=datetime.now(TZ)
            )

            for quest_key in accessible_quests:
                cursor.execute("""
                    SELECT quest_name, xp FROM daily_quest_rotation
                    WHERE quest_key = ? AND date = ?
                """, (quest_key, today))

                result = cursor.fetchone()
                if result:
                    quest_name, xp = result
                    command = f"!{quest_key.replace('_', '')}"
                    embed.add_field(
                        name=f"{quest_name} ({xp} XP)",
                        value=f"Command: `{command}`",
                        inline=False
                    )

            cursor.execute("""
                SELECT quest_name, xp FROM weekly_quest_rotation
                WHERE rank = ? AND week_start = ?
            """, (rank_name_lower, week))

            weekly = cursor.fetchone()
            if weekly:
                quest_name, xp = weekly
                embed.add_field(
                    name=f"🌟 Weekly Quest ({xp} XP)",
                    value=f"{quest_name}\n*Use `!{rank_name_lower}weekly` to claim*",
                    inline=False
                )

            embed.set_footer(text="New quests posted daily at midnight EST")

            try:
                await channel.send(
                    content=header_message,
                    embed=embed
                )
            except Exception as e:
                print(f"Error posting to {channel_name}: {e}")

    # 🔧 NEW: mark quests as posted for today
    cursor.execute(
        "INSERT OR IGNORE INTO daily_quest_post_log (date) VALUES (?)",
        (today,)
    )
    conn.commit()

# ========================
# DAILY SCHEDULER
# ========================

@tasks.loop(minutes=5)
async def daily_reset_task():
    today = today_est()
    cursor.execute(
        "SELECT 1 FROM daily_quest_post_log WHERE date = ?",
        (today,)
    )
    if cursor.fetchone():
        return

    generate_daily_quests()
    generate_weekly_quests()
    await post_daily_quests()

@daily_reset_task.before_loop
async def before_daily_reset():
    await bot.wait_until_ready()
    # Calculate time until next midnight EST
    now = datetime.now(TZ)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    wait_seconds = (next_midnight - now).total_seconds()
    await asyncio.sleep(wait_seconds)

# ========================
# QUEST NOTIFICATIONS
# ========================

@tasks.loop(minutes=60)
async def quest_notifications():
    now = datetime.now(TZ)
    current_hour = now.hour

    # Only run at 9am or 1pm EST
    if current_hour not in (9, 13):
        return

    guild = bot.guilds[0]  # assumes single-server bot

    for rank_key, channel_name in QUEST_CHANNELS.items():
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        role = discord.utils.get(guild.roles, name=rank_key.capitalize())

        if not channel or not role:
            continue

        if current_hour == 9:
            text = "Don’t forget to complete a quest today!"
        else:
            text = "Your streak! You still have time to complete a quest!"

        # 🔔 send ping, then delete message (notification remains)
        msg = await channel.send(f"{role.mention} {text}")
        await msg.delete()

# ========================
# QUEST COMMANDS
# ========================

async def quest_command(ctx, quest_key):
    # Check channel permissions
    if ctx.channel.name not in ALLOWED_QUEST_CHANNEL:
        valid_channel = False
        for channel_name in QUEST_CHANNELS.values():
            if ctx.channel.name == channel_name:
                valid_channel = True
                break
        
        if not valid_channel:
            await ctx.send("❌ Quest commands can only be used in quest channels.")
            return

    # Get user's rank
    user = get_user(ctx.author.id)
    user_rank = user[2]
    
    # Check if user has access to this quest
    if quest_key not in RANK_QUEST_ACCESS[user_rank]:
        await ctx.send(f"❌ You don't have access to this quest. Your current rank is {RANKS[user_rank]}.")
        return

    # Check if quest exists for today
    cursor.execute("""
        SELECT quest_name, xp FROM daily_quest_rotation
        WHERE quest_key = ? AND date = ?
    """, (quest_key, today_est()))

    result = cursor.fetchone()
    if not result:
        await ctx.send("❌ This quest is not available today.")
        return

    quest_name, xp = result

    # Check if already claimed
    if has_claimed(ctx.author.id, quest_key):
        await ctx.send("❌ You have already completed this quest today.")
        return

    # Award XP
    old_xp = user[1]
    add_xp(ctx.author.id, xp)
    claim_quest(ctx.author.id, quest_key)

    update_streak(ctx.author.id)
    
    # Check for rank up
    new_xp = old_xp + xp
    old_rank = user[2]
    new_rank = get_rank_from_xp(new_xp)

    old_tier = get_tier_from_xp(old_rank, old_xp)

    if new_rank == old_rank:
        new_tier = get_tier_from_xp(old_rank, new_xp)
    else:
        new_tier = 1


    # Determine message
    message_parts = [f"✅ Quest completed!\nQuest: {quest_name}\nXP Gained: {xp}"]

    # Rank up
    if new_rank > old_rank:
        set_rank(ctx.author.id, new_rank)
        await assign_rank_role(ctx.author, new_rank)
        message_parts.append(f"🎉 **RANK UP!** You are now {RANKS[new_rank]}!")
    
    # Tier up (even if rank didn't change)
    elif new_tier > old_tier:
        message_parts.append(f"✨ **TIER UP!** You are now {RANKS[new_rank]} — Tier {new_tier}!")

    await ctx.send("\n".join(message_parts))


# Daily Quest Commands
@bot.command(name="initiate1")
async def initiate_1(ctx):
    await quest_command(ctx, "initiate_1")

@bot.command(name="initiate2")
async def initiate_2(ctx):
    await quest_command(ctx, "initiate_2")

@bot.command(name="explorer1")
async def explorer_1(ctx):
    await quest_command(ctx, "explorer_1")

@bot.command(name="explorer2")
async def explorer_2(ctx):
    await quest_command(ctx, "explorer_2")

@bot.command(name="connector1")
async def connector_1(ctx):
    await quest_command(ctx, "connector_1")

@bot.command(name="connector2")
async def connector_2(ctx):
    await quest_command(ctx, "connector_2")

@bot.command(name="leader1")
async def leader_1(ctx):
    await quest_command(ctx, "leader_1")

@bot.command(name="leader2")
async def leader_2(ctx):
    await quest_command(ctx, "leader_2")

# Weekly Quest Commands
async def weekly_quest_command(ctx, rank_name):
    user = get_user(ctx.author.id)
    user_rank = user[2]
    user_rank_name = RANKS[user_rank].lower()
    
    # Check if user's rank matches the quest rank
    if user_rank_name != rank_name:
        await ctx.send(f"❌ You cannot claim this weekly quest. Your current rank is {RANKS[user_rank]}.")
        return
    
    week = week_start_est()
    quest_key = f"weekly_{rank_name}_{week}"
    
    if has_claimed(ctx.author.id, quest_key):
        await ctx.send("❌ You have already completed your weekly quest this week.")
        return
    
    cursor.execute("""
        SELECT quest_name, xp FROM weekly_quest_rotation
        WHERE rank = ? AND week_start = ?
    """, (rank_name, week))
    
    result = cursor.fetchone()
    if not result:
        await ctx.send("❌ No weekly quest available.")
        return
    
    quest_name, xp = result
    
    old_xp = user[1]
    add_xp(ctx.author.id, xp)
    claim_quest(ctx.author.id, quest_key)
    
    new_xp = old_xp + xp
    new_rank = get_rank_from_xp(new_xp)
    
    new_xp = old_xp + xp
    new_rank = get_rank_from_xp(new_xp)
    old_rank = user[2]
    old_tier = get_tier_from_xp(old_rank, old_xp)
    new_tier = get_tier_from_xp(new_rank, new_xp)

    # Determine message
    message_parts = [f"✅ Weekly quest completed!\nQuest: {quest_name}\nXP Gained: {xp}"]

    # Rank up
    if new_rank > old_rank:
        set_rank(ctx.author.id, new_rank)
        await assign_rank_role(ctx.author, new_rank)
        message_parts.append(f"🎉 **RANK UP!** You are now {RANKS[new_rank]}!")

    # Tier up (even if rank didn't change)
    elif new_tier > old_tier:
        message_parts.append(f"✨ **TIER UP!** You are now {RANKS[new_rank]} — Tier {new_tier}!")

    await ctx.send("\n".join(message_parts))

@bot.command(name="initiateweekly")
async def initiate_weekly(ctx):
    await weekly_quest_command(ctx, "initiate")

@bot.command(name="explorerweekly")
async def explorer_weekly(ctx):
    await weekly_quest_command(ctx, "explorer")

@bot.command(name="connectorweekly")
async def connector_weekly(ctx):
    await weekly_quest_command(ctx, "connector")

@bot.command(name="leaderweekly")
async def leader_weekly(ctx):
    await weekly_quest_command(ctx, "leader")

@bot.command(name="masterweekly")
async def master_weekly(ctx):
    await weekly_quest_command(ctx, "master")

# ========================
# STORY SHARING
# ========================

STORY_CHANNEL = ["story-feed"]
STORY_XP_PER_REACTION = 2
STORY_XP_MAX = 10

# Create tables for story tracking
cursor.execute("""
CREATE TABLE IF NOT EXISTS story_posts (
    message_id INTEGER PRIMARY KEY,
    author_id INTEGER,
    xp_awarded INTEGER DEFAULT 0,
    date_posted TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS story_reactions (
    message_id INTEGER,
    reactor_id INTEGER,
    date TEXT,
    PRIMARY KEY(message_id, reactor_id)
)
""")
conn.commit()

# Command to submit a story
@bot.command()
async def story(ctx, *, content: str):
    """Submit a story or experience to share with the server."""
    if ctx.channel.name not in STORY_CHANNEL:
        await ctx.send(f"❌ Stories can only be submitted in: {', '.join(STORY_CHANNEL)}")
        return

    # Remove original user message
    try:
        await ctx.message.delete()
    except:
        pass

    # Create embed with user's name
    embed = discord.Embed(
        title=f"📖 {ctx.author.display_name}'s Story!",
        description=content,
        color=0xFFA500,
        timestamp=datetime.now(TZ)
    )
    embed.set_footer(text=f"React to award XP! Max {STORY_XP_MAX} XP per story.")

    # Send bot repost
    bot_message = await ctx.send(embed=embed)

    # Track in database
    today = today_est()
    cursor.execute("""
        INSERT INTO story_posts (message_id, author_id, xp_awarded, date_posted)
        VALUES (?, ?, ?, ?)
    """, (bot_message.id, ctx.author.id, 0, today))
    conn.commit()

# Reaction listener to grant XP
@bot.event
async def on_reaction_add(reaction, user):
    """Award XP when someone reacts to a story embed."""

    message = reaction.message

    if user.bot:
        return  # Ignore bot reactions

    if message.author.id == user.id:
        return

    cursor.execute(
        "SELECT COUNT(*) FROM story_reactions WHERE message_id = ?",
        (message.id,)
    )
    if cursor.fetchone()[0] >= 3:
        return

    cursor.execute(
        "SELECT COUNT(*) FROM story_reactions WHERE user_id = ?",
        (user.id,)
    )
    if cursor.fetchone()[0] >= 3:
        return

    # Only allow reactions in story channel
    if message.channel.name not in STORY_CHANNEL:
        return

    cursor.execute(
        "INSERT OR IGNORE INTO story_reactions (message_id, user_id) VALUES (?, ?)",
        (message.id, user.id)
    )
    conn.commit()

    # Check if this message is a tracked story
    cursor.execute("SELECT author_id, xp_awarded FROM story_posts WHERE message_id = ?", (message.id,))
    result = cursor.fetchone()
    if not result:
        return  # Not a story post

    author_id, current_xp = result

    # Check if reactor has already given a story XP today
    today = today_est()
    cursor.execute("""
        SELECT 1 FROM story_reactions
        WHERE message_id = ? AND reactor_id = ? AND date = ?
    """, (message.id, user.id, today))
    if cursor.fetchone():
        return  # Reactor already gave XP today for this story

    # Only give XP if story hasn't reached max
    if current_xp >= STORY_XP_MAX:
        return  # Max XP reached

    # Grant XP to original author
    xp_to_add = min(STORY_XP_PER_REACTION, STORY_XP_MAX - current_xp)
    add_xp(author_id, xp_to_add)

    # Log reaction
    cursor.execute("""
        INSERT INTO story_reactions (message_id, reactor_id, date)
        VALUES (?, ?, ?)
    """, (message.id, user.id, today))

    # Update XP in story_posts table
    cursor.execute("""
        UPDATE story_posts SET xp_awarded = xp_awarded + ? WHERE message_id = ?
    """, (xp_to_add, message.id))
    conn.commit()

    # Optionally, notify the author in the channel
    author = message.guild.get_member(author_id)
    if author:
        try:
            await message.channel.send(f"🎉 {author.mention} received {xp_to_add} XP for their story!")
        except:
            pass

# ========================
# STREAK HANDLING
# ========================

def update_streak(user_id):
    cursor.execute("SELECT last_quest_date, streak FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if not result:
        return 1
    
    last_date, streak = result
    today = datetime.utcnow().date()

    if last_date:
        last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
        delta_days = (today - last_date).days

        if delta_days == 1:
            streak += 1
        elif delta_days > 1:
            streak = 1
    else:
        streak = 1

    cursor.execute(
        "UPDATE users SET streak = ?, last_quest_date = ? WHERE user_id = ?",
        (streak, today.isoformat(), user_id)
    )
    conn.commit()
    return streak

# ========================
# RANK SELECTION VIEW
# ========================

class RankSelectView(View):
    def __init__(self, member_id):
        super().__init__(timeout=None)
        self.member_id = member_id

    @discord.ui.button(label="🟢 Start as Initiate", style=discord.ButtonStyle.success, custom_id="rank_initiate")
    async def initiate_button(self, interaction: discord.Interaction, button: Button):
        await self.assign_rank(interaction, 1, 0)

    @discord.ui.button(label="🔵 Start as Explorer", style=discord.ButtonStyle.primary, custom_id="rank_explorer")
    async def explorer_button(self, interaction: discord.Interaction, button: Button):
        await self.assign_rank(interaction, 2, 150)

    async def assign_rank(self, interaction: discord.Interaction, rank_number, bonus_xp):
        if interaction.user.id != self.member_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return

        member = interaction.user
        guild = interaction.guild

        set_rank(member.id, rank_number)

        if bonus_xp > 0:
            add_bonus_xp(member.id, bonus_xp)

        await assign_rank_role(member, rank_number)

        try:
            await interaction.message.delete()
        except:
            pass

        welcome_channel = discord.utils.get(guild.text_channels, name="welcome")
        if welcome_channel:
            await welcome_channel.send(
                f"🎉 Welcome {member.mention}!\n\n"
                "📜 Please read the rules in **#rules**\n"
                "🎓 Learn how the game works in **#tutorial**\n\n"
                "Your journey starts now — complete your first quest today!"
            )

# ========================
# EVENTS
# ========================

@bot.event
async def on_ready():
    if bot._ready_ran:
        return

    bot._ready_ran = True

    print(f"✅ Logged in as {bot.user}")

    bot.add_view(RankSelectView(0))

    generate_daily_quests()
    generate_weekly_quests()

    await post_daily_quests()

    if not daily_reset_task.is_running():
        daily_reset_task.start()

    if not quest_notifications.is_running():
        quest_notifications.start()



@bot.event
async def on_member_join(member):
    if member.bot:
        return

    get_user(member.id)

    guild = member.guild

    unranked_role = discord.utils.get(guild.roles, name="Unranked")
    if unranked_role:
        try:
            await member.add_roles(unranked_role)
        except:
            pass

    start_channel = discord.utils.get(guild.text_channels, name="start-here")
    if not start_channel:
        return

    view = RankSelectView(member.id)

    await start_channel.send(
        f"👋 Welcome {member.mention} to the Social Guinea Pigs!\n\n"
        "This server is a **real-world** social confidence game. It's a place for people to step out of their comfort zone as they complete **daily and weekly challenges** made to suit your own progression.\n"
        "You complete these small challenges in real life, earn XP, rank up, and build confidence step by step.\n\n"
        "For those who want to start small, we recommend starting with the **Initiate Rank**. For those who want to build on their existing social skills, we recommend choosing the **Explorer Rank**.\n"
        "Choose your starting path:\n"
        "🟢 **Initiate** — slower, gentler challenges\n"
        "🔵 **Explorer** — for confident starters\n",
        view=view
    )

# ========================
# PROFILE WIDGET
# ========================

@bot.command()
async def progress(ctx, member: discord.Member = None):
    target = member or ctx.author
    user = get_user(target.id)
    xp, rank_number, streak = user[1], user[2], user[3]

    rank_name = RANKS[rank_number]
    tier = get_tier_from_xp(rank_number, xp) or 1
    
    tiers = RANK_TIERS.get(rank_name, [])

    if tiers:
        tier_index = tier - 1

        if tier_index < len(tiers):
            next_goal_xp = tiers[tier_index]
            next_goal_label = f"{rank_name} — Tier {tier + 1}"
            xp_to_next_goal = max(0, next_goal_xp - xp)
        else:
            next_goal_xp = None
    else:
        next_goal_xp = None

    embed = discord.Embed(
        title=f"{target.display_name}'s Profile",
        description=f"**{rank_name}**",
         color=RANK_COLORS.get(rank_name, 0xFFFFFF)
    )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🔥 Streak", value=f"{streak} day{'s' if streak != 1 else ''}", inline=True)
    embed.add_field(name="⭐ XP", value=f"{xp} XP", inline=True)
    embed.add_field(
        name="Next Goal",
        value=f"{next_goal_label} ({xp_to_next_goal} XP to go)",
        inline=False
    )

    await ctx.send(embed=embed)

# ========================
# LEADERBOARDS
# ========================

@bot.command(name="lb")
async def leaderboard(ctx, category: str):
    category = category.lower()

    # Ensure all members exist in DB
    for member in ctx.guild.members:
        if not member.bot:
            get_user(member.id)

    if category == "global":
        cursor.execute("SELECT user_id, xp FROM users ORDER BY xp DESC")
        results = cursor.fetchall()

        embed = discord.Embed(title="🏆 Global Leaderboard", color=LEADERBOARD_COLORS.get(category, 0xFFFFFF)
    )

        for index, (user_id, xp) in enumerate(results[:10], start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            embed.add_field(name=f"#{index} — {name}", value=f"{xp} XP", inline=False)

        await ctx.send(embed=embed)
        return

    # Map rank name to number
    RANK_LOOKUP = {
        "initiate": 1,
        "explorer": 2,
        "connector": 3,
        "leader": 4,
        "master": 5
    }

    if category not in RANK_LOOKUP:
        await ctx.send("❌ Invalid leaderboard category.")
        return

    rank_number = RANK_LOOKUP[category]
    rank_name = RANKS[rank_number]

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    cursor.execute("""
        SELECT users.user_id, COALESCE(SUM(xp_log.xp), 0) as weekly_xp
        FROM users
        LEFT JOIN xp_log ON users.user_id = xp_log.user_id
            AND xp_log.timestamp >= ?
        WHERE users.rank = ?
        GROUP BY users.user_id
        ORDER BY weekly_xp DESC
    """, (seven_days_ago, rank_number))

    results = cursor.fetchall()

    emoji = RANK_EMOJIS.get(category, "🏆")

    embed = discord.Embed(
        title=f"{emoji} {rank_name} Leaderboard (7 Days)",
        color=LEADERBOARD_COLORS.get(category, 0xFFFFFF)
    )

    for index, (user_id, weekly_xp) in enumerate(results[:10], start=1):
        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else f"User {user_id}"
        embed.add_field(name=f"#{index} — {name}", value=f"{weekly_xp} XP", inline=False)

    await ctx.send(embed=embed)

# ========================
# ADMIN COMMAND
# ========================

@bot.command()
@commands.has_permissions(administrator=True)
async def givexp(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ XP must be positive.")
        return

    get_user(member.id)

    # Get current XP and tier
    cursor.execute("SELECT xp, rank FROM users WHERE user_id = ?", (member.id,))
    user_data = cursor.fetchone()
    old_xp = user_data[0]
    old_rank = user_data[1]
    old_tier = get_tier_from_xp(old_rank, old_xp)

    # Add XP
    add_bonus_xp(member.id, amount)

    # Get new XP, rank, and tier
    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (member.id,))
    new_xp = cursor.fetchone()[0]
    new_rank = get_rank_from_xp(new_xp)
    new_tier = get_tier_from_xp(new_rank, new_xp)

    # Update rank role if rank changed
    if new_rank != old_rank:
        set_rank(member.id, new_rank)
        await assign_rank_role(member, new_rank)

    # Build message
    message_parts = [f"✅ {member.mention} received {amount} XP\nNew Total: {new_xp} XP"]

    if new_rank > old_rank:
        message_parts.append(f"🎉 **RANK UP!** You are now {RANKS[new_rank]}!")
    elif new_tier > old_tier:
        message_parts.append(f"✨ **TIER UP!** You are now {RANKS[new_rank]} — Tier {new_tier}!")

    await ctx.send("\n".join(message_parts))

@bot.command()
@commands.has_permissions(administrator=True)
async def resetxp(ctx, member: discord.Member):
    get_user(member.id)

    cursor.execute(
        "UPDATE users SET xp = 0, rank = 1 WHERE user_id = ?",
        (member.id,)
    )
    conn.commit()

    await assign_rank_role(member, 1)

    await ctx.send(f"⚠️ {member.mention}'s XP and rank have been reset to Initiate.")

# ========================
# START BOT
# ========================

bot.run(os.getenv("DISCORD_TOKEN"))
