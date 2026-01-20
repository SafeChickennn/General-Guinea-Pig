import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    streak INTEGER DEFAULT 0,
    last_quest_date TEXT,
    last_command_time TEXT
)
""")
conn.commit()

import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Temporary in-memory storage
pending_claims = {}

QUESTS = {
    "connector": {
        "1": {"name": "Smile at 3 people", "xp": 5},
        "2": {"name": "Compliment someone's clothing", "xp": 15},
        "3": {"name": "Ask someone how their day is going", "xp": 30},
        "4": {"name": "Introduce yourself", "xp": 40},
    }
}

def get_level(xp):
    if xp >= 500:
        return "Connector"
    elif xp >= 200:
        return "Explorer"
    else:
        return "Initiate"

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        return get_user(user_id)

    return user


def update_xp(user_id, amount):
    cursor.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()


def set_last_command_time(user_id, time_str):
    cursor.execute("UPDATE users SET last_command_time = ? WHERE user_id = ?", (time_str, user_id))
    conn.commit()


def get_last_command_time(user_id):
    cursor.execute("SELECT last_command_time FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def connector(ctx, quest_number: str):
    if quest_number not in QUESTS["connector"]:
        await ctx.send("Invalid quest number.")
        return

    quest = QUESTS["connector"][quest_number]

    message = await ctx.send(
        f"📜 **Quest Completed!**\n"
        f"Player: {ctx.author.mention}\n"
        f"Quest: {quest['name']}\n"
        f"Reward: {quest['xp']} XP\n\n"
    )

    pending_claims[message.id] = {
        "user_id": ctx.author.id,
        "xp": quest["xp"]
    }

@bot.command()
async def xp(ctx):
    user = get_user(ctx.author.id)
    xp = user[1]
    level = user[2]
    streak = user[3]

    await ctx.send(
        f"📊 **{ctx.author.display_name}'s Profile**\n"
        f"⭐ XP: {xp}\n"
        f"🏅 Level: {level}\n"
        f"🔥 Streak: {streak}"
    )


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

    level = get_level(total_xp)


    member = message.guild.get_member(user_id)

    await message.channel.send(
        f"✅ **Quest Approved!**\n"
        f"{member.mention} gained **{xp} XP**\n"
        f"Total XP: {user_xp[user_id]}\n"
        f"Current Rank: **{level}**"
    )


bot.run(os.getenv("DISCORD_TOKEN"))
