import sqlite3
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import os
from datetime import datetime, timedelta
import random
from zoneinfo import ZoneInfo

# ========================
# DATABASE SETUP
# ========================

conn = sqlite3.connect("bot.db")
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

conn.commit()

# ========================
# BOT SETUP
# ========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

ALLOWED_QUEST_CHANNELS = ["quests", "quest-log"]

# ========================
# RANK DATA
# ========================

RANKS = {
    1: "Initiate",
    2: "Explorer",
    3: "Connector",
    4: "Leader",
    5: "Mentor"
}

RANK_LOOKUP = {
    "initiate": 1,
    "explorer": 2,
    "connector": 3,
    "leader": 4,
    "mentor": 5
}

# ========================
# QUEST POOLS
# ========================

QUEST_POOLS = {
    "initiate_1": [
        "Smile at 5 people.",
        "Say “Hi” or “Good morning” to 3 people.",
        "Make eye contact with 5 strangers."
    ],
    "initiate_2": [
        "Sit in a public place for 10 minutes with no phone.",
        "Walk through a busy street for 10 minutes without headphones.",
        "Compliment someone’s clothing.",
        "Read or write for 15 minutes in a public place.",
        "Write 5 sentences about how you felt being around people today.",
        "Use someone’s name after they introduce themselves.",
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
        "Ask someone what they’re reading.",
        "Ask someone about a good place to go nearby.",
        "Ask a stranger for directions (even if you know).",
        "Ask someone their weekend plans."
    ],
    "connector_1": [
        "Learn someone’s name",
        "Give 3 compliments to strangers.",
        "Catch up with an acquaintance."
    ],
    "connector_2": [
        "Insert yourself into an existing group conversation.",
        "Share a small personal truth with someone new.",
        "Sit next to a stranger and start a conversation.",
        "Invite someone for a short coffee.",
        "Give a compliment about someone’s personality.",
        "Ask someone new about their passions.",
        "Tell a new short personal story to someone."
    ],
    "leader_1": [
        "Start 3 conversations.",
        "Lead a group conversation.",
        "Give 3 compliments about a person’s energy or personality."
    ],
    "leader_2": [
        "Bring two people together who don’t know each other.",
        "Get to know someone over coffee or a walk.",
        "Learn the names of 3 new people in one day.",
        "Stand alone in a busy place for 10 minutes with no phone.",
        "Ask a group a meaningful question.",
        "Reflect back someone’s feelings in a conversation.",
        "Sit next to a stranger and start a conversation."
    ]
}

WEEKLY_QUESTS = {
    "initiate": (20, [
        "Ask someone about their day.",
        "Ask someone what the time is."
    ]),
    "explorer": (40, [
        "End a conversation early, but confidently and politely.",
        "Introduce yourself to someone new.",
        "In an awkward silence, stay present and let others fill the silence."
    ]),
    "connector": (60, [
        "Ask for someone’s contact details.",
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
    "mentor": (80, [
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
        (user_id, amount, datetime.utcnow().isoformat())
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
    if xp >= 1000:
        return 5
    elif xp >= 600:
        return 4
    elif xp >= 300:
        return 3
    elif xp >= 100:
        return 2
    else:
        return 1

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

def generate_daily_quests():
    today = today_est()
    cursor.execute("DELETE FROM daily_quest_rotation WHERE date != ?", (today,))

    for key, pool in QUEST_POOLS.items():
        chosen = random.choice(pool)
        xp = XP_VALUES[key]

        cursor.execute("""
            INSERT INTO daily_quest_rotation (rank, quest_key, quest_name, xp, date)
            VALUES (?, ?, ?, ?, ?)
        """, (key.split("_")[0], key, chosen, xp, today))

    conn.commit()

def generate_weekly_quests():
    week = week_start_est()
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
# DAILY SCHEDULER
# ========================

@tasks.loop(minutes=60)
async def daily_reset_task():
    generate_daily_quests()
    generate_weekly_quests()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    daily_reset_task.start()
    generate_daily_quests()
    generate_weekly_quests()

# ========================
# QUEST COMMANDS
# ========================

async def quest_command(ctx, quest_key):
    if ctx.channel.name not in ALLOWED_QUEST_CHANNELS:
        await ctx.send("❌ Quest commands can only be used in quest channels.")
        return

    cursor.execute("""
        SELECT quest_name, xp FROM daily_quest_rotation
        WHERE quest_key = ? AND date = ?
    """, (quest_key, today_est()))

    result = cursor.fetchone()
    if not result:
        await ctx.send("❌ This quest is not available today.")
        return

    quest_name, xp = result

    if has_claimed(ctx.author.id, quest_key):
        await ctx.send("❌ You have already completed this quest today.")
        return

    get_user(ctx.author.id)
    add_xp(ctx.author.id, xp)
    claim_quest(ctx.author.id, quest_key)

    await ctx.send(
        f"✅ Quest completed!\n"
        f"Quest: {quest['name']}\n"
        f"XP Gained: {quest['xp']}"
    )

# Initiate
@bot.command()
async def initiate1(ctx):
    await quest_command(ctx, "initiate_1")

@bot.command()
async def initiate2(ctx):
    await quest_command(ctx, "initiate_2")

# Explorer
@bot.command()
async def explorer1(ctx):
    await quest_command(ctx, "explorer_1")

@bot.command()
async def explorer2(ctx):
    await quest_command(ctx, "explorer_2")

# Connector
@bot.command()
async def connector1(ctx):
    await quest_command(ctx, "connector_1")

@bot.command()
async def connector2(ctx):
    await quest_command(ctx, "connector_2")

# Leader
@bot.command()
async def leader1(ctx):
    await quest_command(ctx, "leader_1")

@bot.command()
async def leader2(ctx):
    await quest_command(ctx, "leader_2")

# ========================
# STREAK HANDLING
# ========================

def update_streak(user_id):
    cursor.execute("SELECT last_quest_date, streak FROM users WHERE user_id = ?", (user_id,))
    last_date, streak = cursor.fetchone()
    today = datetime.utcnow().date()

    if last_date:
        last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
        delta_days = (today - last_date).days

        if delta_days == 1:
            # consecutive day, increment streak
            streak += 1
        elif delta_days > 1:
            # missed one or more days, reset streak
            streak = 0
        # if delta_days == 0: same day, streak doesn't change
    else:
        # first quest ever
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
        await self.assign_rank(interaction, 2, 100)

    async def assign_rank(self, interaction: discord.Interaction, rank_number, bonus_xp):
        if interaction.user.id != self.member_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return

        await interaction.response.defer()

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
    print(f"✅ Logged in as {bot.user}")
    bot.add_view(RankSelectView(0))

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
# PROFILE
# ========================

@bot.command()
async def progress(ctx):
    user = get_user(ctx.author.id)
    xp, rank_number, streak = user[1], user[2], user[3]

    await ctx.send(
        f"📊 **{ctx.author.display_name}'s Stats**\n"
        f"XP: {xp}\n"
        f"Rank: {RANKS[rank_number]}\n"
        f"Streak: {streak}"
    )

# ========================
# LEADERBOARDS
# ========================

@bot.command(name="lb")
async def leaderboard(ctx, category: str):
    category = category.lower()

    for member in ctx.guild.members:
        if not member.bot:
            get_user(member.id)

    if category == "global":
        cursor.execute("SELECT user_id, xp FROM users ORDER BY xp DESC")
        results = cursor.fetchall()

        embed = discord.Embed(title="🏆 Global Leaderboard", color=0xFFD700)

        for index, (user_id, xp) in enumerate(results[:10], start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            embed.add_field(name=f"#{index} — {name}", value=f"{xp} XP", inline=False)

        await ctx.send(embed=embed)
        return

    if category not in RANK_LOOKUP:
        await ctx.send("❌ Invalid leaderboard category.")
        return

    rank_number = RANK_LOOKUP[category]
    rank_name = RANKS[rank_number]

    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

    cursor.execute("""
        SELECT users.user_id, COALESCE(SUM(xp_log.xp), 0) as weekly_xp
        FROM users
        LEFT JOIN xp_log ON users.user_id = xp_log.user_id AND xp_log.timestamp >= ?
        WHERE users.rank = ?
        GROUP BY users.user_id
        ORDER BY weekly_xp DESC
    """, (seven_days_ago, rank_number))

    results = cursor.fetchall()

    embed = discord.Embed(title=f"🏆 {rank_name} Leaderboard (7 Days)", color=0x00FFAA)

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
    add_bonus_xp(member.id, amount)

    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (member.id,))
    total_xp = cursor.fetchone()[0]

    new_rank = get_rank_from_xp(total_xp)
    set_rank(member.id, new_rank)
    await assign_rank_role(member, new_rank)

    await ctx.send(
        f"✅ {member.mention} received {amount} XP\n"
        f"New Total: {total_xp} XP\n"
        f"New Rank: {RANKS[new_rank]}"
    )

@givexp.error
async def givexp_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have permission to use this command.")

# ========================
# START BOT
# ========================

bot.run(os.getenv("DISCORD_TOKEN"))
