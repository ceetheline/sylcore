import discord
from discord import ui
from discord.ext import commands
import os, asyncio

MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", "0"))

HEADER_PREFIXES = ["# ", "## ", "### "]

# 5-stage escalation messages
STAGE_MESSAGES = {
    1: "🛠 {mention} **GURLL** don't use headers... you know.. the thing that enlarges the text. You're disrupting 😐💔",
    2: "🛠 {mention} HAHA not funny. 🙄",
    3: "🛠 {mention} do you really think I'm joking??",
    4: "🛠 {mention} you're doing this on PURPOSE aren't you?",
    5: "🛠 {mention} well if you don't stop using headers..."
}

COOLDOWN_SECONDS = 1   # avoid spam
RESET_AFTER = 30       # reset warning stage after 30s


class WarningView(ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=15)
        self.message = None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except:
                pass


class HeaderWarning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_warning_time = {}  # user_id -> datetime
        self.stage = {}              # user_id -> 1–5

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if message.channel.id != MAIN_CHANNEL_ID:
            return

        content = message.content.lstrip()

        # check for headers
        if not any(content.startswith(h) for h in HEADER_PREFIXES):
            return

        now = discord.utils.utcnow()
        uid = message.author.id

        # --- ANTI-SPAM COOLDOWN ---
        last_time = self.last_warning_time.get(uid)
        if last_time and (now - last_time).total_seconds() < COOLDOWN_SECONDS:
            return

        # --- DETERMINE WARNING STAGE ---
        if not last_time or (now - last_time).total_seconds() > RESET_AFTER:
            current_stage = 1
        else:
            current_stage = min(self.stage.get(uid, 1) + 1, 5)

        # store stage & timestamp
        self.stage[uid] = current_stage
        self.last_warning_time[uid] = now

        # get the message for this stage
        msg_text = STAGE_MESSAGES[current_stage].format(mention=message.author.mention)

        # build the view like christmas event
        container = ui.Container(ui.TextDisplay(msg_text))
        view = WarningView()
        view.add_item(container)

        sent = await message.channel.send(view=view)
        view.message = sent

        # Delete after timeout
        await asyncio.sleep(10)
        try:
            await sent.delete()
        except:
            pass


async def setup(bot):
    await bot.add_cog(HeaderWarning(bot))
