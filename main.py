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

def update_streak(user_id):
    cursor.execute("SELECT last_quest_date, streak FROM users WHERE user_id = ?", (user_id,))
    last_date, streak = cursor.fetchone()
    today = datetime.utcnow().date()

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
    # Removed persistent view to avoid double messages

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    get_user(member.id)

    guild = member.guild

    unranked_role = discord.utils.get(guild.roles, name="Unranked")
    if unranked_role and unranked_role not in member.roles:
        try:
            await member.add_roles(unranked_role)
        except:
            pass

    start_channel = discord.utils.get(guild.text_channels, name="start-here")
    if not start_channel:
        return

    # Prevent duplicate onboarding messages
    async for msg in start_channel.history(limit=50):
        if member.mention in msg.content:
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
# QUEST SYSTEM
# ========================

async def handle_quest(ctx, rank_key, quest_number):
    quest = QUESTS.get(rank_key, {}).get(quest_number)
    if not quest:
        await ctx.send("❌ Invalid quest number.")
        return

    user_id = ctx.author.id
    user = get_user(user_id)
    current_rank = user[2]

    add_xp(user_id, quest["xp"])
    update_streak(user_id)

    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    total_xp = cursor.fetchone()[0]

    new_rank = get_rank_from_xp(total_xp)
    if new_rank > current_rank:
        set_rank(user_id, new_rank)
        await assign_rank_role(ctx.author, new_rank)

    # Only one message per quest
    await ctx.send(
        f"✅ Quest completed!\n"
        f"Quest: {quest['name']}\n"
        f"XP Gained: {quest['xp']}"
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
