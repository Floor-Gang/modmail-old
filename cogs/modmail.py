import pytz
import disputils
from asyncpg import ForeignKeyViolationError
from natural.date import duration
from utils.checks import *
from utils.reply import *
from utils.category_selector import *


class ModmailCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn
        self.conf = bot.conf
        self.yellow = 0xE8D90C
        self.green = 0x7CFC00
        self.blue = 0xADD8E6

    # Reply takes a text of max 2048 characters
    #  replies to modmail with the inputted text
    #  sends reply on success, error on failure
    @commands.command(aliases=['r'])
    @commands.guild_only()
    @has_access()
    async def reply(self, ctx, *, message: typing.Optional[str]) -> None:
        if message is None and not ctx.message.attachments:
            raise commands.MissingRequiredArgument(ctx.command)

        if message is not None and (len(message) > 2048):
            await ctx.send(embed=common_embed("Modmail Reply",
                                              "Sorry this message is over 2048 characters, please reduce the "
                                              "character count"))
            return

        conv = await self.db_conn.fetchrow("SELECT conversation_id, user_id \
                                            FROM modmail.conversations \
                                            WHERE \
                                                channel_id=$1 AND active=true",
                                           ctx.channel.id)

        if not conv:
            await ctx.send(embed=common_embed("Modmail Reply",
                                              f"You are currently not in a modmail thread, if you want to create one "
                                              f"look at `{ctx.prefix}help create`"))
            return

        await reply(self.bot, ctx, self.db_conn, conv[1], f'{message} \n', conv[0], attachments=ctx.message.attachments)

    # Reply takes a text of max 2048 characters
    #  replies to modmail with the inputted text anonymously
    #  sends reply on success, error on failure
    @commands.command(aliases=['ar'])
    @has_access()
    @commands.guild_only()
    async def anonymous_reply(self, ctx, *, message: typing.Optional[str]) -> None:
        if message is None and not ctx.message.attachments:
            raise commands.MissingRequiredArgument(ctx.command)

        if message is not None and (len(message) > 2048):
            await ctx.send(embed=common_embed("Modmail Reply",
                                              "Sorry this message is over 2048 characters, please reduce the "
                                              "character count"))
            return

        conv = await self.db_conn.fetchrow("SELECT conversation_id, user_id \
                                            FROM modmail.conversations \
                                            WHERE \
                                               channel_id=$1 AND \
                                               active=true",
                                           ctx.channel.id)

        if not conv:
            await ctx.send(embed=common_embed("Modmail Reply",
                                              f"You are currently not in a modmail thread, if you want to create one "
                                              f"look at `{ctx.prefix}help create`"))
            return

        await reply(self.bot, ctx, self.db_conn, conv[1], message, conv[0], anon=True,
                    attachments=ctx.message.attachments)

    # create takes user discord.Member, int and category int, str.
    #  If category string => Fetches category from string.
    #  Creates modmail thread and notifies the user about it.
    #  Creates channel on success, error on failure.
    @commands.command(aliases=['contact', 'newthread', 'new_thread'])
    @has_access()
    @commands.guild_only()
    async def create(self, ctx, user: discord.Member) -> None:
        main_guild = await self.bot.fetch_guild(self.conf.get('global', 'main_server_id'))

        if not user:
            await ctx.send(embed=common_embed("Create conversation",
                                              "Unable to find that user, please check the id and try again"))
            return

        category, guild = await category_selector.start_embed(self.bot, ctx.channel, ctx.author, True) or (None, None)

        if category is None:
            return

        category_permissions = await self.bot.db_conn.fetch("SELECT role_id \
                                                             FROM modmail.permissions \
                                                             WHERE \
                                                               active=true AND \
                                                               category_id=$1", category.id)

        try:
            if len(set(category_permissions) - set([role.id for role in guild.get_member(ctx.author.id).roles])) == 0:
                await ctx.send(embed=common_embed("Create conversation",
                                                  "You do not have permissions in this category."))
                return
        except:
            if ctx.author.id not in json.loads(self.conf.get('global', 'owners')):
                await ctx.send(embed=common_embed("Create conversation",
                                                  "You do not have permissions in this category."))
                return

        channel = await guild.create_text_channel(name=f'{user.name}-{user.discriminator}', category=category)

        try:
            await self.db_conn.execute("INSERT INTO modmail.conversations \
                                        (creation_date, user_id, active, channel_id, category_id) \
                                        VALUES (now(), $1, true, $2, $3)",
                                       user.id, channel.id, category.id)
        except ForeignKeyViolationError:
            await ctx.send(embed=common_embed("Create conversation",
                                              "The category that was provided is not a valid modmail category, "
                                              "please check your id or name and try again"))
            await channel.delete(reason="Thread Closed")
            return

        past_threads = await self.db_conn.fetch("SELECT * \
                                                 FROM modmail.conversations \
                                                 WHERE \
                                                    user_id=$1 AND \
                                                    active=false",
                                                user.id)
        created_ago, joined_ago = datetime.datetime.now() - user.created_at, datetime.datetime.now() - user.joined_at

        chnl_embed = common_embed("", f"{user.mention} was created {created_ago.days} days ago, "
                                      f"joined {joined_ago.days} days ago"
                                      f" with **{'no' if len(past_threads) == 0 else len(past_threads)}** past threads",
                                  color=0x7289da)
        chnl_embed.set_author(name=str(user), icon_url=user.avatar_url)
        roles = " ".join([role.mention for role in user.roles if role.id != main_guild.id])
        chnl_embed.add_field(name="Roles", value=roles if roles else "No Roles")
        await channel.send(embed=chnl_embed)

        await channel.send(embed=common_embed("Created conversation",
                                              f"Thread created by {ctx.author.mention} for {user.mention}"))

        try:
            await user.send(embed=common_embed("Conversation created", f"A modmail was created to contact {user}"))

        except discord.Forbidden:
            await channel.send(embed=common_embed("Create conversation",
                                                  "The user has dm's disabled so I can't reach out\n"
                                                  "This thread will get deleted in 15 seconds..."))
            await asyncio.sleep(15)
            await self.db_conn.execute("UPDATE modmail.conversations \
                                        SET closing_date=now(), active=false \
                                        WHERE \
                                          channel_id=$1",
                                       channel.id)
            await channel.delete(reason="Thread Closed")

        else:
            await ctx.message.add_reaction('✅')
            await asyncio.sleep(10)
            await ctx.message.delete()

    # Close takes no arguments
    #  closes the modmail thread aka channel
    #  sends confirmation on success, error on failure
    @commands.command()
    @has_access()
    @commands.guild_only()
    async def close(self, ctx) -> None:
        conv = await self.db_conn.fetchrow("SELECT user_id \
                                            FROM modmail.conversations \
                                            WHERE \
                                                channel_id=$1",
                                           ctx.channel.id)
        if not conv:
            await ctx.send(embed=common_embed("Close conversation",
                                              "You're in a invalid channel, please check if you're in a "
                                              "conversation channel"))
            return

        user = await self.bot.fetch_user(user_id=conv[0])
        try:
            await user.send(embed=common_embed("Conversation closed",
                                               "The conversation was closed, we hope that we were able to help you!"))
        except discord.Forbidden:
            await ctx.send(embed=common_embed("Conversation closed",
                                              "The user disabled dm's so no message's arrived"))
        finally:
            await self.db_conn.execute("UPDATE modmail.conversations \
                                        SET closing_date=now(), active=false \
                                        WHERE \
                                            channel_id=$1",
                                       ctx.channel.id)
            await ctx.send(embed=common_embed("Conversation closed", "This channel will get deleted in 10 seconds..."))
            await asyncio.sleep(10)

        await ctx.channel.delete(reason="Thread Closed")

    # edit takes message str max size of 2048 characters
    #  Checks on what side it is on
    #  If on mod side => edits the most recent message made by mod
    #  If on user side => Edits the most recent message and notifies the mods about it and shows original state
    #  Edits message on success error on failure.
    @commands.command()
    async def edit(self, ctx, *, message: str) -> None:
        """Edit the most recent message in thread made by you"""
        if ctx.guild is None:
            results = await self.db_conn.fetchrow("SELECT messages.message_id, messages.other_side_message_id, \
                                                          conversations.user_id, conversations.channel_id, \
                                                          messages.message \
                                                   FROM modmail.messages \
                                                   INNER JOIN modmail.conversations \
                                                   ON messages.conversation_id = conversations.conversation_id \
                                                   WHERE conversations.user_id=$1 AND messages.made_by_mod = false AND messages.deleted = false \
                                                   ORDER BY messages.created_at DESC \
                                                   LIMIT 1", ctx.author.id)
            if not results:
                await ctx.send(embed=common_embed("Edit message", "You have not sent any messages in this thread yet"))
                return

            mod_chnl = await self.bot.fetch_channel(results[3])

            mod_msg = await mod_chnl.fetch_message(results[1])

            usr_embed = common_embed("Successfully edited the message", message, color=self.yellow)
            usr_embed.add_field(name="Original Message:", value=results[4])
            usr_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
            usr_embed.set_footer(text=f"Message ID: {results[0]} (edited)")

            thread_embed = common_embed("", message, color=self.green)
            thread_embed.add_field(name="Edited, original message:", value=results[4])
            thread_embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
            thread_embed.set_footer(text=f"Message ID: {results[0]} (edited)")

            await ctx.send(embed=usr_embed)
            await mod_msg.edit(embed=thread_embed)

        else:
            results = await self.db_conn.fetchrow("SELECT messages.message_id, messages.other_side_message_id, \
                                                          conversations.user_id \
                                                   FROM modmail.messages \
                                                   INNER JOIN modmail.conversations \
                                                   ON messages.conversation_id = conversations.conversation_id \
                                                   WHERE \
                                                      conversations.channel_id = $1 AND \
                                                      messages.made_by_mod = true AND \
                                                      deleted = false AND \
                                                      messages.author_id = $2 \
                                                   ORDER BY messages.created_at DESC \
                                                   LIMIT 1",
                                                  ctx.channel.id, ctx.author.id)
            if not results:
                await ctx.send(embed=common_embed("Edit message", "There's no message made in this thread yet"))
                return

            usr = await self.bot.fetch_user(results[2])

            mod_msg = await ctx.channel.fetch_message(results[0])
            usr_msg = await usr.dm_channel.fetch_message(results[1])

            mod_new_embed = mod_msg.embeds[0]
            mod_new_embed.description = message

            usr_new_embed = usr_msg.embeds[0]
            usr_new_embed.description = message

            await usr_msg.edit(embed=usr_new_embed)
            await mod_msg.edit(embed=mod_new_embed)

        await self.db_conn.execute("UPDATE modmail.messages \
                                    SET message=$1 \
                                    WHERE \
                                        message_id=$2",
                                   message, results[0])
        await self.db_conn.execute("UPDATE modmail.all_messages_attachments \
                                    SET message=$1 \
                                    WHERE \
                                        message_id=$2",
                                   message, results[0])

        await ctx.message.add_reaction('✅')

    # Delete takes optional message parameter
    #  Only available for mods, user runs on event
    #  If message parameter is supplied => locates that message and deletes it
    #  If there is a message to delete => Deletes the message on user and mod side
    #  Returns reaction on success, error on failure
    @commands.command()
    @has_access()
    @commands.guild_only()
    async def delete(self, ctx, message: typing.Optional[int]) -> None:
        if message is None:
            results = await self.db_conn.fetchrow("SELECT messages.message_id, messages.other_side_message_id, \
                                                          conversations.user_id \
                                                   FROM modmail.messages \
                                                   INNER JOIN modmail.conversations \
                                                   ON messages.conversation_id = conversations.conversation_id \
                                                   WHERE \
                                                        conversations.channel_id = $1 AND \
                                                        messages.made_by_mod = true AND \
                                                        deleted = false \
                                                   ORDER BY messages.created_at DESC \
                                                   LIMIT 1", ctx.channel.id)
            if not results:
                await ctx.send(
                    embed=common_embed("Delete message", "There's no message made by mods in this thread yet"))
                return

            mod_msg: discord.Message = await ctx.channel.fetch_message(results[0])

        else:

            mod_msg: discord.Message = await ctx.channel.fetch_message(message)
            results = await self.db_conn.fetchrow("SELECT messages.message_id, messages.other_side_message_id, \
                                                          conversations.user_id \
                                                   FROM modmail.messages \
                                                   INNER JOIN modmail.conversations \
                                                   ON messages.conversation_id = conversations.conversation_id \
                                                   WHERE \
                                                        messages.message_id = $1 AND \
                                                        messages.made_by_mod = true AND \
                                                        deleted = false \
                                                   ORDER BY messages.created_at DESC \
                                                   LIMIT 1", message)
            if not results:
                await ctx.send(embed=common_embed("Delete message",
                                                  "Unable to locate a message with that ID, please check the ID and try again"))
                return

        usr = await self.bot.fetch_user(results[2])
        usr_msg: discord.Message = await usr.dm_channel.fetch_message(results[1])

        await mod_msg.delete()
        await usr_msg.delete()
        await self.db_conn.execute("UPDATE modmail.messages \
                                    SET deleted=true \
                                    WHERE \
                                        message_id=$1", results[0])
        await self.db_conn.execute("UPDATE modmail.all_messages_attachments \
                                    SET deleted=true \
                                    WHERE \
                                        message_id=$1", results[0])

        await ctx.message.add_reaction('✅')

    # forward takes no arguments
    #  Sends category selector embed
    #  Forwards the conversation to the selected category
    #  Sends every previous message in new thread and deletes old channel
    #  Returns confirmation on success, error on failure
    @commands.command()
    @has_access()
    @commands.guild_only()
    async def forward(self, ctx) -> None:
        category, guild = await category_selector.start_embed(self.bot, ctx.channel, ctx.author, True) or (None, None)

        if category is None:
            return
        elif category == ctx.channel.category:
            await ctx.send(
                embed=common_embed("Forward conversation", f"This conversation is already in category {category.name}"))

        usr_db = await self.db_conn.fetchrow("SELECT user_id, conversation_id \
                                              FROM modmail.conversations \
                                              WHERE \
                                                channel_id=$1", ctx.channel.id)
        user = await self.bot.fetch_user(usr_db[0])

        channel = await guild.create_text_channel(name=f"{user.name}-{user.discriminator}", category=category)

        past_threads = await self.db_conn.fetch("SELECT conversation_id \
                                                 FROM modmail.conversations \
                                                 WHERE \
                                                    user_id=$1 AND \
                                                    active=false",
                                                user.id)

        created_ago = datetime.datetime.now() - user.created_at

        await channel.send(embed=common_embed("", f"{user.mention} was created {created_ago.days} days ago"
                                                  f" with **{'no' if len(past_threads) == 0 else len(past_threads)}** "
                                                  f"past threads"))
        await channel.send(embed=common_embed("Forwarded conversation",
                                              f"Conversation forwarded by {ctx.author.mention} from "
                                              f"{ctx.channel.category.name}"))
        messages = await self.db_conn.fetch("SELECT message, made_by_mod, author_id, message_id \
                                             FROM modmail.all_messages_attachments \
                                             WHERE \
                                                conversation_id=$1 AND \
                                                deleted=false",
                                            usr_db[1])

        internal_messages = await self.db_conn.fetch("SELECT * \
                                                      FROM modmail.messages \
                                                      WHERE \
                                                        conversation_id=$1 AND \
                                                        deleted=false",
                                                     usr_db[1])

        for row in messages:
            author = await self.bot.fetch_user(row[2])

            if row[3] in internal_messages:
                thread_embed = common_embed("", row[0], color=self.green if row[1] else self.yellow)
            else:
                thread_embed = common_embed("", "**Internal Message:**\n" + row[0], color=self.blue)

            thread_embed.set_author(name=str(author), icon_url=author.avatar_url)
            thread_embed.set_footer(text="Forwarded message")

            msg = await channel.send(embed=thread_embed)

            await self.db_conn.execute("UPDATE modmail.all_messages_attachments \
                                        SET message_id=$1 \
                                        WHERE \
                                            message_id=$2",
                                       msg.id, row[3])

            if row[3] in internal_messages:
                await self.db_conn.execute("UPDATE modmail.messages \
                                            SET message_id=$1 \
                                            WHERE \
                                                message_id=$2",
                                           msg.id, row[3])

        await self.db_conn.execute("UPDATE modmail.conversations \
                                    SET channel_id = $1 \
                                    WHERE \
                                        conversation_id=$2",
                                   channel.id, usr_db[1])

        await user.send(embed=common_embed("Conversation forward", f"You were forwarded to {channel.category.name}"))
        await ctx.send(embed=common_embed("Conversation forward",
                                          "The conversation was successfully forwarded. This channel will get deleted "
                                          "in 10 seconds"))
        await asyncio.sleep(10)
        await ctx.channel.delete()

    # Logs takes optional user discord.Member, int
    #  displays the discord user's past modmails in pages
    #  sends paginator(s) on success, error on failure
    @commands.command()
    @has_access()
    @commands.guild_only()
    async def logs(self, ctx: commands.Context, user: typing.Optional[typing.Union[discord.Member, int]]) -> None:
        if user is None:
            result = await self.db_conn.fetchrow("SELECT user_id \
                                                  FROM modmail.conversations \
                                                  WHERE \
                                                     channel_id = $1",
                                                 ctx.channel.id)
            if not result:
                await ctx.send(
                    embed=common_embed(title="Not Found",
                                       description="Unable to locate modmail thread, please specify the id"))
                return

            user = await self.bot.fetch_user(result[0])

        else:
            if isinstance(user, int):
                user = await self.bot.fetch_user(user)

            if not user:
                await ctx.send(embed=common_embed("Create conversation",
                                                  "Unable to find that user, please check the id and try again"))
                return

        embeds = list()

        conversations = await self.db_conn.fetch("SELECT conversations.conversation_id, conversations.created_at,\
                                                         conversations.closing_date, categories.category_name, \
                                                         categories.category_id \
                                                  FROM modmail.conversations \
                                                  INNER JOIN modmail.categories \
                                                  ON conversations.category_id = categories.category_id \
                                                  WHERE \
                                                    conversations.active=false AND \
                                                    conversations.user_id=$1 \
                                                  ORDER BY created_at DESC", user.id)
        if conversations:
            async with ctx.typing():
                for row in conversations:
                    embed = common_embed("", f"ID: {row[0]}")
                    embed.set_author(name=f"Total Results Found ({len(conversations)}) - {user}",
                                     icon_url=user.avatar_url)
                    embed.add_field(name="Created", value=duration(row[1], now=datetime.datetime.now(pytz.utc)))
                    embed.add_field(name="Closed", value=duration(row[1], now=datetime.datetime.now(pytz.utc)))
                    embed.add_field(name="Category", value=f"{row[3].capitalize()} ({row[4]})")

                    messages = await self.db_conn.fetch("SELECT message, author_id, deleted, made_by_mod \
                                                         FROM modmail.messages \
                                                         WHERE \
                                                            conversation_id=$1 \
                                                         ORDER BY created_at", row[0])
                    embed_messages = list()

                    for index, message in enumerate(messages, 1):
                        if message[2]:
                            embed_messages.append(
                                f'[{index}] - ~~{message[0]}~~ ~ <@{message[1]}> {"(mod)" if message[3] else ""}')
                        else:
                            embed_messages.append(
                                f'[{index}] - {message[0]} ~ <@{message[1]}> {"(mod)" if message[3] else ""}')

                    embed.add_field(name="Messages:",
                                    value="\n".join(embed_messages if embed_messages else ["No messages"]),
                                    inline=False)
                    embeds.append(embed)

            await disputils.BotEmbedPaginator(ctx, embeds).run()
        else:
            await ctx.send(embed=common_embed('Logs', f'No prior logs found for {user}'))


def setup(bot):
    bot.add_cog(ModmailCog(bot))
