import asyncio

from asyncpg import ForeignKeyViolationError
from asyncpg.pool import Pool

from utils.checks import *
from utils.common_embed import *
import datetime
import typing
import discord


class ModmailCog(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.db_conn: Pool = bot.db_conn
        self.conf = bot.conf
        self.yellow = 0xE8D90C
        self.green = 0x7CFC00

    # Reply takes a text of max 2048 characters
    #  replies to modmail with the inputted text
    #  sends reply on success, error on failure
    @commands.command(aliases=['r'])
    @is_owner()
    async def reply(self, ctx: commands.Context, *, message: str) -> None:
        if len(message) > 2048:  # Checks if message is over 2048 characters
            await ctx.send(embed=common_embed('Modmail Reply',
                                              'Sorry this message is over 2048 characters, please reduce the character count'))
            return

        conv = await self.db_conn.fetchrow(
            "SELECT conversation_id, user_id FROM modmail.conversations WHERE channel_id=$1 AND active=true",
            ctx.channel.id)

        if not conv:  # Checks if command is executed in a modmail thread
            await ctx.send(embed=common_embed('Modmail Reply',
                                              f'You are currently not in a modmail thread, if you want to create one look at `{ctx.prefix}help create`'))
            return

        user = self.bot.get_user(conv[1])

        usr_embed = common_embed('', message, color=self.yellow)
        usr_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        usr_embed.set_footer(text=ctx.author.roles[-1].name)
        usr_msg = await user.send(embed=usr_embed)

        thread_embed = common_embed('', message, color=self.green)
        thread_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        thread_embed.set_footer(text=ctx.author.roles[-1].name)
        mod_msg = await ctx.send(embed=thread_embed)

        await self.db_conn.execute("INSERT INTO modmail.messages \
                                   (message_id, message, author_id, conversation_id, other_side_message_id, made_by_mod)\
                                   VALUES ($1, $2, $3, $4, $5, true)",
                                   mod_msg.id, message, ctx.author.id, conv[0], usr_msg.id)

        await ctx.message.delete()

    @commands.command(aliases=['ar'])
    @is_owner()
    async def anonymous_reply(self, ctx, *, message: str) -> None:
        if len(message) > 2048:  # Checks if message is over 2048 characters
            await ctx.send(embed=common_embed('Modmail Reply',
                                              'Sorry this message is over 2048 characters, please reduce the character count'))
            return

        conv = await self.db_conn.fetchrow(
            "SELECT conversation_id, user_id FROM modmail.conversations WHERE channel_id=$1 AND active=true",
            ctx.channel.id)

        if not conv:  # Checks if command is executed in a modmail thread
            await ctx.send(embed=common_embed('Modmail Reply',
                                              f'You are currently not in a modmail thread, if you want to create one look at `{ctx.prefix}help create`'))
            return

        user = self.bot.get_user(conv[1])

        usr_embed = discord.Embed(color=self.yellow)
        usr_embed.set_author(name="Anonymous")
        usr_embed.timestamp = datetime.datetime.now()
        usr_embed.description = message
        usr_msg = await user.send(embed=usr_embed)

        thread_embed = discord.Embed(color=self.green)
        thread_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        thread_embed.set_footer(text="Anonymous Reply")
        thread_embed.timestamp = datetime.datetime.now()
        thread_embed.description = message
        mod_msg = await ctx.send(embed=thread_embed)

        await self.db_conn.execute("INSERT INTO modmail.messages \
                                   (message_id, message, author_id, conversation_id, other_side_message_id, made_by_mod)\
                                   VALUES ($1, $2, $3, $4, $5, true)",
                                   mod_msg.id, message, ctx.author.id, conv[0], usr_msg.id)

        await ctx.message.delete()

    @commands.command()
    @is_owner()
    async def create(self, ctx: commands.Context, user: typing.Union[discord.Member, int],
                     category: typing.Union[int, str]) -> None:
        if isinstance(user, int):
            user = await self.bot.fetch_user(user)

        if not user:
            await ctx.send(embed=common_embed('Create conversation',
                                              "Unable to find that user, please check the id and try again"))
            return

        if isinstance(category, int):
            category: discord.CategoryChannel = self.bot.get_channel(category)
        elif isinstance(category, str):
            category = discord.utils.get(ctx.guild.categories, name=category.lower())
            if not category:
                await ctx.send(embed=common_embed('Create conversation',
                                                  "Unable to fetch that category please check spelling or use the id"))
                return

        channel = await ctx.guild.create_text_channel(name=f'{user.name}-{user.discriminator}', category=category)

        try:
            await self.db_conn.execute("INSERT INTO modmail.conversations \
                                       (creation_date, user_id, active, channel_id, category_id)\
                                       VALUES (now(), $1, true, $2, $3)",
                                       user.id, channel.id, category.id)
        except ForeignKeyViolationError:
            await ctx.send(embed=common_embed('Create conversation',
                                              'The category that was provided is not a valid modmail category, please check your id or name and try again'))
            await channel.delete(reason='Thread Closed')
            return

        past_threads = await self.db_conn.fetch("SELECT * FROM modmail.conversations WHERE user_id=$1 AND active=false",
                                                user.id)

        created_ago = datetime.datetime.now() - user.created_at
        joined_ago = datetime.datetime.now() - user.joined_at

        chnl_embed = discord.Embed(color=0x7289da)
        chnl_embed.set_author(name=str(user), icon_url=user.avatar_url)
        chnl_embed.description = f"{user.mention} was created {created_ago.days} days ago, " \
                                 f"joined {joined_ago.days} days ago" \
                                 f" with **{'no' if len(past_threads) == 0 else len(past_threads)}** past threads"
        roles = " ".join([role.mention for role in user.roles if role.id != ctx.guild.id])
        chnl_embed.add_field(name='Roles', value=roles if roles else 'No Roles')
        await channel.send(embed=chnl_embed)

        await channel.send(
            embed=common_embed('Created conversation', f'Thread created by {ctx.author.mention} for {user.mention}'))

        try:
            await user.send(embed=common_embed('Conversation created', 'A modmail was created to contact you'))
        except discord.Forbidden:
            await channel.send(embed=common_embed('Create conversation',
                                                  'The user has dm\'s disabled so I can\'t reach out\n'
                                                  'This thread will get deleted in 15 seconds...'))
            await asyncio.sleep(15)
            await self.db_conn.execute(
                "UPDATE modmail.conversations SET closing_date=now(), active=false WHERE channel_id=$1",
                channel.id)
            await channel.delete(reason='Thread Closed')

        else:
            await ctx.send(
                embed=common_embed('Create conversation', f'The conversation was created at {channel.mention}'))

    # Close takes no arguments
    #  closes the modmail thread aka channel
    #  sends error on failure
    @commands.command()
    @is_owner()
    async def close(self, ctx) -> None:
        conv = await self.db_conn.fetchrow("SELECT user_id FROM modmail.conversations WHERE channel_id=$1",
                                           ctx.channel.id)
        if not conv:
            await ctx.send(embed=common_embed('Close conversation',
                                              'You\'re in a invalid channel, please check if you\'re in a conversation channel'))
            return

        user = await self.bot.fetch_user(user_id=conv[0])
        try:
            await user.send(embed=common_embed('Conversation closed',
                                               'The conversation was closed, hope that we were able to help you!'))
        except discord.Forbidden:
            await ctx.send(
                embed=common_embed('Conversation closed', 'The user disabled dm\'s so no message\'s arrived'))
        finally:
            await self.db_conn.execute(
                "UPDATE modmail.conversations SET closing_date=now(), active=false WHERE channel_id=$1",
                ctx.channel.id)
            await ctx.send(embed=common_embed('Conversation closed', 'This channel will get deleted in 10 seconds...'))
            await asyncio.sleep(10)

        await ctx.channel.delete(reason='Thread Closed')

    @commands.command()
    @is_owner()
    async def edit(self, ctx, *, message: str) -> None:
        results = await self.db_conn.fetchrow("SELECT messages.message_id, messages.other_side_message_id, conversations.user_id\
                                              FROM modmail.messages\
                                              INNER JOIN modmail.conversations\
                                              ON messages.conversation_id = conversations.conversation_id\
                                              WHERE conversations.channel_id = $1 AND messages.made_by_mod = true AND deleted = false\
                                              ORDER BY messages.created_at DESC LIMIT 1", ctx.channel.id)
        if not results:
            await ctx.send(embed=common_embed('Edit message', 'Theres no message made in this thread yet'))
            return

        usr = await self.bot.fetch_user(results[2])
        usr_chnl = await self.bot.fetch_channel(usr.dm_channel.id)

        mod_msg: discord.Message = await ctx.channel.fetch_message(results[0])
        usr_msg: discord.Message = await usr_chnl.fetch_message(results[1])

        usr_embed = common_embed('', message, color=self.yellow)
        usr_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        usr_embed.set_footer(text=ctx.author.roles[-1].name)

        thread_embed = common_embed('', message, color=self.green)
        thread_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        thread_embed.set_footer(text=ctx.author.roles[-1].name)

        await usr_msg.edit(embed=usr_embed)
        await mod_msg.edit(embed=thread_embed)

        await self.db_conn.execute("UPDATE modmail.messages SET message=$1 WHERE message_id=$2", message, results[0])

        await ctx.message.add_reaction('✅')

    @commands.command()
    @is_owner()
    async def delete(self, ctx) -> None:
        results = await self.db_conn.fetchrow("SELECT messages.message_id, messages.other_side_message_id, conversations.user_id\
                                              FROM modmail.messages\
                                              INNER JOIN modmail.conversations\
                                              ON messages.conversation_id = conversations.conversation_id\
                                              WHERE conversations.channel_id = $1 AND messages.made_by_mod = true AND deleted = false\
                                              ORDER BY messages.created_at DESC LIMIT 1", ctx.channel.id)
        if not results:
            await ctx.send(embed=common_embed('Delete message', 'Theres no message made by mods in this thread yet'))
            return

        usr = await self.bot.fetch_user(results[2])
        usr_chnl = await self.bot.fetch_channel(usr.dm_channel.id)

        mod_msg: discord.Message = await ctx.channel.fetch_message(results[0])
        usr_msg: discord.Message = await usr_chnl.fetch_message(results[1])

        await mod_msg.delete()
        await usr_msg.delete()
        await self.db_conn.execute("UPDATE modmail.messages SET deleted=true WHERE message_id=$1", results[0])

        await ctx.message.add_reaction('✅')

    @commands.command()
    @is_owner()
    async def forward(self, ctx, category: typing.Union[int, str]) -> None:
        if isinstance(category, int):
            if ctx.channel.category.id == category:
                await ctx.send(embed=common_embed('Forward conversation', 'The conversation is already in that thread'))
                return

            cat_db = await self.db_conn.fetchrow(
                'SELECT category_id, guild_id FROM modmail.categories WHERE category_id = $1',
                category)
            if not cat_db:
                await ctx.send(embed=common_embed('Forward conversation',
                                                  "I can't find the category related to that id please check if its correct"))
                return

        else:
            if ctx.channel.category.name == category:
                await ctx.send(embed=common_embed('Forward conversation', 'The conversation is already in that thread'))
                return

            cat_db = await self.db_conn.fetchrow(
                'SELECT category_id, guild_id FROM modmail.categories WHERE lower(category_name) = lower($1)',
                category)
            if not cat_db:
                await ctx.send(embed=common_embed('Create conversation',
                                                  "Unable to fetch that category please check spelling or use the id"))
                return
        usr_db = await self.db_conn.fetchrow(
            'SELECT user_id, conversation_id FROM modmail.conversations WHERE channel_id=$1', ctx.channel.id)

        guild: discord.Guild = self.bot.get_guild(cat_db[1]) if not ctx.guild.id == cat_db[1] else ctx.guild
        category: discord.CategoryChannel = await self.bot.fetch_channel(cat_db[0])
        user: discord.User = await self.bot.fetch_user(usr_db[0])

        channel = await guild.create_text_channel(name=f"{user.name}-{user.discriminator}", category=category)

        past_threads = await self.db_conn.fetch("SELECT * FROM modmail.conversations WHERE user_id=$1 AND active=false",
                                                user.id)

        created_ago = datetime.datetime.now() - user.created_at

        await channel.send(embed=common_embed('', f"{user.mention} was created {created_ago.days} days ago"
                                                  f" with **{'no' if len(past_threads) == 0 else len(past_threads)}** past threads"))
        await channel.send(embed=common_embed('Forwarded conversation',
                                              f'Conversation forwarded by {ctx.author.mention} from {ctx.channel.category.name}'))
        messages = await self.db_conn.fetch(
            "SELECT message, made_by_mod, author_id, message_id FROM modmail.messages WHERE conversation_id=$1 AND deleted=false",
            usr_db[1])

        for row in messages:
            author = await self.bot.fetch_user(row[2])

            thread_embed = common_embed('', row[0], color=self.green if row[1] else self.yellow)
            thread_embed.set_author(name=str(author), icon_url=author.avatar_url)
            thread_embed.set_footer(text='Forwarded message')
            msg = await channel.send(embed=thread_embed)

            await self.db_conn.execute("UPDATE modmail.messages SET message_id=$1 WHERE message_id=$2",
                                       msg.id, row[3])

        await self.db_conn.execute("UPDATE modmail.conversations SET channel_id = $1 WHERE conversation_id=$2",
                                   channel.id, usr_db[1])

        await user.send(embed=common_embed('Conversation forward', f"You were forwarded to {channel.category.name}"))
        await ctx.send(embed=common_embed('Conversation forward', 'The conversation was successfully forwarded this channel will get deleted in 10 seconds'))
        await asyncio.sleep(10)
        await ctx.channel.delete()

    # Logs takes no arguments
    #  displays the discord user's past modmails (Perhaps in paginator(s)?)
    #  sends paginator(s) on success, error on failure
    @commands.command()
    @is_owner()
    async def logs(self, ctx):
        await ctx.send("Displaying logs")


def setup(bot):
    bot.add_cog(ModmailCog(bot))
