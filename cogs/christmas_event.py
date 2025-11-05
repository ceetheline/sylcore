import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import json
import os
from data import data
import random
import time
import asyncio
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class ChristmasEvent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = data

        # Configuration
        self.drop_channel_id = int(os.getenv("DROP_CHANNEL_ID", "0"))
        spam_channels = os.getenv("SPAM_CHANNEL_IDS", "")
        self.spam_channel_ids = [int(cid.strip()) for cid in spam_channels.split(",") if cid.strip().isdigit()]
        
        # Activity tracking
        self.activity_tracker = defaultdict(lambda: {"users": set(), "count": 0, "last_drop": 0})
        self.user_last_message = {}
        
    # Data is persisted using the data/data.py module
        
        # Drop configuration
        self.drop_types = [
            {"name": "Santa Claus", "emoji": "🎅", "gifts": +3, "weight": 5},
            {"name": "Christmas Tree", "emoji": "🎄", "gifts": +1, "weight": 50},
            {"name": "Coal", "emoji": "🪨", "gifts": -1, "weight": 35},
            {"name": "Grinch", "emoji": "👺", "gifts": -3, "weight": 10}
        ]
        
        # Activity settings
        self.min_messages = 3
        self.max_messages = 5
        self.min_unique_users = 2
        self.same_user_cooldown = 1
        self.drop_cooldown = 15
        
        # Event active status
        self.event_active = False
        self.check_event_status.start()
    
    def cog_unload(self):
        self.check_event_status.cancel()
    
    @tasks.loop(hours=1)
    async def check_event_status(self):
        """Check if the event should be active (Nov 1 - Dec 24)"""
        now = datetime.now()
        
        if (now.month == 11) or (now.month == 12 and now.day < 24):
            if not self.event_active:
                self.event_active = True
                print("🎄 Christmas event is now ACTIVE!")
        elif now.month == 12 and now.day == 24 and now.hour == 12:
            if self.event_active:
                self.event_active = False
                print("🎄 Christmas event has ENDED! Happy Holidays!")
        else:
            if self.event_active:
                self.event_active = False
                print("🎄 Christmas event is now INACTIVE")
    
    @check_event_status.before_loop
    async def before_check_event_status(self):
        await self.bot.wait_until_ready()
        await self.check_event_status()
    
    def is_event_active(self):
        return self.event_active
    
    # NOTE: persistence is delegated to data/data.record_gift and helpers
    
    # Drop logic
    def calculate_drop_chance(self, active_users_count, message_count):
        if message_count < self.min_messages:
            return 0
        
        base_chance = min((message_count - self.min_messages + 1) * 5, 50)
        
        if active_users_count >= self.min_unique_users:
            user_bonus = (active_users_count - self.min_unique_users) * 10
            return min(base_chance + user_bonus, 80)
        
        return 0
    
    def get_random_drop(self):
        weights = [d["weight"] for d in self.drop_types]
        return random.choices(self.drop_types, weights=weights)[0]
    
    # Gift Drop View
    class GiftDropView(View):
        def __init__(self, cog, drop_type, active_slot, message, data):
            super().__init__(timeout=30)
            self.cog = cog
            self.drop_type = drop_type
            self.active_slot = active_slot
            self.message = message
            self.data = data
            self.claimed = False

            for i in range(4):
                if i == active_slot:
                    btn_emoji = "🎁"
                    button = Button(
                        style=discord.ButtonStyle.primary,
                        emoji=btn_emoji,
                        custom_id=f"gift_{i}",
                        disabled=False
                    )
                    button.callback = self.create_callback(i)
                else:
                    button = Button(
                        style=discord.ButtonStyle.secondary,
                        label="\u200b",
                        custom_id=f"empty_{i}",
                        disabled=True
                    )
                self.add_item(button)

        async def on_timeout(self):
            try:
                await self.message.delete()
            except:
                pass

        def create_callback(self, button_id):
            async def callback(interaction: discord.Interaction):
                if self.claimed:
                    # Interaction already handled, just defer update silently
                    try:
                        await interaction.response.defer()
                    except:
                        # Last resort, try editing message to remove buttons
                        try:
                            await interaction.response.edit_message(view=None)
                        except:
                            pass
                    return

                if button_id != self.active_slot:
                    # Wrong button clicked: respond ephemeral to user
                    try:
                        await interaction.response.send_message("That wasn't the right gift! 😢", ephemeral=True)
                    except:
                        pass
                    return

                # Mark claimed early to prevent race conditions
                self.claimed = True
                
                # Disable buttons immediately
                for child in self.children:
                    child.disabled = True

                # Always defer the update immediately to avoid interaction timeout
                try:
                    await interaction.response.defer()
                except Exception as e:
                    print(f"Error deferring interaction response: {e}")

                # Run gift recording in a thread (blocking) but after defer
                try:
                    new_total = await asyncio.to_thread(
                        self.data.record_gift,
                        interaction.user.id,
                        self.drop_type["gifts"],
                        self.drop_type.get("name"),
                    )
                except Exception as e:
                    print(f"Error recording gift: {e}")
                    # Optionally notify user or log
                
                # Build claim log text
                try:
                    original_desc = self.message.embeds[0].description if self.message.embeds else ""
                except Exception:
                    original_desc = ""
                
                gifts_amount = self.drop_type.get("gifts", 0)
                item_emoji = f"{self.drop_type.get('emoji', '')}"
                item_name = f"{self.drop_type.get('name', 'gift')}"
                messages = {
                    "Santa Claus": "Ho ho ho! You are on the nice list! You got a special gift!",
                    "Christmas Tree": "That's a lovely gift to brighten the season!",
                    "Coal": "Oops! Looks like you're on the naughty list this year!",
                    "Grinch": "Oh no! The Grinch got you! Better luck next time!",
                }
                message_text = messages.get(item_name, "")
                claim_line = f"\n\n{interaction.user.mention} just collected a {item_name}! `{gifts_amount}`🎁. {message_text}"

                updated_description = original_desc + claim_line
                updated_embed = discord.Embed(description=updated_description, color=0x00FF00)

                # Update the message with new embed and disable buttons
                try:
                    await self.message.edit(embed=updated_embed, view=self)
                except Exception as e:
                    print(f"Error editing message: {e}")
                    try:
                        await interaction.response.edit_message(embed=updated_embed, view=self)
                    except Exception as e2:
                        print(f"Fallback error editing message: {e2}")

            return callback

    
    @commands.Cog.listener()
    async def on_message(self, message):
       # Temporarily disabled for testing - remove this comment and uncomment below for production
        if not self.is_event_active():
            return
        
        if message.author.bot:
            return
        
        if self.drop_channel_id and message.channel.id != self.drop_channel_id:
            return
        
        if message.channel.id in self.spam_channel_ids:
            return
        
        channel_id = message.channel.id
        current_time = time.time()
        user_id = message.author.id
        
        if user_id in self.user_last_message:
            time_diff = current_time - self.user_last_message[user_id]
            if time_diff < self.same_user_cooldown:
                return
        
        self.user_last_message[user_id] = current_time
        
        tracker = self.activity_tracker[channel_id]
        tracker["users"].add(user_id)
        tracker["count"] += 1
        
        active_users = len(tracker["users"])
        message_count = tracker["count"]
        
        drop_chance = self.calculate_drop_chance(active_users, message_count)

        # Debug logging
        print(f"📊 Activity: {message_count} msgs, {active_users} users, {drop_chance}% chance")
        
        if drop_chance > 0 and random.randint(1, 100) <= drop_chance:
            if current_time - tracker["last_drop"] < self.drop_cooldown:
                return
            
            tracker["last_drop"] = time.time()
            tracker["users"].clear()
            tracker["count"] = 0
            
            drop = self.get_random_drop()
            active_slot = random.randint(0, 3)
            
            # Create embed with description including the drop item and its gift value
            gifts_amount = drop.get("gifts", 0)
            item_emoji = f"{drop.get('emoji','')}"
            item_name = f"{drop.get('name','gift')}"
            if item_name == "Santa Claus":
                message_text = "Ho ho ho! A special visitor has arrived! Hurry and collect it before he goes away!"
            elif item_name == "Christmas Tree":
                message_text = "Grab it quickly before anyone to add some cheer!"
            elif item_name == "Coal":
                message_text = "Uh oh! This is not the gift that I wanted!"
            elif item_name == "Grinch":
                message_text = "Yikes! The Grinch is here! Better hide those gifts away!"
            embed = discord.Embed(
                description=f"# {item_emoji} A {item_name} just appeared!\n\n{message_text} `{gifts_amount}`🎁",
                color=0xFF0000
            )
            
            # Send message first, then create view with the message object
            sent_message = await message.channel.send(embed=embed)
            view = self.GiftDropView(self, drop, active_slot, sent_message, data)
            await sent_message.edit(view=view)
    
    @app_commands.command(name="leaderboard", description="Show the top 10 gift collectors")
    async def leaderboard(self, interaction: discord.Interaction):
        # defer immediately to avoid timeout
        await interaction.response.defer()

        counts = getattr(data, "gifts", {})

        if not counts:
            await interaction.followup.send("No one has collected any gifts yet! 🎁")
            return

        sorted_users = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        top_10 = sorted_users[:10]

        embed = discord.Embed(
            description="""## 🎄 Christmas Gift Leaderboard 🎄""",
            color=0x00FF00
        )

        leaderboard_text = ""
        for idx, (user_id, gifts_count) in enumerate(top_10, 1):
            try:
                user = self.bot.get_user(int(user_id))
                user_mention = user.mention if user else f"<@{user_id}>"
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
                leaderboard_text += f"{medal} {user_mention} - **{gifts_count}** 🎁\n"
            except Exception as e:
                print(f"Failed to get user {user_id}: {e}")
                leaderboard_text += f"{idx}. <@{user_id}> - **{gifts_count}** 🎁\n"

        embed.add_field(name="Top Collectors", value=leaderboard_text or "None yet!", inline=False)

        # show user's own stats
        user_id_str = str(interaction.user.id)
        user_gifts = counts.get(user_id_str, 0)
        user_rank = next((i for i, (uid, _) in enumerate(sorted_users, 1) if uid == user_id_str), None)
        embed.add_field(
            name="Your Stats",
            value=f"-# Rank: **#{user_rank}** | Gifts: **{user_gifts}** 🎁",
            inline=False
        )

        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="gifts", description="Check your or someone else's gift count")
    async def gifts(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gifts = data.get_user_total(target.id)

        if target == interaction.user:
            await interaction.response.send_message(f"You have **{gifts}** 🎁")
        else:
            await interaction.response.send_message(f"{target.mention} has **{gifts}** 🎁")
    
    @app_commands.command(name="setchristmaschannel", description="Set the current channel as the Christmas drop channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setchristmaschannel(self, interaction: discord.Interaction):
        self.drop_channel_id = interaction.channel.id
        await interaction.response.send_message(f"✅ Christmas drop channel set to {interaction.channel.mention}")
    
    @app_commands.command(name="christmasstatus", description="Check if the Christmas event is active")
    async def christmasstatus(self, interaction: discord.Interaction):
        if self.is_event_active():
            await interaction.response.send_message("🎄 The Christmas event is currently **ACTIVE**!")
        else:
            await interaction.response.send_message("❄️ The Christmas event is currently **INACTIVE**. Event runs Nov 1 - Dec 24.")

async def setup(bot):
    await bot.add_cog(ChristmasEvent(bot))
