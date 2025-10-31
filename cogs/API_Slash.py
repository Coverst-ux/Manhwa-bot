import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio

class ComickSlash(commands.Cog):
    BASE_URL = "https://comick-api-proxy.notaspider.dev/api"
    WEB_BASE = "https://comick.dev"
    TIMEOUT = aiohttp.ClientTimeout(total=10)

    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        """Called when cog is loaded."""
        self.session = aiohttp.ClientSession(timeout=self.TIMEOUT)

    async def cog_unload(self):
        """Called when cog is unloaded. Clean up session."""
        if self.session:
            await self.session.close()

    # ---------------- Utility ----------------
    async def fetch_json(self, url, params=None):
        """Fetch JSON from URL. Returns None if fails."""
        if not self.session:
            return None
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    async def search_slug(self, title: str):
        """Return first matching slug and info from title."""
        if not title or not title.strip():
            return None, None
        
        search_url = f"{self.BASE_URL}/v1.0/search"
        data = await self.fetch_json(search_url, params={"q": title, "tachiyomi": "true"})
        
        if not data or len(data) == 0:
            return None, None
        
        top = data[0]
        slug = top.get("slug")
        
        return slug, top if slug else (None, None)

    async def send_embed(self, interaction: discord.Interaction, embed, view=None):
        """Send embed safely with optional buttons."""
        try:
            await interaction.followup.send(embed=embed, view=view)
        except discord.errors.InteractionResponded:
            pass
        except Exception:
            try:
                await interaction.followup.send("⚠️ Failed to send message.")
            except Exception:
                pass

    # ---------------- Commands ----------------
    @app_commands.command(name="search", description="Search for a manga/manhwa by title")
    async def search(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer()
        
        slug, top = await self.search_slug(title)
        if not slug or not top:
            await interaction.followup.send(f"❌ No results found for **{title}**.")
            return

        cover = top.get("cover_url") or top.get("cover")
        desc = (top.get("desc") or "No description available.")
        desc = desc[:300] + "..." if len(desc) > 300 else desc
        url = f"{self.WEB_BASE}/comic/{slug}"

        embed = discord.Embed(
            title=top.get("title", "Unknown Title"),
            url=url,
            description=desc,
            color=0x2b2d31
        )
        if cover:
            embed.set_image(url=cover)
        embed.set_footer(text="Powered by Comick API")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="📖 Read on Comick", url=url))

        await self.send_embed(interaction, embed, view)

    @app_commands.command(name="getdetails", description="Get detailed info about a manga/manhwa")
    async def getdetails(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer()
        
        slug, _ = await self.search_slug(title)
        if not slug:
            await interaction.followup.send(f"❌ No results found for **{title}**.")
            return

        details_url = f"{self.BASE_URL}/comic/{slug}"
        data = await self.fetch_json(details_url)
        if not data:
            await interaction.followup.send("⚠️ Details not found.")
            return

        cover = data.get("cover_url") or data.get("cover")
        desc = data.get("desc") or data.get("description") or "No description available."
        desc = desc[:4000]
        url = f"{self.WEB_BASE}/comic/{slug}"

        embed = discord.Embed(
            title=data.get("title", "Unknown"),
            url=url,
            description=desc,
            color=0x1abc9c
        )
        if cover:
            embed.set_image(url=cover)
        embed.set_footer(text="Powered by Comick API")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="📖 Read on Comick", url=url))

        await self.send_embed(interaction, embed, view)

    @app_commands.command(name="latestchapter", description="Get the latest chapter of a manga/manhwa")
    async def latestchapter(self, interaction: discord.Interaction, title: str):
        await interaction.response.defer()
        
        slug, _ = await self.search_slug(title)
        if not slug:
            await interaction.followup.send(f"❌ No results found for **{title}**.")
            return

        # Fetch comic details to get hid (required for chapters endpoint)
        details_url = f"{self.BASE_URL}/v1.0/comic/{slug}"
        comic_data = await self.fetch_json(details_url)
        if not comic_data:
            await interaction.followup.send("⚠️ Could not fetch comic details.")
            return

        hid = comic_data.get("hid")
        if not hid:
            await interaction.followup.send("⚠️ Comic ID not found.")
            return

        # Use hid to fetch chapters
        chapters_url = f"{self.BASE_URL}/v1.0/comic/{hid}/chapters"
        data = await self.fetch_json(chapters_url, params={"limit": 1, "tachiyomi": "true"})
        if not data:
            await interaction.followup.send("⚠️ Could not fetch chapters.")
            return

        chapters_list = data.get("chapters") or data.get("data") or []
        if not chapters_list:
            await interaction.followup.send("⚠️ No chapters found.")
            return

        latest = chapters_list[0]
        ch_title = latest.get("title") or latest.get("name") or "Unknown Chapter"
        ch_url = latest.get("url") or latest.get("link") or f"{self.WEB_BASE}/comic/{slug}"

        embed = discord.Embed(
            title=ch_title,
            description=f"[Read here]({ch_url})",
            color=0xe67e22
        )
        embed.set_footer(text="Powered by Comick API")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="📖 Read Chapter", url=ch_url))

        await self.send_embed(interaction, embed, view)

# ---------------- Setup ----------------
async def setup(bot):
    await bot.add_cog(ComickSlash(bot))