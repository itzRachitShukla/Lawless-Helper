# cogs/roles_cog.py
import discord
from discord.ext import commands
import asyncio
import json
import os
import re
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

# Put role IDs you want to be possible "special roles" here
SPECIAL_ROLE_IDS = [
    # example: 111111111111111111,
    # 222222222222222222,
]
REQUIRED_ROLE_ID = 1423163442319200256  # ID required to use the special command
ROLE_DATA_FILE = Path("temp_roles.json")  # stored in bot's working directory
LEVEL_UP_CHANNEL_ID = 1387056580578512967  # channel where level up embeds are sent
LEVEL_UP_FORWARD_AUTHOR_ID = 691713521007984681
LEVEL_UP_FORWARD_CHANNEL_ID = 1396101528477106176

def load_data() -> dict:
    if not ROLE_DATA_FILE.exists():
        ROLE_DATA_FILE.write_text("{}", encoding="utf-8")
    try:
        return json.loads(ROLE_DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

def save_data(data: dict) -> None:
    ROLE_DATA_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


class RolesCog(commands.Cog, name="roles"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # start deferred startup task
        self.bot.loop.create_task(self._deferred_startup())

    async def _deferred_startup(self):
        await self.bot.wait_until_ready()
        await self.restore_roles_on_startup()

    # ---------------- ROLE RESTORE & SCHEDULING ----------------
    async def restore_roles_on_startup(self):
        data = load_data()
        now = datetime.utcnow().timestamp()
        changed = False

        for user_id, info in list(data.items()):
            if not isinstance(info, dict) or "role_id" not in info or "expires_at" not in info:
                print(f"⚠️ Skipping invalid entry for user {user_id}")
                data.pop(user_id, None)
                changed = True
                continue

            role_id = info["role_id"]
            expires_at = info["expires_at"]
            member_found = False

            for guild in self.bot.guilds:
                member = guild.get_member(int(user_id))
                role = guild.get_role(role_id)
                if member and role:
                    member_found = True
                    if expires_at <= now:
                        # already expired: try to remove immediately
                        try:
                            if role in member.roles:
                                await member.remove_roles(role)
                                try:
                                    await member.send(f"⌛ Your **{role.name}** role has expired.")
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        data.pop(user_id, None)
                        changed = True
                    else:
                        delay = expires_at - now
                        # schedule removal
                        asyncio.create_task(self._remove_role_later(member, role, delay))
                    break

            if not member_found:
                # user not in any guild the bot is in -> clean up
                data.pop(user_id, None)
                changed = True

        if changed:
            save_data(data)

    async def _remove_role_later(self, member: discord.Member, role: discord.Role, delay: float):
        await asyncio.sleep(delay)
        try:
            if role in member.roles:
                await member.remove_roles(role)
                try:
                    await member.send(f"⌛ Your **{role.name}** role has expired.")
                except Exception:
                    pass
        except Exception:
            pass

        # cleanup persisted data
        data = load_data()
        data.pop(str(member.id), None)
        save_data(data)

    # ---------------- LISTENER: ON_MESSAGE (level up forward + .guild icon) ----------------
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # respond to .guild icon
        if msg.content == ".guild icon":
            if msg.guild and msg.guild.icon:
                await msg.channel.send(msg.guild.icon.url)
            return

        # special forwarding behavior (preserve original checks)
        if msg.author.id == LEVEL_UP_FORWARD_AUTHOR_ID and msg.channel.id == LEVEL_UP_FORWARD_CHANNEL_ID:
            if not msg.mentions:
                await self.bot.process_commands(msg)
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

            level_up_ch = self.bot.get_channel(LEVEL_UP_CHANNEL_ID)
            if level_up_ch:
                pass
            #    await level_up_ch.send(content=user.mention, embed=embed)
            

           
            

        # ensure commands still process in other cases

    # ---------------- COMMAND: special ----------------
    @commands.command(name="special")
    async def special(self, ctx: commands.Context):
        """
        Main command that handles random temporary role assignment.
        User must have REQUIRED_ROLE_ID (consumed on use).
        """
        user = ctx.author
        guild = ctx.guild
        if guild is None:
            return await ctx.send("This command can only be used in a server.")

        required_role = guild.get_role(REQUIRED_ROLE_ID)
        if required_role is None or required_role not in user.roles:
            return await ctx.send(f"❌ You are missing <@&{REQUIRED_ROLE_ID}>, purchase it from <#1388210679886119052>!")

        # consume the access role
        try:
            await user.remove_roles(required_role)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to remove that role.")
        except Exception as e:
            return await ctx.send(f"⚠️ Error removing required role: {e}")

        await ctx.send(f"🔒 {user.mention}, your access role has been consumed. Rolling...")

        # 10% chance to win
        if random.random() > 0.10:
            return await ctx.send("💤 You didn’t win a special role this time. Try again later!")

        # pick a special role id from configured list
        if not SPECIAL_ROLE_IDS:
            return await ctx.send("⚠️ No special roles were configured. Ask an admin to configure `SPECIAL_ROLE_IDS`.")
        # filter to roles that exist in this guild
        valid_roles = [guild.get_role(rid) for rid in SPECIAL_ROLE_IDS]
        valid_roles = [r for r in valid_roles if r is not None]

        if not valid_roles:
            return await ctx.send("⚠️ None of the configured special roles exist on this server.")

        chosen_role = random.choice(valid_roles)

        # remove any previous special roles the user has (only among configured special roles)
        for r in valid_roles:
            if r in user.roles:
                try:
                    await user.remove_roles(r)
                    await ctx.send(f"❌ Removed your previous special role: **{r.name}**")
                except Exception:
                    pass

        # add chosen role
        try:
            await user.add_roles(chosen_role)
        except discord.Forbidden:
            return await ctx.send("❌ I don't have permission to add that role.")
        except Exception as e:
            return await ctx.send(f"⚠️ Failed to add role: {e}")

        await ctx.send(f"🎉 Congrats! You got **{chosen_role.name}** for 7 days!")

        expires_at = datetime.utcnow().timestamp() + 7 * 24 * 60 * 60
        data = load_data()
        data[str(user.id)] = {"role_id": chosen_role.id, "expires_at": expires_at}
        save_data(data)
        asyncio.create_task(self._remove_role_later(user, chosen_role, 7 * 24 * 60 * 60))


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))
