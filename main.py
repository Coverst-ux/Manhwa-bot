import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import traceback

# ------------------------
# Setup
# ------------------------
load_dotenv()
TOKEN = os.getenv("TOKEN")

DEV_MODE = True  # ✅ Set to False when deploying globally

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------
# Cogs
# ------------------------
initial_extensions = [
    "cogs.Owner_Commands",
    "cogs.Comick_API",
    "cogs.API_Slash",
    "cogs.Tracking"
]

async def load_cogs():
    for ext in initial_extensions:
        try:
            await bot.load_extension(ext)
            print(f"✅ Loaded {ext}")
        except Exception as e:
            print(f"❌ Failed to load {ext}: {e}")
            traceback.print_exc()

# ------------------------
# Events
# ------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")

    await asyncio.sleep(2)

    print("\n[DEBUG] Commands loaded in tree:")
    for cmd in bot.tree.get_commands():
        cog_name = cmd.binding.__class__.__name__ if cmd.binding else "None"
        print(f"  - /{cmd.name} (from {cog_name})")

    guild = discord.Object(id=1432282882952527902)

    try:
        # REMOVE copy_global_to() - it's bringing back old command definition   s
        synced = await bot.tree.sync(guild=guild)
        print(f"✅ Synced {len(synced)} command(s) to guild")
    except Exception as e:
        print(f"⚠️ Failed to sync commands: {e}")
        traceback.print_exc()

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.reading, name="Novels")
    )

    print("✅ Bot is fully ready.\n")

# ------------------------
# Main
# ------------------------
async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
