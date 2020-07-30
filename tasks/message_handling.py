import discord
from discord.ext import commands


class messageHandlingTasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn

    @commands.Cog.listener(name='on_message')
    async def dm_listener(self, ctx, message: discord.Message):
        if message.guild is None:

