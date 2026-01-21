import sqlite3
import discord
from discord.ext import commands
from discord.ui import View, Button
import os
from datetime import datetime, timedelta

# ========================
# DATABASE
# ========================

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    rank INTEGER DEFAULT 1,
    streak INTEGER DEFAULT 0,
    last_quest_date TEXT,
    onboarding_complete INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS xp_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    xp INTEGER,
    timestamp TEXT,
    source TEXT
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
            "INSERT INTO users (user_id, xp, rank, streak, onboarding_complete) VALUES (?, 0, 1, 0, 0)",
            (user_id,)
        )
        conn.commit()
        return get_user(user_id)

    return user

def log_xp(user_id, amount, source):
    cursor.execute(
        "INSERT INTO xp_log (user_id, xp, timestamp, source) VALUES (?, ?, ?, ?)",
        (user_id, amount, datetime.utcnow().isoformat(), source)
    )
    conn.commit()

def add_xp(user_id, amount, source="quest"):
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    log_xp(user_id, amount, source)

def set_rank(user_id, rank):
    cursor.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank, user_id))
    conn.commit()

def complete_onboarding(user_id):
    cursor.execute("UPDATE users SET onboarding_complete = 1 WHERE user_id = ?", (user_id,))
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
        await member.remove_roles(unranked_role)

    for role in member.roles:
        if role.name in RANKS.values() and role.name != rank_name:
            await member.remove_roles(role)

    if rank_role and rank_role not in member.roles:
        await member.add_roles(rank_role)

def update_streak(user_id):
    cursor.execute("SELECT last_quest_date, streak FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    today = datetime.utcnow().date()

    if row[0]:
        last_date = datetime.strptime(row[0], "%Y-%m-%d").date()
        streak = row[1] + 1 if today > last_date else row[1]
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
            add_xp(member.id, bonus_xp, source="onboarding")

        complete_onboarding(member.id)
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
    bot.add_view(RankSelectView(0))  # Persistent buttons

@bot.event
async def on_member_join(member):
    if member.bot:
        return

    get_user(member.id)

    guild = member.guild

    unranked_role = discord.utils.get(guild.roles, name="Unranked")
    if unranked_role:
        await member.add_roles(unranked_role)

    start_channel = discord.utils.get(guild.text_channels, name="start-here")
    if not start_channel:
        return

    view = RankSelectView(member.id)

    await start_channel.send(
        f"👋 Welcome {member.mention} to the Social Guinea Pigs!\n\n"
        "This server is a real-world social confidence game. You complete daily challenges, "
        "earn XP, rank up, and build confidence step by step.\n\n"
        "Choose your starting path:\n"
        "🟢 Initiate — slower, gentler challenges\n"
        "🔵 Explorer — confident starter path",
        view=view
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

    user = get_user(user_id)
    current_rank = user[2]

    add_xp(user_id, quest["xp"], source="quest")
    update_streak(user_id)

    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    total_xp = cursor.fetchone()[0]

    xp_rank = get_rank_from_xp(total_xp)

    if xp_rank > current_rank:
        set_rank(user_id, xp_rank)
        await assign_rank_role(ctx.author, xp_rank)

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
# ADMIN
# ========================

@bot.command()
@commands.has_permissions(administrator=True)
async def givexp(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ XP must be positive.")
        return

    get_user(member.id)
    add_xp(member.id, amount, source="admin")

    cursor.execute("SELECT xp, rank FROM users WHERE user_id = ?", (member.id,))
    total_xp, current_rank = cursor.fetchone()

    xp_rank = get_rank_from_xp(total_xp)

    if xp_rank > current_rank:
        set_rank(member.id, xp_rank)
        await assign_rank_role(member, xp_rank)

    await ctx.send(
        f"✅ {member.mention} received {amount} XP\n"
        f"New Total: {total_xp} XP\n"
        f"Rank: {RANKS[max(current_rank, xp_rank)]}"
    )

# ========================
# START
# ========================

bot.run(os.getenv("DISCORD_TOKEN"))
