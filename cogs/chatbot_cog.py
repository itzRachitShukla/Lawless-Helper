# cogs/chatbot_cog.py
import asyncio
import random
import time
import aiohttp
import logging
import re
from discord.ext import commands
from db_json import db
from markov_chains import MarkovChains

# mention sanitizer
MENTION_PATTERN = re.compile(r"<@!?(?P<id>\d+)>")
def sanitize_mentions(text: str, disabled_ids: list):
    if not text or not disabled_ids:
        return text
    def repl(m):
        uid = m.group("id")
        if uid in disabled_ids:
            return ""
        return m.group(0)
    out = MENTION_PATTERN.sub(repl, text)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out

logger = logging.getLogger("chatbot_cog")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

class ChatbotCog(commands.Cog, name="chatbot"):
    def __init__(self, bot):
        self.bot = bot
        if not hasattr(bot, "cooldown"):
            bot.cooldown = {}
        try:
            cp = bot.command_prefix
            if isinstance(cp, str):
                self.cmd_prefixes = (cp,)
            elif isinstance(cp, (list, tuple)):
                self.cmd_prefixes = tuple(cp)
            else:
                self.cmd_prefixes = None
        except Exception:
            self.cmd_prefixes = None
        self._last_setchannel = {}

    def _is_command(self, content: str) -> bool:
        if not content or self.cmd_prefixes is None:
            return False
        return any(content.startswith(p) for p in self.cmd_prefixes)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not message.content or not message.content.strip():
            return

        # DM learning support
        if message.guild is None:
            user_id = str(message.author.id)
            try:
                all_raw = db._raw
            except Exception:
                all_raw = {}
            for gid, graw in list(all_raw.items()):
                try:
                    dm_learn = graw.get("dm_learn_users", {})
                    if user_id in dm_learn:
                        weight = int(dm_learn.get(user_id, 1))
                        gd = db.fetch(gid)
                        gd.add_text(message.content, user_id, str(message.id), weight=weight, source="dm")
                        logger.info(f"[DM] Added DM from {user_id} -> guild {gid} (w={weight})")
                except Exception:
                    logger.exception("Error processing DM learn")
                    continue
            return

        if self._is_command(message.content):
            await self.bot.process_commands(message)
            return

        guild_id = str(message.guild.id)
        guild_db = db.fetch(guild_id)

        if guild_db.is_banned() or not guild_db.toggled_activity():
            await self.bot.process_commands(message)
            return

        channel = message.channel
        channel_id = guild_db.get_channel()
        webhook_url = guild_db.get_webhook()

        try:
            me = await message.guild.fetch_member(self.bot.user.id)
            can_send = channel.permissions_for(me).send_messages
        except Exception:
            can_send = False

        if not (channel and channel.id == channel_id and can_send):
            await self.bot.process_commands(message)
            return

        has_mention = any(u.id == self.bot.user.id for u in message.mentions)
        texts_len = guild_db.get_texts_length()
        last_send = self.bot.cooldown.get(guild_id, 0)

        send_pct = guild_db.get_sending_percentage()
        collect_pct = guild_db.get_collection_percentage()

        logger.info(f"[{guild_id}] Received message: {message.content[:120]}")

        # collect (probabilistic)
        if random.random() <= collect_pct:
            try:
                if guild_db.is_track_allowed(str(message.author.id)):
                    guild_db.add_text(message.content, str(message.author.id), str(message.id))
                    logger.debug(f"[{guild_id}] collected text")
            except Exception:
                logger.exception("Error adding text")

        if texts_len < 5:
            logger.info(f"[{guild_id}] Not enough texts ({texts_len})")
            await self.bot.process_commands(message)
            return

        now_ms = int(time.time() * 1000)
        if has_mention and last_send + 1000 < now_ms:
            send_pct = guild_db.get_reply_percentage()
            last_send = 0

        will_respond = (random.random() <= send_pct) and (last_send + 15000 < now_ms)
        if not will_respond:
            await self.bot.process_commands(message)
            return

        self.bot.cooldown[guild_id] = now_ms

        try:
            maxw = random.randint(5, 40)
            generated = guild_db.markov.generate_chain(maxw)
        except Exception:
            logger.exception("Generation error")
            generated = ""

        if not generated.strip():
            await self.bot.process_commands(message)
            return

        # sanitize mentions
        try:
            disabled_list = guild_db._raw.get("disabledMentionUserIds", [])
            disabled_list_str = [str(x) for x in disabled_list]
            generated = sanitize_mentions(generated, disabled_list_str)
        except Exception:
            logger.exception("Sanitization failed")

        delay = 5 + random.random() * 5

        if not webhook_url:
            try:
                async with channel.typing():
                    await asyncio.sleep(delay)
                if has_mention:
                    await message.reply(generated)
                else:
                    await channel.send(generated)
            except Exception:
                logger.exception("Send failed")
        else:
            await asyncio.sleep(delay)
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {"content": generated, "allowed_mentions": {"parse": []}}
                    async with session.post(webhook_url, json=payload) as resp:
                        _ = resp.status
            except Exception:
                logger.exception("Webhook send failed")

        await self.bot.process_commands(message)

    # ---------------- admin commands ----------------
    @commands.command(name="markov-setchannel")
    @commands.has_guild_permissions(administrator=True)
    async def set_channel(self, ctx, channel_id: int = None):
        gid = str(ctx.guild.id)
        now = time.time()
        last = self._last_setchannel.get(gid, 0)
        if now - last < 2.0:
            logger.warning(f"[set_channel] duplicate suppressed {gid}")
            return
        self._last_setchannel[gid] = now
        guild_db = db.fetch(gid)
        guild_db.set_channel(channel_id)
        await ctx.send(f"Set Markov channel to: {channel_id}")

    @commands.command(name="markov-scan")
    @commands.has_guild_permissions(administrator=True)
    async def markov_scan(self, ctx, limit: int = None):
        """Scan channel history (batch flushes + progress).
        Usage:
          ?markov-scan           -> full history
          ?markov-scan 500      -> up to 500 messages
        """
        await ctx.send(f"📥 Starting scan (limit={limit or 'ALL'}) — this may take a while for large channels...")

        guild_db = db.fetch(str(ctx.guild.id))
        channel_id = guild_db.get_channel()
        if channel_id is None:
            return await ctx.send("❌ Markov channel not set. Use ?markov-setchannel first.")

        channel = ctx.guild.get_channel(channel_id)
        if channel is None:
            return await ctx.send("❌ Could not find configured channel.")

        batch_size = 1000
        progress_every = 500
        added = 0
        buffer_texts = []
        idx = 0

        try:
            async for msg in channel.history(limit=limit, oldest_first=True):
                idx += 1
                # filters
                if msg.author.bot:
                    continue
                if not msg.content or not msg.content.strip():
                    continue

                buffer_texts.append({
                    "text": msg.content,
                    "authorId": str(msg.author.id),
                    "messageId": str(msg.id),
                    "weight": 1,
                    "source": "scan"
                })
                added += 1

                # flush batch to DB
                if len(buffer_texts) >= batch_size:
                    guild_raw = guild_db._raw
                    guild_raw.setdefault("texts", []).extend(buffer_texts)
                    buffer_texts = []
                    texts = guild_raw.get("texts", [])
                    guild_db.markov.generate_dictionary(texts)
                    guild_db.save_markov()

                # progress update
                if added % progress_every == 0:
                    await ctx.send(f"🔁 Scanned {added} messages so far...")

        except Exception as e:
            logger.exception("Scan error")
            return await ctx.send(f"❌ Scan failed: {e}")

        # append any remaining buffer
        if buffer_texts:
            guild_raw = guild_db._raw
            guild_raw.setdefault("texts", []).extend(buffer_texts)
            texts = guild_raw.get("texts", [])
            guild_db.markov.generate_dictionary(texts)
            guild_db.save_markov()

        await ctx.send(f"✅ Scan complete — added {added} messages.")

    @commands.command(name="markov-stats")
    @commands.has_guild_permissions(administrator=True)
    async def markov_stats(self, ctx):
        guild_db = db.fetch(str(ctx.guild.id))
        texts = guild_db.get_texts()
        wl_size = len(guild_db.markov.word_list) if hasattr(guild_db, "markov") else 0
        await ctx.send(
            f"Texts stored: {len(texts)}\n"
            f"Markov keys: {wl_size}\n"
            f"collectionPercentage: {guild_db.get_collection_percentage()}\n"
            f"sendingPercentage: {guild_db.get_sending_percentage()}\n"
            f"replyPercentage: {guild_db.get_reply_percentage()}\n"
            f"channelId: {guild_db.get_channel()}\n"
        )

    @commands.command(name="markov-clear")
    @commands.has_guild_permissions(administrator=True)
    async def markov_clear(self, ctx):
        guild_db = db.fetch(str(ctx.guild.id))
        guild_db._raw["texts"] = []
        guild_db.markov = MarkovChains({})
        guild_db.save_markov()
        await ctx.send("Cleared stored texts and model.")

    @commands.command(name="markov-disable-mention")
    @commands.has_guild_permissions(administrator=True)
    async def disable_mention(self, ctx, user_id: int):
        guild_db = db.fetch(str(ctx.guild.id))
        lst = guild_db._raw.setdefault("disabledMentionUserIds", [])
        sid = str(user_id)
        if sid in lst:
            return await ctx.send("User already disabled.")
        lst.append(sid)
        guild_db.save_markov()
        await ctx.send(f"Disabled mentions for {user_id}")

    @commands.command(name="markov-enable-mention")
    @commands.has_guild_permissions(administrator=True)
    async def enable_mention(self, ctx, user_id: int):
        guild_db = db.fetch(str(ctx.guild.id))
        lst = guild_db._raw.setdefault("disabledMentionUserIds", [])
        sid = str(user_id)
        if sid in lst:
            lst.remove(sid)
            guild_db.save_markov()
            await ctx.send(f"Enabled mentions for {user_id}")
        else:
            await ctx.send("That user id was not in the disabled list.")

    @commands.command(name="markov-dm-learn")
    @commands.has_guild_permissions(administrator=True)
    async def markov_dm_learn(self, ctx, user_id: int, weight: int = 3):
        guild_db = db.fetch(str(ctx.guild.id))
        mg = guild_db._raw.setdefault("dm_learn_users", {})
        mg[str(user_id)] = int(weight)
        guild_db.save_markov()
        await ctx.send(f"Enabled DM learning for {user_id} with weight {weight}.")

    @commands.command(name="markov-dm-unlearn")
    @commands.has_guild_permissions(administrator=True)
    async def markov_dm_unlearn(self, ctx, user_id: int):
        guild_db = db.fetch(str(ctx.guild.id))
        mg = guild_db._raw.setdefault("dm_learn_users", {})
        if str(user_id) in mg:
            del mg[str(user_id)]
            guild_db.save_markov()
            await ctx.send(f"Disabled DM learning for {user_id}.")
        else:
            await ctx.send("User not enabled for DM learning.")

# setup guard
async def setup(bot):
    cog_name = "chatbot"
    if cog_name in bot.cogs:
        print(f"[setup] Skipping {cog_name} - already loaded.")
        return
    await bot.add_cog(ChatbotCog(bot))
    print("[setup] ChatbotCog LOADED")
