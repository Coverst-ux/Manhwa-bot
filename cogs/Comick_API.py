# cogs/Comick_API_Prefix.py
import discord
from discord.ext import commands
import aiohttp
import traceback

class APIClient(commands.Cog):
    BASE_URL = "https://comick-api-proxy.notaspider.dev/api"
    WEB_BASE = "https://comick.dev"

    def __init__(self, bot):
        self.bot = bot

    # ---------------- Utility ----------------
    async def fetch_json(self, url, params=None):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except Exception:
            traceback.print_exc()
            return None

    async def search_slug(self, title: str):
        search_url = f"{self.BASE_URL}/v1.0/search"
        data = await self.fetch_json(search_url, params={"q": title, "tachiyomi": "true"})
        if not data:
            return None, None
        top = data[0]
        return top.get("slug"), top

    async def send_embed(self, ctx, embed, view=None):
        try:
            await ctx.send(embed=embed, view=view)
        except Exception:
            traceback.print_exc()

    # ---------------- Commands ----------------
    @commands.command(name="search", help="Search for a manhwa by title.")
    async def search_manhwa(self, ctx, *, title: str):
        slug, top = await self.search_slug(title)
        if not slug:
            await ctx.send(f"❌ No results found for **{title}**.")
            return

        cover = top.get("cover_url") or top.get("cover")
        desc = (top.get("desc") or "No description available.")[:300] + "..."
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
        await self.send_embed(ctx, embed, view)

    @commands.command(name="getdetails", help="Get detailed info about a manhwa.")
    async def get_manhwa_details(self, ctx, *, title: str):
        slug, _ = await self.search_slug(title)
        if not slug:
            await ctx.send(f"❌ No results found for **{title}**.")
            return

        details_url = f"{self.BASE_URL}/comic/{slug}"
        data = await self.fetch_json(details_url)
        if not data:
            await ctx.send("⚠️ Details not found.")
            return

        cover = data.get("cover_url") or data.get("cover")
        desc = data.get("desc") or data.get("description") or "No description available."
        url = f"{self.WEB_BASE}/comic/{slug}"

        embed = discord.Embed(
            title=data.get("title", "Unknown"),
            url=url,
            description=desc[:4000],
            color=0x1abc9c
        )
        if cover:
            embed.set_image(url=cover)
        embed.set_footer(text="Powered by Comick API")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="📖 Read on Comick", url=url))
        await self.send_embed(ctx, embed, view)

    @commands.command(name="latestchapter", help="Get the latest chapter of a manhwa.")
    async def latest_chapter(self, ctx, *, title: str):
        slug, _ = await self.search_slug(title)
        if not slug:
            await ctx.send(f"❌ No results found for **{title}**.")
            return

        chapters_url = f"{self.BASE_URL}/comic/{slug}/chapters?tachiyomi=true"
        data = await self.fetch_json(chapters_url)
        if not data:
            await ctx.send("⚠️ Could not fetch chapters.")
            return

        chapters_list = []

        # Flatten chapters from 'volumes'
        if "volumes" in data:
            for vol in data["volumes"].values():
                chapters_list.extend(vol.get("chapters", []))

        # Fallback to 'chapters'
        if not chapters_list and "chapters" in data:
            chapters_list = data["chapters"]

        if not chapters_list:
            await ctx.send("⚠️ No chapters found.")
            return

        # Sort chapters by numeric 'number', fallback to last item
        def chapter_sort_key(ch):
            try:
                return float(ch.get("number", 0))
            except (ValueError, TypeError):
                return 0

        chapters_list.sort(key=chapter_sort_key, reverse=True)
        latest = chapters_list[0]

        ch_title = latest.get("title") or latest.get("name") or f"Chapter {latest.get('number', '?')}"
        ch_url = latest.get("url") or latest.get("link") or f"{self.WEB_BASE}/comic/{slug}"

        embed = discord.Embed(
            title=ch_title,
            description=f"[Read here]({ch_url})",
            color=0xe67e22
        )
        embed.set_footer(text="Powered by Comick API")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="📖 Read Chapter", url=ch_url))
        await self.send_embed(ctx, embed, view)

# ---------------- Setup ----------------
def setup(bot):
    bot.add_cog(APIClient(bot))

async def setup(bot):
    await bot.add_cog(APIClient(bot))
