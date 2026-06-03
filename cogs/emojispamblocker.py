import re
import time
import discord
from discord.ext import commands
import emoji
import os
from dotenv import load_dotenv

load_dotenv()

class EmojiSpamBlocker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Whitelist configuration (Replace with actual IDs or handle in secret ENV)
        owners = os.getenv("OWNER_IDS", "")
        self.owner_ids = [int(cid.strip()) for cid in owners.split(",") if cid.strip().isdigit()]

        devs = os.getenv("DEV_IDS", "")
        self.dev_ids = [int(cid.strip()) for cid in devs.split(",") if cid.strip().isdigit()]

        # In-memory tracking data structures
        # { user_id: [timestamp1, timestamp2, ...] }
        self.msg_history = {}
        
        # { user_id: {"strikes": int, "last_strike_time": float} }
        self.violation_tracker = {} # used when individually used
        self.last_channel_author = {}

    def clean_and_count_emojis(self, text: str):
        """
        Highly robust parser to separate text from custom and unicode emojis.
        Accounts for whitespace, hidden characters, and animated tags.
        """
        # 1. Match all Discord Custom Emojis (Standard and Animated)
        # This regex catches: <:name:id> and <a:name:id>
        custom_emoji_pattern = r"<a?:[a-zA-Z0-9_]+:\d+>"
        custom_emojis = re.findall(custom_emoji_pattern, text)
        custom_count = len(custom_emojis)
        
        # Strip custom emojis out of the text completely
        text_no_custom = re.sub(custom_emoji_pattern, "", text)

        # 2. Extract and count all Unicode Emojis
        # Using emoji.emoji_list() keeps track of every single emoji match
        unicode_emojis = emoji.emoji_list(text_no_custom)
        unicode_count = len(unicode_emojis)
        
        # Strip unicode emojis out of the text completely
        text_no_emoji = emoji.replace_emoji(text_no_custom, replace="")

        # 3. Calculate Total Emoji Volume
        total_emojis = custom_count + unicode_count

        # 4. Clean up remaining text to evaluate "Real Content"
        # Strip out spaces, tabs, and newlines so "😂   😂" is recognized as pure emoji
        cleaned_text = re.sub(r"\s+", "", text_no_emoji)
        cleaned_length = len(cleaned_text)

        # A message is pure emoji if there's no actual textual characters left,
        # but the total emoji count is greater than 0.
        is_pure_emoji = (cleaned_length == 0 and total_emojis > 0)

        return cleaned_length, total_emojis, is_pure_emoji

    async def _process_message_spam(self, message: discord.Message):
        """
        Central processing core handling calculations, strike tracking,
        and moderation actions for new and edited text payloads.
        """
        current_time = time.time()
        user_id = message.author.id

        # 3. Analyze the message content
        cleaned_length, total_emojis, is_pure_emoji = self.clean_and_count_emojis(message.content)

        # Sticker Check: Count how many stickers are in the message
        sticker_count = len(message.stickers)
        has_stickers = sticker_count > 0

        # ---- THE 50-CHARACTER BYPASS RULE ----
        # If the non-emoji character count is 75 or more, completely bypass spam rules
        if cleaned_length >= 50:
            return

        # Initialize tracker data if it's a new user
        if user_id not in self.bot.shared_violation_tracker:
            self.bot.shared_violation_tracker[user_id] = {"strikes": 0, "probation_until": 0.0}

        is_spamming = False
        user_status = self.bot.shared_violation_tracker[user_id]

        # Default warning message
        warning_msg = f"{message.author.mention}, please stop spamming emojis/stickers."

        # ---- PROBATION CHECK (STRIKE 2 & 3 TRIGGER) ----
        # If the user already has a strike AND they are within their 30-second window,
        # ANY emoji message or sticker (whether it's 1 emoji or 8) triggers the next strike.
        if user_status["strikes"] > 0 and current_time < user_status["probation_until"]:
            if total_emojis > 0 or is_pure_emoji or has_stickers:
                is_spamming = True

        # ---- BASELINE CHECKS (STRIKE 1 TRIGGER) ----
        # If they aren't on probation, they have to break the original rules to get Strike 1
        else:
            # Rule 1: 8 or more emojis in one message
            if total_emojis >= 8:
                is_spamming = True
                # Override the default message specifically for Rule 1
                warning_msg = f"Too much emojis, {message.author.mention}. Please lessen the use of emojis next time."
            
            # Rule 2: 4 separate emoji-only messages in 30 seconds
            elif is_pure_emoji or has_stickers:
                channel_id = message.channel.id
                
                # If someone else spoke in this channel since their last emoji, reset their history
                if self.last_channel_author.get(channel_id) != user_id:
                    self.msg_history[user_id] = []
                
                # Update the last author cache for this channel
                self.last_channel_author[channel_id] = user_id

                # Continue with your existing 30-second logic...
                self.msg_history[user_id].append(current_time)
                self.msg_history[user_id] = [t for t in self.msg_history[user_id] if current_time - t <= 30]
                
                if len(self.msg_history[user_id]) >= 4:
                    is_spamming = True
                    self.msg_history[user_id] = []

            elif has_stickers:
                if user_id not in self.msg_history:
                    self.msg_history[user_id] = []
                
                self.msg_history[user_id].append(current_time)
                self.msg_history[user_id] = [t for t in self.msg_history[user_id] if current_time - t <= 30]
                
                if len(self.msg_history[user_id]) >= 3:
                    is_spamming = True
                    self.msg_history[user_id] = [] # Clear history on trigger

        # ---- ACTIONS & STRIKE ESCALATION ----
        if is_spamming:
            # Increment their strike count
            user_status["strikes"] += 1
            # Lock them into a new 30-second probation window starting from right now
            user_status["probation_until"] = current_time + 30.0
            
            current_strikes = user_status["strikes"]

            # Always delete the offending spam message
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"Missing permissions to delete message in {message.channel.name}")
                return

            # Check if they hit the 3rd strike for a timeout
            if current_strikes >= 3:
                # Reset their tracker entirely because they are being timed out
                self.bot.shared_violation_tracker[user_id] = {"strikes": 0, "probation_until": 0.0}
                if user_id in self.msg_history:
                    self.msg_history[user_id] = []

                # Apply 5-minute timeout
                duration = discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=5)
                try:
                    await message.author.timeout(duration, reason="Emoji spamming (3rd strike)")
                    await message.channel.send(
                        f"{message.author.mention}, you have been timed out for 5 minutes for repeated spam.",
                        delete_after=10
                    )
                except discord.Forbidden:
                    # In case the bot lacks role hierarchy power to timeout the member
                    await message.channel.send(
                        warning_msg,
                        delete_after=10
                    )
            else:
                # Strike 1 or Strike 2 warning
                await message.channel.send(
                    warning_msg,
                    delete_after=10 # Automatically deletes the bot's warning after 10s to avoid clutter
                )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignore if it's a DM or sent by a bot
        if not message.guild or message.author.bot:
            return

        # 2. Whitelist Check (Owner, Developers, and Administrators)
        if message.author.id == self.owner_ids or message.author.id in self.dev_ids:
            return
        if message.author.guild_permissions.administrator:
            return

        # Forward the message to the core process function
        await self._process_message_spam(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """
        Listens for message updates and channels edited text to the spam tracker.
        """
        # 1. Ignore DMs or actions triggered by bots
        if not after.guild or after.author.bot:
            return

        # 2. Whitelist Check (Instantly passes server admins, owners, and developers)
        if after.author.id in self.owner_ids or after.author.id in self.dev_ids:
            return
        if after.author.guild_permissions.administrator:
            return

        # 3. Prevent duplicate scanning if the text did not change (e.g. embed updates)
        if before.content == after.content:
            return

        # Forward the newly edited message variant to the core process function
        await self._process_message_spam(after)

# Setup function to load cog
async def setup(bot):
    await bot.add_cog(EmojiSpamBlocker(bot))