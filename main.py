import sqlite3
import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from datetime import datetime, timedelta

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

conn.commit()

# ========================
# BOT SETUP
# ========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot_ready = False

# ========================
# GAME DATA
# ========================

QUESTS = {
    "initiate": {
        "1": {"name": "Smile at 3 people", "xp": 5},
        "2": {"name": "Say hello to 5 people", "xp": 10},
    },
    "connector": {
        "1": {"name": "Smile at 3 people", "xp": 5},
        "2": {"name": "Compliment someone's clothing", "xp": 15},
        "3": {"name": "Ask someone how their day is going", "xp": 30},
        "4": {"name": "Introduce yourself", "xp": 40},
    }
}

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
    timestamp = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO xp_log (user_id, xp, timestamp) VALUES (?, ?, ?)",
        (user_id, amount, timestamp)
    )
    conn.commit()

def update_xp(user_id, amount):
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    log_xp(user_id, amount)

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

async def safe_add_role(member, role):
    try:
        await member.add_roles(role)
        return True
    except discord.Forbidden:
        print(f"❌ Missing permissions to add role {role.name} to {member}")
        return False
    except Exception as e:
        print(f"❌ Role add error: {e}")
        return False

async def safe_remove_role(member, role):
    try:
        await member.remove_roles(role)
        return True
    except discord.Forbidden:
        print(f"❌ Missing permissions to remove role {role.name} from {member}")
        return False
    except Exception as e:
        print(f"❌ Role remove error: {e}")
        return False

async def assign_rank_role(member, rank_number):
    rank_name = RANKS.get(rank_number)
    if not rank_name:
        return

    guild = member.guild
    rank_role = discord.utils.get(guild.roles, name=rank_name)

    if not rank_role:
        print(f"⚠ Rank role '{rank_name}' not found")
        return

    for role in member.roles:
        if role.name in RANKS.values() and role != rank_role:
            await safe_remove_role(member, role)

    if rank_role not in member.roles:
        await safe_add_role(member, rank_role)

def update_streak(user_id):
    cursor.execute("SELECT last_quest_date, streak FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    today = datetime.utcnow().date()
    streak = result[1]
    last_date = result[0]

    if last_date:
        last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
        if today > last_date:
            streak += 1
    else:
        streak = 1

    cursor.execute(
        "UPDATE users SET streak = ?, last_quest_date = ? WHERE user_id = ?",
        (streak, today.isoformat(), user_id)
    )
    conn.commit()
    return streak

# ========================
# EVENTS
# ========================

@bot.event
async def on_ready():
    global bot_ready
    if bot_ready:
        return
    bot_ready = True
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    print(f"👋 New member joined: {member}")

    get_user(member.id)

    guild = member.guild
    unranked_role = discord.utils.get(guild.roles, name="Unranked")

    if not unranked_role:
        print("❌ Unranked role not found")
        return

    added = await safe_add_role(member, unranked_role)

    if not added:
        print("❌ Failed to assign Unranked role")
        return

    start_channel = discord.utils.get(guild.text_channels, name="start-here")

    if not start_channel:
        print("❌ start-here channel not found")
        return

    try:
        await start_channel.send(
            f"👋 Welcome {member.mention}! Please choose your starting level below:",
            view=RankSelectView(member)
        )
    except discord.Forbidden:
        print("❌ Missing permissions to send message in start-here")

# ========================
# RANK SELECTION VIEW
# ========================

class RankSelectView(View):
    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member

    @discord.ui.button(label="🟢 Start as Initiate", style=discord.ButtonStyle.success)
    async def initiate_button(self, interaction: discord.Interaction, button: Button):
        await self.assign_rank(interaction, 1, 0)

    @discord.ui.button(label="🔵 Start as Explorer (100 XP)", style=discord.ButtonStyle.primary)
    async def explorer_button(self, interaction: discord.Interaction, button: Button):
        await self.assign_rank(interaction, 2, 100)

    async def assign_rank(self, interaction, rank_number, bonus_xp):
        if interaction.user != self.member:
            await interaction.response.send_message(
                "❌ This selection is not for you.", ephemeral=True
            )
            return

        guild = interaction.guild
        unranked_role = discord.utils.get(guild.roles, name="Unranked")

        if unranked_role:
            await safe_remove_role(self.member, unranked_role)

        set_rank(self.member.id, rank_number)

        if bonus_xp > 0:
            update_xp(self.member.id, bonus_xp)

        await assign_rank_role(self.member, rank_number)

        await interaction.response.send_message(
            f"✅ You are now an **{RANKS[rank_number]}**! Your journey begins now.",
            ephemeral=True
        )

        tutorial_channel = discord.utils.get(guild.text_channels, name="tutorial")
        if tutorial_channel:
            await tutorial_channel.send(
                f"🎓 Welcome {self.member.mention}! Here's how to get started:\n\n"
                "🔹 Complete quests: `!initiate 1`\n"
                "🔹 Check your progress: `!progress`\n"
                "🔹 View leaderboards: `!lb global`\n\n"
                "Start with your first quest today!"
            )

# ========================
# QUEST SYSTEM
# ========================

async def handle_quest(ctx, rank_key, quest_number):
    if quest_number not in QUESTS[rank_key]:
        await ctx.send("❌ Invalid quest number.")
        return

    quest = QUESTS[rank_key][quest_number]
    user_id = ctx.author.id

    get_user(user_id)
    update_xp(user_id, quest["xp"])
    streak = update_streak(user_id)

    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    total_xp = cursor.fetchone()[0]

    new_rank = get_rank_from_xp(total_xp)
    set_rank(user_id, new_rank)
    await assign_rank_role(ctx.author, new_rank)

    await ctx.send(
        f"✅ Quest completed! **{quest['name']}**\n"
        f"Reward: {quest['xp']} XP\n"
        f"Total XP: {total_xp}\n"
        f"Rank: {RANKS[new_rank]}\n"
        f"Streak: {streak}"
    )

@bot.command()
async def initiate(ctx, quest_number: str):
    await handle_quest(ctx, "initiate", quest_number)

@bot.command()
async def connector(ctx, quest_number: str):
    await handle_quest(ctx, "connector", quest_number)

# ========================
# PROFILE
# ========================

@bot.command()
async def progress(ctx):
    user = get_user(ctx.author.id)
    xp = user[1]
    rank_number = user[2]
    streak = user[3]

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
# START BOT
# ========================

bot.run(os.getenv("DISCORD_TOKEN"))
