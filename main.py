import sqlite3
from datetime import datetime, timedelta
import discord
from discord.ext import commands
import os

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
    last_quest_date TEXT,
    last_command_time TEXT
)
""")
conn.commit()

# ========================
# BOT SETUP
# ========================

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ========================
# GAME DATA
# ========================

QUESTS = {
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

# ========================
# PENDING MOD APPROVALS
# ========================

pending_claims = {}

# ========================
# HELPER FUNCTIONS
# ========================

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)

    return user


def update_xp(user_id, amount):
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()


def get_rank_from_xp(xp):
    if xp >= 500:
        return 3
    elif xp >= 200:
        return 2
    else:
        return 1


def update_rank(user_id, new_rank):
    cursor.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank, user_id))
    conn.commit()


# ========================
# EVENTS
# ========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# ========================
# COMMANDS
# ========================

@bot.command()
async def connector(ctx, quest_number: str):
    if quest_number not in QUESTS["connector"]:
        await ctx.send("❌ Invalid quest number.")
        return

    quest = QUESTS["connector"][quest_number]

    message = await ctx.send(
        f"📜 **Quest Submitted!**\n"
        f"Player: {ctx.author.mention}\n"
        f"Quest: {quest['name']}\n"
        f"Reward: {quest['xp']} XP\n\n"
        f"Waiting for moderator approval..."
    )

    pending_claims[message.id] = {
        "user_id": ctx.author.id,
        "xp": quest["xp"]
    }


@bot.command()
async def xp(ctx):
    user = get_user(ctx.author.id)
    xp = user[1]
    rank_number = user[2]
    streak = user[3]

    rank_name = RANKS.get(rank_number, "Unknown")

    await ctx.send(
        f"📊 **{ctx.author.display_name}'s Profile**\n"
        f"⭐ XP: {xp}\n"
        f"🏅 Rank: {rank_name}\n"
        f"🔥 Streak: {streak}"
    )


# ========================
# REACTION APPROVAL
# ========================

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message = reaction.message

    if message.id not in pending_claims:
        return

    # Only allow moderators to approve
    if not any(role.permissions.manage_guild for role in user.roles):
        return

    claim = pending_claims.pop(message.id)
    user_id = claim["user_id"]
    xp = claim["xp"]

    update_xp(user_id, xp)

    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    total_xp = cursor.fetchone()[0]

    new_rank = get_rank_from_xp(total_xp)
    update_rank(user_id, new_rank)

    rank_name = RANKS.get(new_rank, "Unknown")
    member = message.guild.get_member(user_id)

    await message.channel.send(
        f"✅ **Quest Approved!**\n"
        f"{member.mention} gained **{xp} XP**\n"
        f"⭐ Total XP: {total_xp}\n"
        f"🏅 Rank: **{rank_name}**"
    )


# ========================
# START BOT
# ========================

bot.run(os.getenv("DISCORD_TOKEN"))
