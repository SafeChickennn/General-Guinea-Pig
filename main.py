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

user_xp = {}

def get_level(xp):
    if xp >= 500:
        return "Connector"
    elif xp >= 200:
        return "Explorer"
    else:
        return "Initiate"


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
        f"📜 **Quest Claim Submitted**\n"
        f"Player: {ctx.author.mention}\n"
        f"Quest: {quest['name']}\n"
        f"Reward: {quest['xp']} XP\n\n"
        f"Awaiting moderator approval..."
    )

    pending_claims[message.id] = {
        "user_id": ctx.author.id,
        "xp": quest["xp"]
    }

    await message.add_reaction("✅")


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

    user_xp[user_id] = user_xp.get(user_id, 0) + xp
    level = get_level(user_xp[user_id])

    member = message.guild.get_member(user_id)

    await message.channel.send(
        f"✅ **Quest Approved!**\n"
        f"{member.mention} gained **{xp} XP**\n"
        f"Total XP: {user_xp[user_id]}\n"
        f"Current Rank: **{level}**"
    )


bot.run(os.getenv("DISCORD_TOKEN"))
