import discord
from discord import ui
from discord.ext import commands, tasks
from discord.ui import Button
import os, random, time, asyncio, json
from collections import defaultdict
from datetime import datetime
from data import data
from dotenv import load_dotenv

load_dotenv()

IS_COMPONENTS_V2 = True

class ChristmasEvent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = data

        # Config
        self.drop_channel_id = int(os.getenv("DROP_CHANNEL_ID", "0"))
        spam_channels = os.getenv("SPAM_CHANNEL_IDS", "")
        self.spam_channel_ids = [int(cid.strip()) for cid in spam_channels.split(",") if cid.strip().isdigit()]

        # Activity
        self.activity_tracker = defaultdict(lambda: {"users": set(), "count": 0, "last_drop": 0})
        self.user_last_message = {}

        # Drop config
        self.drop_types = [
            {"name": "Santa Claus", "emoji": "🎅", "gifts": +3, "weight": 10},
            {"name": "Christmas Tree", "emoji": "🎄", "gifts": +1, "weight": 60},
            {"name": "Coal", "emoji": "🪨", "gifts": -1, "weight": 20},
            {"name": "Grinch", "emoji": "👺", "gifts": -3, "weight": 10},
        ]

        # Settings
        self.min_messages = 10
        self.max_messages = 25
        self.min_unique_users = 2
        self.same_user_cooldown = 1
        self.drop_cooldown = 10
        self.event_active = False

        self.check_event_status.start()

    def cog_unload(self):
        self.check_event_status.cancel()

    # --- COMPONENTS SYSTEM ---
    class GiftDropView(ui.LayoutView):
        def __init__(self, cog, drop_type, active_slot, message, data):
            super().__init__(timeout=25)
            self.cog = cog
            self.drop_type = drop_type
            self.active_slot = active_slot
            self.message = message
            self.data = data
            self.claimed = False
            self.claim_window_open = False
            self.pending_claims = set()

            # container layout
            messages = {
                "Santa Claus": "Ho ho ho! A special visitor has arrived! Hurry and collect it before he goes away!",
                "Christmas Tree": "Grab it quickly before anyone to add some cheer!",
                "Coal": "Uh oh! This is not the gift that I wanted!",
                "Grinch": "Yikes! The Grinch is here! Better hide those gifts away!",
            }

            drop_message = messages.get(self.drop_type["name"], "You found something interesting!")
            
            self.container = ui.Container(ui.TextDisplay(f"# {drop_type['emoji']} A {drop_type['name']} just appeared!"))
            self.container.add_item(ui.TextDisplay(f"{drop_message} **`{'+' if self.drop_type['gifts'] > 0 else ''}{self.drop_type['gifts']}`**🎁"))
            self.container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))

            # button row
            row = ui.ActionRow()
            for i in range(4):
                if i == active_slot:
                    button = ui.Button(
                        style=discord.ButtonStyle.primary,
                        emoji="🎁",
                        custom_id=f"gift_{i}",
                        disabled=False
                    )

                    async def make_callback(interaction: discord.Interaction, index=i):
                        if self.claimed:
                            try:
                                await interaction.response.defer()
                            except:
                                pass
                            return

                        # start claim window if not started
                        if not self.claim_window_open:
                            self.claim_window_open = True
                            self.pending_claims = set()

                            async def claim_window():
                                await asyncio.sleep(0.6)  # wait for others to click
                                await self.finish_claim()  # <-- only call here, after window

                            asyncio.create_task(claim_window())  # <-- run the window in background

                        # append user to pending_claims
                        self.pending_claims.add(interaction.user)

                        try:
                            await interaction.response.defer()
                        except:
                            pass


                    button.callback = make_callback
                else:
                    button = ui.Button(
                        style=discord.ButtonStyle.secondary,
                        label="\u200b",
                        custom_id=f"empty_{i}",
                        disabled=True
                    )
                row.add_item(button)

            self.container.add_item(row)
            self.add_item(self.container)

        async def finish_claim(self):
            import random
            if self.claimed or not self.pending_claims:
                return

            self.claimed = True
            winner = random.choice(list(self.pending_claims))

            # instantly disable all buttons so no one else can click
            for child in self.container.children:
                if isinstance(child, ui.ActionRow):
                    for btn in child.children:
                        btn.disabled = True

            # record gift in a thread-safe way
            await asyncio.to_thread(
                self.data.record_gift,
                winner.id,
                self.drop_type["gifts"],
                self.drop_type.get("name"),
            )

            channel_id = self.message.channel.id
            tracker = self.cog.activity_tracker[channel_id]
            tracker["last_drop"] = time.time()

            # rebuild the entire container layout (your version)
            messages = {
                "Santa Claus": "Ho ho ho! A special visitor has arrived! Hurry and collect it before he goes away!",
                "Christmas Tree": "Grab it quickly before anyone to add some cheer!",
                "Coal": "Uh oh! This is not the gift that I wanted!",
                "Grinch": "Yikes! The Grinch is here! Better hide those gifts away!",
            }
            drop_message = messages.get(self.drop_type["name"], "You found something interesting!")

            messages_2 = {
                "Santa Claus": "You are on the nice list! You got a special gift!",
                "Christmas Tree": "That's a lovely gift to brighten the season!",
                "Coal": "Oops! Looks like you're on the naughty list this year!",
                "Grinch": "Oh no! The Grinch got you! Better luck next time!",
            }
            append_message = messages_2.get(self.drop_type["name"], "You found something interesting!")

            new_container = ui.Container(
                ui.TextDisplay(f"# {self.drop_type['emoji']} A {self.drop_type['name']} just appeared!"),
                ui.TextDisplay(f"{drop_message} **`{'+' if self.drop_type['gifts'] > 0 else ''}{self.drop_type['gifts']}`**🎁"),
                ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True),
                ui.TextDisplay(
                    f"🎉 {winner.mention} claimed the {self.drop_type['emoji']} **{self.drop_type['name']}**! {append_message} **`{'+' if self.drop_type['gifts'] > 0 else ''}{self.drop_type['gifts']}`**🎁"
                )
            )
            new_view = ui.LayoutView(timeout=None)
            new_view.add_item(new_container)

            # edit message instantly (no defer lag)
            try:
                await self.message.edit(view=new_view)
            except Exception as e:
                print(f"Error editing message: {e}")

            # start background cooldown reset after claim (non-blocking)
            async def _post_claim_cooldown(channel_id_local, tracker_local):
                try:
                    # Immediately stop counting new activity if you want:
                    # (set a flag the on_message checks, OR rely on tracker["last_drop"] checks)
                    # example: set a guard flag (optional)
                    # self.cog._tracking_paused = True

                    await asyncio.sleep(self.cog.drop_cooldown)  # non-blocking for callback

                    # reset tracker state after cooldown
                    if tracker_local is not None:
                        tracker_local["users"].clear()
                        tracker_local["count"] = 0
                        # optionally reset last_drop if you want:
                        # tracker_local["last_drop"] = 0

                    # re-enable tracking guard if you used one:
                    # self.cog._tracking_paused = False

                    print(f"Cooldown ended for channel {channel_id_local}")
                except Exception as e:
                    print(f"Post-claim cooldown task error: {e}")

            try:
                asyncio.create_task(_post_claim_cooldown(channel_id, tracker))
            except Exception as e:
                print(f"Failed to start cooldown task: {e}")

        async def on_timeout(self):
            try:
                await self.message.delete()
            except:
                pass

    # --- DROP LOGIC ---
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

    # --- EVENT CHECKER ---
    @tasks.loop(hours=1)
    async def check_event_status(self):
        now = datetime.now()
        if (now.month == 11) or (now.month == 12 and now.day < 24):
            if not self.event_active:
                self.event_active = True
                print("🎄 Christmas event is now ACTIVE!")
        elif (now.month == 12 and now.day == 24 and now.hour == 12) or (now.month == 1 and now.day == 4):
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

    # --- MESSAGE HANDLER ---
    @commands.Cog.listener()
    async def on_message(self, message):
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

        print(f"📊 Activity: {message_count} msgs, {active_users} users, {drop_chance}% chance")

        if drop_chance > 0 and random.randint(1, 100) <= drop_chance:
            if current_time - tracker["last_drop"] < self.drop_cooldown:
                return
            tracker["last_drop"] = time.time()
            tracker["users"].clear()
            tracker["count"] = 0

            drop = self.get_random_drop()
            active_slot = random.randint(0, 3)
            view = self.GiftDropView(self, drop, active_slot, None, data)
            sent = await message.channel.send(view=view)
            view.message = sent

    # --- COMMANDS ---
    @discord.app_commands.command(name="leaderboard", description="Show the top 10 gift collectors")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()

        counts = getattr(data, "gifts", {})
        if not counts:
            await interaction.followup.send("No one has collected any gifts yet! 🎁")
            return

        sorted_users = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        top_10 = sorted_users[:10]

        # build leaderboard text
        leaderboard_text = ""
        for idx, (user_id, gifts_count) in enumerate(top_10, 1):
            user = self.bot.get_user(int(user_id))
            user_mention = user.mention if user else f"<@{user_id}>"
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            leaderboard_text += f"{medal} {user_mention}: **`{gifts_count}`** 🎁\n"

        # get user's own stats
        user_id_str = str(interaction.user.id)
        user_gifts = counts.get(user_id_str, 0)
        user_rank = next((i for i, (uid, _) in enumerate(sorted_users, 1) if uid == user_id_str), None)
        rank_display = f"#{user_rank}" if user_rank else "Unranked"

        # create leaderboard container styled like gift drop
        leaderboard_container = ui.Container(
            ui.TextDisplay("# 🎄 Christmas 2025 Leaderboard"),
            ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True),
            ui.TextDisplay(leaderboard_text or "_No one has collected any gifts yet!_"),
            ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True),
            ui.TextDisplay(f"-# Your Current Rank: **{rank_display}** | Gifts: **`{user_gifts}`**🎁"),
        )
        view = ui.LayoutView(timeout=None)
        view.add_item(leaderboard_container)

        await interaction.followup.send(view=view, allowed_mentions=discord.AllowedMentions.none())


    @discord.app_commands.command(name="christmasstatus", description="Check if the Christmas event is active")
    async def christmasstatus(self, interaction: discord.Interaction):
        if self.is_event_active():
            await interaction.response.send_message("🎄 The Christmas event is **ACTIVE**!")
        else:
            await interaction.response.send_message("❄️ The Christmas event is **INACTIVE**. Runs Nov - Dec 24.")

async def setup(bot):
    await bot.add_cog(ChristmasEvent(bot))
