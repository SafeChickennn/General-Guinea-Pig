import sqlite3
import discord
from discord.ext import commands
import os
from datetime import datetime

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
    rank_name = RANKS.get(rank_number)

    if not rank_name:
        return

    guild = member.guild
    rank_role = discord.utils.get(guild.roles, name=rank_name)

    if not rank_role:
        print(f"Role '{rank_name}' not found in server.")
        return

    # Remove any other rank roles
    for role in member.roles:
        if role.name in RANKS.values() and role != rank_role:
            await member.remove_roles(role)

    # Add correct rank role
    if rank_role not in member.roles:
        await member.add_roles(rank_role)


# ========================
# EVENTS
# ========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Ensure all members have a rank
    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue

            user = get_user(member.id)
            xp = user[1]
            rank_number = get_rank_from_xp(xp)
            set_rank(member.id, rank_number)
            await assign_rank_role(member, rank_number)


@bot.event
async def on_member_join(member):
    if member.bot:
        return

    get_user(member.id)
    await assign_rank_role(member, 1)


# ========================
# COMMANDS
# ========================

@bot.command()
async def connector(ctx, quest_number: str):
    if quest_number not in QUESTS["connector"]:
        await ctx.send("❌ Invalid quest number.")
        return

    quest = QUESTS["connector"][quest_number]
    user_id = ctx.author.id

    # Add XP
    update_xp(user_id, quest["xp"])

    # Fetch updated user
    cursor.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    total_xp = cursor.fetchone()[0]

    # Update rank
    new_rank = get_rank_from_xp(total_xp)
    set_rank(user_id, new_rank)
    await assign_rank_role(ctx.author, new_rank)

    rank_name = RANKS.get(new_rank, "Unknown")

    await ctx.send(
        f"✅ **Quest Completed!**\n"
        f"Player: {ctx.author.mention}\n"
        f"Quest: {quest['name']}\n"
        f"Reward: {quest['xp']} XP\n"
        f"⭐ Total XP: {total_xp}\n"
        f"🏅 Rank: {rank_name}"
    )


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
# START BOT
# ========================

bot.run(os.getenv("DISCORD_TOKEN"))
