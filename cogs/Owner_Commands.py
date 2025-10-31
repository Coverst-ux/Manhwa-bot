import discord
from discord.ext import commands

class OwnerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="shutdown", description="Shuts down the bot. Owner only.")
    @commands.is_owner()
    async def shutdown(self, ctx):
        """Shuts down the bot."""
        await ctx.send("Shutting down...")
        await self.bot.close()
        
async def setup(bot):
    await bot.add_cog(OwnerCommands(bot))