from discord.ext import tasks, commands
from discord import app_commands
import discord
import asyncio
import aiosqlite
import aiohttp
import traceback
import math
from typing import Optional

class AddManhwaComick(commands.Cog):
    BASE_URL = "https://comick-api-proxy.notaspider.dev/api"
    WEB_BASE = "https://comick.dev"
    TIMEOUT = aiohttp.ClientTimeout(total=10)

    def __init__(self, bot):
        self.bot = bot
        self._chapter_check_task = None
        self.session = None
        print("[AddManhwaComick] Cog initialized")

    async def cog_load(self):
        """runs when cog is loaded by discord.py; start tasks here."""
        print("[AddManhwaComick] Cog loaded - initializing DB and starting task")
        self.session = aiohttp.ClientSession(timeout=self.TIMEOUT)
        await self.init_db()
        await self.init_chapter_tracking_db()
        # create and start the repeated task safely
        if self._chapter_check_task is None:
            self._chapter_check_task = tasks.loop(hours=24)(self._chapter_check_loop)
            self._chapter_check_task.before_loop(self._before_chapter_check)
            self._chapter_check_task.start()

    async def cog_unload(self):
        """called when the cog is unloaded — stop background tasks cleanly."""
        print("[AddManhwaComick] Unloading cog: stopping tasks")
        if self._chapter_check_task and self._chapter_check_task.is_running():
            self._chapter_check_task.cancel()
        if self.session:
            await self.session.close()

    # ============ DATABASE ============
    async def init_db(self):
        try:
            async with aiosqlite.connect('manhwa.db') as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS manhwas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        title TEXT NOT NULL,
                        cover TEXT,
                        link TEXT NOT NULL
                    )
                ''')
                await db.commit()
            print("[AddManhwaComick] Manhwas table initialized")
        except Exception as e:
            print(f"[AddManhwaComick] Manhwas table init failed: {e}")
            traceback.print_exc()

    async def init_chapter_tracking_db(self):
        try:
            async with aiosqlite.connect('manhwa.db') as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS chapter_tracking (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        manhwa_title TEXT,
                        manhwa_slug TEXT,
                        latest_chapter_notified REAL,
                        last_notified_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, manhwa_slug)
                    )
                ''')
                await db.commit()
            print("[AddManhwaComick] Chapter tracking table initialized")
        except Exception as e:
            print(f"[AddManhwaComick] Chapter tracking table init failed: {e}")
            traceback.print_exc()

    # ============ UTILITIES ============
    async def fetch_json(self, url: str, params: Optional[dict] = None, retries: int = 2, timeout: int = 10):
        """Fetch JSON from API with basic retries and timeout."""
        if not self.session:
            return None
            
        for attempt in range(1, retries + 2):
            try:
                async with self.session.get(url, params=params) as resp:
                    if resp.status != 200:
                        print(f"[AddManhwaComick] API returned {resp.status} for {url} (attempt {attempt})")
                        if attempt <= retries:
                            await asyncio.sleep(1)
                            continue
                        return None
                    return await resp.json()
            except asyncio.TimeoutError:
                print(f"[AddManhwaComick] API request timeout for {url} (attempt {attempt})")
                if attempt <= retries:
                    await asyncio.sleep(1)
                    continue
                return None
            except Exception as e:
                print(f"[AddManhwaComick] Fetch error for {url} (attempt {attempt}): {e}")
                if attempt <= retries:
                    await asyncio.sleep(1)
                    continue
                return None

    async def search_slug(self, title: str):
        search_url = f"{self.BASE_URL}/v1.0/search"
        print(f"[AddManhwaComick] Searching for: {title}")
        data = await self.fetch_json(search_url, params={"q": title, "tachiyomi": "true"})
        if not data:
            print(f"[AddManhwaComick] No results for: {title}")
            return None, None
        top = data[0]
        slug = top.get("slug")
        print(f"[AddManhwaComick] Found: {top.get('title', title)} (slug: {slug})")
        return slug, top

    # ============ SLASH COMMANDS ============
    @app_commands.command(name="add_manhwa", description="Add a manhwa to your list using Comick API")
    async def add_manhwa(self, interaction: discord.Interaction, title: str):
        print(f"[AddManhwaComick] add_manhwa called by {interaction.user} with title: {title}")
        await interaction.response.defer()
        
        slug, top = await self.search_slug(title)
        if not slug:
            await interaction.followup.send(f"❌ No results found for **{title}**.")
            return

        cover = top.get("cover_url") or top.get("cover")
        url = f"{self.WEB_BASE}/comic/{slug}"

        try:
            async with aiosqlite.connect('manhwa.db') as db:
                await db.execute(
                    "INSERT INTO manhwas (user_id, title, cover, link) VALUES (?, ?, ?, ?)",
                    (interaction.user.id, top.get("title", title), cover, url)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO chapter_tracking (user_id, manhwa_title, manhwa_slug, latest_chapter_notified) VALUES (?, ?, ?, ?)",
                    (interaction.user.id, top.get("title", title), slug, 0)
                )
                await db.commit()
            print(f"[AddManhwaComick] Inserted {top.get('title', title)} for user {interaction.user.id}")
        except Exception as e:
            print(f"[AddManhwaComick] Database insert failed: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ Failed to save to database. Try again.")
            return

        embed = discord.Embed(
            title=top.get("title", title),
            url=url,
            description="✅ Added to your list!",
            color=0x2b2d31
        )
        if cover:
            embed.set_image(url=cover)
        embed.set_footer(text="Powered by Comick API")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="remove_manhwa", description="Remove a manhwa from your list")
    async def remove_manhwa(self, interaction: discord.Interaction, title: str):
        print(f"[AddManhwaComick] remove_manhwa called by {interaction.user} for: {title}")
        await interaction.response.defer()
        try:
            async with aiosqlite.connect('manhwa.db') as db:
                async with db.execute("SELECT link FROM manhwas WHERE title = ? AND user_id = ?", (title, interaction.user.id)) as cursor:
                    row = await cursor.fetchone()
                if not row:
                    await interaction.followup.send(f"❌ **{title}** not found in your list.")
                    return
                link = row[0]
                slug = link.split("/comic/")[1] if "/comic/" in link else None
                cursor = await db.execute("DELETE FROM manhwas WHERE title = ? AND user_id = ?", (title, interaction.user.id))
                rows_deleted = cursor.rowcount
                if slug:
                    await db.execute("DELETE FROM chapter_tracking WHERE user_id = ? AND manhwa_slug = ?", (interaction.user.id, slug))
                await db.commit()
            if rows_deleted == 0:
                await interaction.followup.send(f"❌ **{title}** not found in your list.")
            else:
                await interaction.followup.send(f"🗑️ Removed **{title}** from your list!")
        except Exception as e:
            print(f"[AddManhwaComick] Database delete failed: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ Failed to remove. Try again.")

    @app_commands.command(name="list_manhwas", description="List all your saved manhwas")
    async def list_manhwas(self, interaction: discord.Interaction):
        print(f"[AddManhwaComick] list_manhwas called by {interaction.user}")
        await interaction.response.defer()
        try:
            async with aiosqlite.connect('manhwa.db') as db:
                async with db.execute("SELECT title, link FROM manhwas WHERE user_id = ? ORDER BY title ASC", (interaction.user.id,)) as cursor:
                    rows = await cursor.fetchall()

            if not rows:
                await interaction.followup.send("📭 You don't have any saved manhwas yet.")
                return

            formatted = "\n".join([f"• {r[0]} — {r[1]}" for r in rows])
            embed = discord.Embed(
                title=f"{interaction.user.display_name}'s Manhwa List",
                description=formatted,
                color=0x3498db
            )
            embed.set_footer(text=f"{len(rows)} manhwa(s)")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"[AddManhwaComick] Database query failed: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ Failed to load your list. Try again.")

    # ============ BACKGROUND TASK ============

    async def _before_chapter_check(self):
        await self.bot.wait_until_ready()
        print("[AddManhwaComick] Bot ready, chapter check task will start now")

    async def _chapter_check_loop(self):
        print("[AddManhwaComick] Running chapter check...")
        try:
            user_updates = {}
            async with aiosqlite.connect('manhwa.db') as db:
                async with db.execute("SELECT user_id, manhwa_title, manhwa_slug, latest_chapter_notified FROM chapter_tracking") as cursor:
                    rows = await cursor.fetchall()

            print(f"[AddManhwaComick] Checking {len(rows)} tracked manhwas")
            for user_id, manhwa_title, manhwa_slug, latest_notified in rows:
                try:
                    # Step 1: Fetch comic details to get hid and cover
                    details_url = f"{self.BASE_URL}/v1.0/comic/{manhwa_slug}"
                    comic_data = await self.fetch_json(details_url)
                    if not comic_data:
                        print(f"[AddManhwaComick] Could not fetch details for {manhwa_title}")
                        continue

                    comic_obj = comic_data.get("comic", {})
                    hid = comic_obj.get("hid")
                    if not hid:
                        print(f"[AddManhwaComick] No hid found in comic object for {manhwa_title}")
                        continue

                    # Get cover from comic object
                    cover_url = comic_obj.get("cover_url") or comic_obj.get("cover")

                    # Step 2: Fetch latest chapters from endpoint using hid
                    chapters_url = f"{self.BASE_URL}/v1.0/comic/{hid}/chapters"
                    chapters_data = await self.fetch_json(chapters_url, params={"limit": 1, "tachiyomi": "true"})
                    if not chapters_data:
                        continue

                    chapters_list = chapters_data.get("chapters") or chapters_data.get("data") or []
                    if not chapters_list:
                        continue

                    latest_chapter_obj = chapters_list[0]
                    chap_val = latest_chapter_obj.get("chap") or latest_chapter_obj.get("chapter") or 0
                    # safe parse -> float if possible, else 0
                    try:
                        latest_chapter_num = float(chap_val)
                    except Exception:
                        # fallback: try to extract numeric prefix
                        latest_chapter_num = 0.0
                        for part in str(chap_val).split():
                            try:
                                latest_chapter_num = float(part)
                                break
                            except Exception:
                                continue

                    chapter_title = latest_chapter_obj.get("title", "")
                    chapter_hid = latest_chapter_obj.get("hid", "") or latest_chapter_obj.get("id", "")
                    chapter_link = f"{self.WEB_BASE}/comic/{manhwa_slug}/chapter/{chapter_hid}"

                    if latest_chapter_num > (latest_notified or 0):
                        if user_id not in user_updates:
                            user_updates[user_id] = []
                        user_updates[user_id].append({
                            "title": manhwa_title,
                            "chapter": latest_chapter_num,
                            "chapter_title": chapter_title,
                            "link": chapter_link,
                            "cover": cover_url
                        })
                        # update DB immediately
                        async with aiosqlite.connect('manhwa.db') as db:
                            await db.execute(
                                "UPDATE chapter_tracking SET latest_chapter_notified = ?, last_notified_time = CURRENT_TIMESTAMP WHERE user_id = ? AND manhwa_slug = ?",
                                (latest_chapter_num, user_id, manhwa_slug)
                            )
                            await db.commit()
                except Exception as e:
                    print(f"[AddManhwaComick] Error checking {manhwa_title}: {e}")
                    traceback.print_exc()

            # Send DMs for each user, with small delay to avoid rate limits
            print(f"[AddManhwaComick] Sending updates to {len(user_updates)} users")
            for uid, updates in user_updates.items():
                try:
                    user = await self.bot.fetch_user(uid)
                    
                    # Single embed with all updates
                    embed = discord.Embed(
                        title="📚 Your Manhwas Have New Chapters!",
                        description=f"**{len(updates)}** new chapter(s) since last check:",
                        color=0x2b2d31
                    )
                    
                    # Add first cover as main image
                    if updates and updates[0]['cover']:
                        embed.set_image(url=updates[0]['cover'])
                    
                    for update in updates:
                        chapter_num = int(update['chapter']) if update['chapter'] == int(update['chapter']) else update['chapter']
                        chapter_info = f"**Chapter {chapter_num}**"
                        if update['chapter_title']:
                            chapter_info += f"\n_{update['chapter_title']}_"
                        chapter_info += f"\n[Read here]({update['link']})"
                        embed.add_field(name=update['title'], value=chapter_info, inline=False)
                    
                    embed.set_footer(text="Powered by Comick")
                    await user.send(embed=embed)
                    await asyncio.sleep(1)
                    print(f"[AddManhwaComick] Sent {len(updates)} updates to {uid}")
                except Exception as e:
                    print(f"[AddManhwaComick] Failed to send DM to {uid}: {e}")
                    traceback.print_exc()

        except Exception as e:
            print(f"[AddManhwaComick] Chapter check failed: {e}")
            traceback.print_exc()


# setup function for load_extension
async def setup(bot):
    cog = AddManhwaComick(bot)
    await bot.add_cog(cog)
    print("[AddManhwaComick] Cog added")