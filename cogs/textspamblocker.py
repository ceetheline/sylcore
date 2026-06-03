import regex
import time
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

class TextSpamBlocker(commands.Cog):
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

    def check_text_wall(self, content: str, message: discord.Message):
        """
        Analyzes text structure to detect regular walls of text, heading abuse,
        and aggressively catches hidden Unicode/invisible text wall spam.
        """
        total_length = len(content)
        lines = content.splitlines()
        total_lines = len(lines)

        # 1. Clean out standard punctuation and whitespaces
        cleaned_base = regex.sub(r'[\s\.,!\?\-_:;\(\)\[\]"\']', '', content)

        # 2. Extract standard visible English/ASCII alphanumeric characters
        visible_chars = len(regex.findall(r'[a-zA-Z0-9]', cleaned_base))

        # ---- BULLETPROOF INVISIBLE SPAM RECOGNITION ----
        
        # Catch A: Stretches vertically but has almost zero visible text content.
        if total_lines > 4 and visible_chars <= 2:
            return True, f"Please stop sending blank walls of text, {message.author.mention}."

        # Catch B: High raw payload size with absolutely zero visible text (No line breaks needed)
        if total_length > 20 and visible_chars == 0:
            return True, f"Please stop sending blank walls of text, {message.author.mention}."
        
        # Catch C: Direct scan for unlisted hidden/invisible unicode characters.
        # Includes: Control (Cc), Format (Cf), Invisible Spaces (Zs), and Unassigned Hidden blocks (Cn)
        # Strips out standard spaces (\x20) so they aren't marked as bad characters.
        invisible_count = len(regex.findall(r'(?>[\p{Cc}\p{Cf}\p{Zs}\p{Cn}](?<![\x20\r\n]))', content))
        if invisible_count > 10:  # Triggers immediately on your payload (counts 80+ targets)
            return True, f"Invisible characters/text walls are not allowed, {message.author.mention}."
        
        # 4. Check for massive character walls
        if total_length > 1000:
            return True, f"Your message is too long, {message.author.mention}. Please shorten your text."

        # 5. Check for "Unnatural Word" spam
        words = content.split()
        for word in words:
            if len(word) > 85: 
                return True, f"Please stop sending walls of text, {message.author.mention}."

        # 6. Check for Heading Abuse
        # ---- ADVANCED HEADING ABUSE & CHARACTER CAPS ----
        heading_count = 0
        total_heading_chars = 0

        for line in lines:
            stripped_line = line.strip()
            
            # Matches 1 to 3 hashtags followed by any number of spaces at the start of a line
            heading_match = regex.match(r'^#{1,3}\s+', stripped_line)
            
            if heading_match:
                heading_count += 1
                
                # Strip the marker out cleanly to check the raw content length
                heading_text = regex.sub(r'^#{1,3}\s+', '', stripped_line)
                line_heading_length = len(heading_text)
                total_heading_chars += line_heading_length

                # Rule: A single header line cannot be a giant wall of text (Cap: 60 chars)
                if line_heading_length > 60:
                    return True, f"Heading text line is too long, {message.author.mention}. Keep it concise."

        # Rule: Total number of headings allowed in a single message
        if heading_count > 3:
            return True, f"Too many big fonts/headings, {message.author.mention}. Please keep it readable."

        # Rule: Combined maximum characters allowed across all headings (Cap: 60 chars)
        if total_heading_chars > 60:
            return True, f"Too much heading text used overall, {message.author.mention}. Use regular text instead."

        # 7. Check for Vertical Line-Break Spam (Empty spacing to stretch chat)
        if total_lines > 12:
            # If they have a lot of lines but almost no text, they are stretching the chat screen
            if total_lines > 0 and (visible_chars / total_lines) < 3: 
                return True, f"Please stop flooding the chat, {message.author.mention}."

        return False, ""
    
    async def _process_message_spam(self, message: discord.Message):
        """
        Central processing core handling calculations, strike tracking,
        and moderation actions for new and edited text payloads.
        """
        current_time = time.time()
        user_id = message.author.id

        # 3. Initialize tracking data inside memory arrays if it's a new user chatting
        if user_id not in self.bot.shared_violation_tracker:
            self.bot.shared_violation_tracker[user_id] = {"strikes": 0, "probation_until": 0.0}

        # Run the text analysis immediately to capture if it breaks a rule, and get its unique warning string
        is_text_spam, dynamic_warning = self.check_text_wall(message.content, message)

        is_spamming = False
        user_status = self.bot.shared_violation_tracker[user_id]
        warning_msg = dynamic_warning

        # ---- THE STRIKE SYSTEM & PROBATION LOGIC ----
        
        # Check if the user is currently trapped inside the high-alert 30-second probation window
        if user_status["strikes"] > 0 and current_time < user_status["probation_until"]:
            # Run text processing against the message
            is_text_spam, text_warning = self.check_text_wall(message.content, message)
            
            # During probation, any structural rule break triggers the next strike instantly
            if is_text_spam:
                is_spamming = True
                # Keep general warning for subsequent strikes unless explicitly overriden
        
        # Baseline checking loop if the user has a clean record or their probation timer expired
        else:
            # Pass the raw content string and the complete discord message object to your algorithm
            is_text_spam, text_warning = self.check_text_wall(message.content, message)
            if is_text_spam:
                is_spamming = True
                warning_msg = text_warning # Capture the highly specific warning reason from your rules

        # ---- ENFORCING PUNISHMENT & DELETION ACTIONS ----
        if is_spamming:
            # Advance strike count and establish a brand new 30-second probation penalty window
            user_status["strikes"] += 1
            user_status["probation_until"] = current_time + 30.0
            current_strikes = user_status["strikes"]

            # Try to instantly drop the text wall from view
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"Missing administrative permissions to delete message in {message.channel.name}")
                return

            # Strike 3 Escalation: Apply a 5-minute timeout penalty
            if current_strikes >= 3:
                # Flush structural history records so the user starts fresh after the timeout expires
                self.bot.shared_violation_tracker[user_id] = {"strikes": 0, "probation_until": 0.0}
                if user_id in self.msg_history:
                    self.msg_history[user_id] = []

                # Configure the exact timestamp calculation for a 5-minute moderation break
                duration = discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=5)
                try:
                    await message.author.timeout(duration, reason="Text spam rules violation (3rd strike)")
                    await message.channel.send(
                        f"{message.author.mention}, you have been timed out for 5 minutes for repeated spam.",
                        delete_after=10
                    )
                except discord.Forbidden:
                    # In case the target is higher up the role hierarchy than the bot, send the textual warning
                    await message.channel.send(warning_msg, delete_after=10)
            
            # Strike 1 & Strike 2 Handler: Send the appropriate warning and clear it after 10 seconds
            else:
                await message.channel.send(warning_msg, delete_after=10)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignore Direct Messages (DMs) or messages generated by other bots
        if not message.guild or message.author.bot:
            return

        # 2. Whitelist Check (Instantly passes server admins, the owner, and listed developers)
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

# Standard setup hook enabling your central bot.py file to load this extension smoothly
async def setup(bot):
    await bot.add_cog(TextSpamBlocker(bot))