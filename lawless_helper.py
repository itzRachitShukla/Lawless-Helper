<<<<<<< HEAD
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
=======
import discord
from discord.ext import commands
from discord import app_commands
import re
import random
import json
import asyncio
import os
from datetime import datetime
import sys 
sys.stdout.reconfigure(encoding='utf-8')


token = "" # ⚠️ Never share this publicly
bot = commands.Bot(command_prefix="?", intents=discord.Intents.all())
level_up_channel = None
REQUIRED_ROLE_ID = 1423163442319200256
ROLE_DATA_FILE = "temp_roles.json"


# ---------------- JSON DATA HANDLING ----------------
def load_data():
    """Loads the JSON file that stores temporary role data."""
    if not os.path.exists(ROLE_DATA_FILE):
        with open(ROLE_DATA_FILE, "w") as f:
            json.dump({}, f)
    with open(ROLE_DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_data(data):
    """Saves temporary role data back to the JSON file."""
    with open(ROLE_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ---------------- ROLE RESTORATION ON STARTUP ----------------
async def restore_roles_on_startup():
    """Restores valid temporary roles and removes expired ones on startup."""
    data = load_data()
    now = datetime.utcnow().timestamp()
    changed = False

    for user_id, info in list(data.items()):
        if not isinstance(info, dict) or "role_id" not in info or "expires_at" not in info:
            print(f"⚠️ Skipping invalid data for user {user_id}")
            del data[user_id]
            changed = True
            continue

        role_id = info["role_id"]
        expires_at = info["expires_at"]
        member_found = False

        for guild in bot.guilds:
            member = guild.get_member(int(user_id))
            role = guild.get_role(role_id)
            if member and role:
                member_found = True

                if expires_at <= now:
                    if role in member.roles:
                        await member.remove_roles(role)
                        try:
                            await member.send(f"⌛ Your **{role.name}** role has expired.")
                        except:
                            pass
                    del data[user_id]
                    changed = True
                else:
                    delay = expires_at - now
                    asyncio.create_task(remove_role_later(member, role, delay))
                break

        if not member_found:
            del data[user_id]
            changed = True

    if changed:
        save_data(data)


# ---------------- ROLE REMOVAL ----------------
async def remove_role_later(member, role, delay):
    """Waits for a delay, then removes the role from the member."""
    await asyncio.sleep(delay)
    if role in member.roles:
        await member.remove_roles(role)
        try:
            await member.send(f"⌛ Your **{role.name}** role has expired.")
        except:
            pass
    data = load_data()
    if str(member.id) in data:
        del data[str(member.id)]
        save_data(data)


# ---------------- BOT READY EVENT ----------------
@bot.event
async def on_ready():
    global level_up_channel
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} slash commands.")
        level_up_channel = bot.get_channel(1387056580578512967)
        await restore_roles_on_startup()
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


# ---------------- MESSAGE EVENT ----------------
@bot.event
async def on_message(msg):
    global level_up_channel
    if msg.content == '.guild icon':
        await msg.channel.send(msg.guild.icon.url)

    if msg.author.id != 691713521007984681 or msg.channel.id != 1396101528477106176:
        await bot.process_commands(msg)
        return

    if not msg.mentions:
        await bot.process_commands(msg)
        return

    user = msg.mentions[0]
    level_m = re.search(r"level\s+\**(\d+)\**", msg.content, flags=re.IGNORECASE)
    level = int(level_m.group(1)) if level_m else None

    embed = discord.Embed(
        title=f"{user.display_name} has leveled up!",
        description=(f"Congrats, {user.mention} you are now level {level}!"
                     if level is not None else f"Congrats, {user.mention}!")
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    if msg.guild and msg.guild.icon:
        embed.set_footer(text=msg.guild.name, icon_url=msg.guild.icon.url)

    await level_up_channel.send(content=user.mention, embed=embed)
    await bot.process_commands(msg)


# ---------------- SPECIAL ROLE COMMAND ----------------
@bot.command()
async def special(ctx):
    """Main command that handles random temporary role assignment."""
    user = ctx.author
    guild = ctx.guild

    required_role = guild.get_role(REQUIRED_ROLE_ID)
    if not required_role or required_role not in user.roles:
        return await ctx.send("❌ You are missing <@&1423163442319200256>, purchase it from <#1388210679886119052>!")

    await user.remove_roles(required_role)
    await ctx.send(f"🔒 {user.mention}, your access role has been consumed. Rolling...")

    if random.random() > 0.10:
        return await ctx.send("💤 You didn’t win a special role this time. Try again later!")

    valid_roles = [r for r in bot.list if r != 0]
    chosen_role_id = random.choice(valid_roles)
    chosen_role = guild.get_role(chosen_role_id)
    if not chosen_role:
        return await ctx.send("⚠️ Could not find the chosen role on this server.")

    for r_id in valid_roles:
        r = guild.get_role(r_id)
        if r and r in user.roles:
            await user.remove_roles(r)
            await ctx.send(f"❌ Removed your previous special role: **{r.name}**")

    await user.add_roles(chosen_role)
    await ctx.send(f"🎉 Congrats! You got **{chosen_role.name}** for 7 days!")

    expires_at = datetime.utcnow().timestamp() + 7 * 24 * 60 * 60
    data = load_data()
    data[str(user.id)] = {
        "role_id": chosen_role_id,
        "expires_at": expires_at
    }
    save_data(data)
    asyncio.create_task(remove_role_later(user, chosen_role, 7 * 24 * 60 * 60))


# ---------------- SLASH COMMAND: ROLES WITH PERM ----------------
PERMISSIONS_LIST = list(discord.Permissions.VALID_FLAGS.keys())

# ✅ Safe async autocomplete
async def permission_autocomplete(interaction: discord.Interaction, current: str):
    # Filter permissions based on user input (case-insensitive)
    filtered = [
        app_commands.Choice(
            name=perm.replace("_", " ").title(),  # prettier display
            value=perm
        )
        for perm in PERMISSIONS_LIST
        if current.lower() in perm.lower()
    ]
    return filtered[:25]  # Discord only allows max 25 choices


class RemovePermView(discord.ui.View):
    def __init__(self, roles, role_perm):
        super().__init__(timeout=None)
        self.roles = roles
        self.role_perm = role_perm

    @discord.ui.button(label="🗑 Remove Permission from All", style=discord.ButtonStyle.danger)
    async def remove_perm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        removed_count = 0
        failed_count = 0

        await interaction.response.defer(thinking=True, ephemeral=True)

        for role in self.roles:
            try:
                perms = role.permissions
                if getattr(perms, self.role_perm, False):
                    setattr(perms, self.role_perm, False)
                    await role.edit(permissions=perms, reason=f"Removed {self.role_perm} via bot command")
                    removed_count += 1
            except discord.Forbidden:
                failed_count += 1
            except Exception:
                failed_count += 1

        msg = f"✅ Removed `{self.role_perm}` from **{removed_count}** roles."
        if failed_count > 0:
            msg += f"\n⚠️ Failed to edit **{failed_count}** roles (insufficient permissions)."

        await interaction.followup.send(msg, ephemeral=True)


@bot.tree.command(
    name="roles_with_perm",
    description="Get all roles that have a specific permission."
)
@app_commands.describe(role_perm="Choose the permission to check for")
@app_commands.autocomplete(role_perm=permission_autocomplete)
async def roles_with_perm(interaction: discord.Interaction, role_perm: str):
    guild = interaction.guild

    if guild is None:
        return await interaction.response.send_message(
            "❌ This command can only be used inside a server.",
            ephemeral=True
        )

    roles_with_permission = [
        role for role in guild.roles if getattr(role.permissions, role_perm, False)
    ]

    if not roles_with_permission:
        await interaction.response.send_message(
            f"⚠️ No roles found with `{role_perm}` permission.",
            ephemeral=True
        )
        return

    roles_text = "\n".join(f"<@&{role.id}> ({role.id})" for role in roles_with_permission)
    view = RemovePermView(roles_with_permission, role_perm)

    await interaction.response.send_message(
        f"✅ Roles with `{role_perm}` permission:\n{roles_text}",
        view=view,
        ephemeral=False
    )

@bot.command()
@commands.is_owner()
async def boot(ctx):
    print("Booting the Systum.")
    await bot.close()
# ---------------- RUN BOT ----------------
bot.run(token)

>>>>>>> ed9f5e7224a7da3fb77e571548fc23a84465878b
