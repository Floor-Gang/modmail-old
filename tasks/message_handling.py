import discord
from discord.ext import commands
from utils.common_embed import *
import asyncio


class messageHandlingTasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn
        self.yellow = 0xE8D90C
        self.green = 0x7CFC00

    @commands.Cog.listener(name='on_message')
    async def dm_message_listener(self, message: discord.Message) -> None:
        if message.guild is None:
            if (message.content.startswith(self.bot.command_prefix)) or (message.author == self.bot.user):
                return

            conv = await self.db_conn.fetchrow(
                "SELECT conversation_id, channel_id FROM modmail.conversations WHERE user_id=$1 AND active=true",
                message.author.id)
            if not conv:
                try:
                    categories = await self.db_conn.fetch(
                        "SELECT category_name, emote_id FROM modmail.categories WHERE active=true")
                    embed = common_embed('Category Selector',
                                         'Please react with the corresponding emote for your desired category')

                    embed.add_field(name='Available categories: ',
                                    value='\n'.join([f'{row[0].capitalize()} = {row[1]}' for row in categories]))
                    msg = await message.channel.send(embed=embed)

                    for row in categories:
                        await msg.add_reaction(row[1])

                    reaction, _ = await self.bot.wait_for('reaction_add',
                                                          check=lambda react,
                                                                       user: react.message.id == msg.id and user == message.author,
                                                          timeout=30)

                    db_category = await self.db_conn.fetchrow(
                        "SELECT category_id, guild_id FROM modmail.categories WHERE emote_id=$1 AND active=true",
                        reaction.emoji)
                    if not db_category:
                        await msg.edit(embed=common_embed('Invalid Reaction',
                                                          "What the heck, you should be using the existing emotes not new ones. Please restart the process and try again"))
                        return

                    category = self.bot.get_channel(db_category[0])
                    guild = self.bot.get_guild(db_category[1])
                    channel = await guild.create_text_channel(f'{message.author.name}-{message.author.discriminator}',
                                                              category=category)

                    past_threads = await self.db_conn.fetch(
                        "SELECT * FROM modmail.conversations WHERE user_id=$1 AND active=false",
                        message.author.id)

                    user = guild.get_member(message.author.id)

                    created_ago = datetime.datetime.now() - user.created_at
                    joined_ago = datetime.datetime.now() - user.joined_at

                    chnl_embed = discord.Embed(color=0x7289da)
                    chnl_embed.set_author(name=str(user), icon_url=user.avatar_url)
                    chnl_embed.description = f"{user.mention} was created {created_ago.days} days ago, " \
                                             f"joined {joined_ago.days} days ago" \
                                             f" with **{'no' if len(past_threads) == 0 else len(past_threads)}** past threads"
                    roles = " ".join([role.mention for role in user.roles if not role.is_default()])
                    chnl_embed.add_field(name='Roles', value=roles if roles else 'No Roles')
                    await channel.send(embed=chnl_embed)

                    thread_embed = common_embed('', message.content, color=self.yellow)
                    thread_embed.set_author(name=message.author, icon_url=message.author.avatar_url)
                    thread_embed.set_footer(text=f"Message ID: {message.id}")
                    thread_msg = await channel.send(embed=thread_embed)

                    await self.db_conn.execute("INSERT INTO modmail.conversations \
                                               (creation_date, user_id, active, channel_id, category_id)\
                                               VALUES (now(), $1, true, $2, $3)",
                                               message.author.id, channel.id, category.id)

                    conv_id = await self.db_conn.fetchrow(
                        "SELECT conversation_id FROM modmail.conversations WHERE channel_id=$1", channel.id)

                    await self.db_conn.execute("INSERT INTO modmail.messages \
                                               (message_id, message, author_id, conversation_id, other_side_message_id, made_by_mod)\
                                               VALUES ($1, $2, $3, $4, $5, false)",
                                               message.id, message.content, message.author.id, conv_id[0],
                                               thread_msg.id)

                    usr_embed = common_embed('Message send',
                                             f'\'{message.content}\'\n\n *if this isn\'t correct you can change it with {self.bot.command_prefix}edit*',
                                             color=self.green)
                    usr_embed.set_author(name=message.author, icon_url=message.author.avatar_url)
                    usr_embed.set_footer(text=f"Message ID: {message.id}")
                    await message.channel.send(embed=usr_embed)

                except asyncio.TimeoutError:
                    await message.channel.send(
                        "You didn't answer in time, please restart the process by sending your message again")
                    return

            else:
                channel = await self.bot.fetch_channel(conv[1])
                thread_embed = common_embed('', message.content, color=self.yellow)
                thread_embed.set_author(name=message.author, icon_url=message.author.avatar_url)
                thread_embed.set_footer(text=f"Message ID: {message.id}")
                thread_msg = await channel.send(embed=thread_embed)

                usr_embed = common_embed('Message send',
                                         f'\'{message.content}\'\n\n *if this isn\'t correct you can change it with {self.bot.command_prefix}edit*',
                                         color=self.green)
                usr_embed.set_author(name=message.author, icon_url=message.author.avatar_url)
                usr_embed.set_footer(text=f"Message ID: {message.id}")
                await message.channel.send(embed=usr_embed)
                await self.db_conn.execute("INSERT INTO modmail.messages \
                                           (message_id, message, author_id, conversation_id, other_side_message_id, made_by_mod)\
                                           VALUES ($1, $2, $3, $4, $5, false)",
                                           message.id, message.content, message.author.id, conv[0], thread_msg.id)

    @commands.Cog.listener(name='on_message_delete')
    async def dm_delete_listener(self, message: discord.Message) -> None:
        if message.guild is None:
            conv = await self.db_conn.fetchrow(
                "SELECT conversation_id, channel_id FROM modmail.conversations WHERE user_id=$1 AND active=true",
                message.author.id)
            if conv:
                db_msg = await self.db_conn.fetchrow(
                    "SELECT other_side_message_id FROM modmail.messages WHERE message_id=$1 AND conversation_id=$2",
                    message.id, conv[0])

                thread_channel = await self.bot.fetch_channel(conv[1])
                thread_msg = await thread_channel.fetch_message(db_msg[0])

                thread_embed = common_embed('', message.content, color=self.yellow)
                thread_embed.set_author(name=message.author, icon_url=message.author.avatar_url)
                thread_embed.set_footer(text=f"Message ID: {message.id} (deleted)")

                await thread_msg.edit(embed=thread_embed)
                await self.db_conn.execute("UPDATE modmail.messages SET deleted=true WHERE message_id=$1", message.id)


def setup(bot):
    bot.add_cog(messageHandlingTasks(bot))
