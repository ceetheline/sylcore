import discord
from discord import ui, Interaction
import os
from discord.ext import commands

MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", "0"))
IS_COMPONENTS_V2 = True

class HeaderWarning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldown = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # only in main channel
        if message.channel.id != MAIN_CHANNEL_ID:
            return

        content = message.content.lstrip()  # trim leading spaces
        uid = message.author.id
        now = discord.utils.utcnow()

        # check cooldown
        last_warn = self.cooldown.get(uid)
        if last_warn and (now - last_warn).total_seconds() < 5:
            return
        self.cooldown[uid] = discord.utils.utcnow()

        warning_text = None

        # --- header check ---
        if content.startswith("# ") or content.startswith("## ") or content.startswith("### "):
            warning_text = f"> 🛠 {message.author.mention} **GURLL**, don't use headers here okay? you're disrupting 😐💔"

            if warning_text:
                # make a container view
                container = ui.Container(
                    ui.TextDisplay(f"{warning_text}")
                )
                view = ui.LayoutView(timeout=15)
                view.add_item(container)
                await message.channel.send(view=view)

        # allow commands to still work
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(HeaderWarning(bot))
