# bot.py
import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

INTENTS = discord.Intents.all()
BOT_PREFIX = "?"

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=BOT_PREFIX, intents=INTENTS)
        self.level_up_channel_id = 1387056580578512967  # keep this if you use it; adjust if needed
        self.level_up_channel = None

    async def setup_hook(self):
        # load all cogs in cogs/ folder that end with _cog.py
        for filename in os.listdir("cogs"):
            if filename.endswith("_cog.py"):
                name = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(name)
                    print(f"Loaded extension: {name}")
                except Exception as e:
                    print(f"Failed to load extension {name}: {e}")

        # sync application commands after loading cogs
        try:
            synced = await self.tree.sync()
            print(f"🔁 Synced {len(synced)} application (slash) commands.")
            # diagnostic: show which extensions are loaded
            print("Currently loaded extensions:", list(self.extensions.keys()))

        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"✅ Logged in as {self.user} ({self.user.id})")
        self.level_up_channel = self.get_channel(self.level_up_channel_id)

bot = MyBot()

# keep owner-only boot command here (or move to a cog)
@bot.command()
@commands.is_owner()
async def boot(ctx):
    print("Booting the Systum.")
    try:
        await bot.close()
    except Exception as e: 
        print(e)

@bot.event 
async def on_message(message): 
    if message.author.id == 426019189174829056 and message.content.lower() == "hi dost": 
        await message.reply("Hi Dost")
        
    await bot.process_commands(message)

if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Error: BOT_TOKEN environment variable not set. Set it and restart.")
        raise SystemExit(1)
    bot.run(token)
