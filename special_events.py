# special_events.py
from typing import Dict
from discord import Message

class BaseSpecialEvent:
    async def run(self, bot, message: Message):
        return

SPECIALS: Dict[str, type] = {}

class HelloEvent(BaseSpecialEvent):
    async def run(self, bot, message: Message):
        await message.channel.send("🎉 Special event triggered!")

SPECIALS["hello"] = HelloEvent
