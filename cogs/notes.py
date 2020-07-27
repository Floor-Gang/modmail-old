"""
create table modmail.notes
(
    id bigserial
        constraint notes_pk
            primary key,
    conversation_id bigint not null,
    user_id bigint not null,
    made_by_id bigint not null,
    note varchar not null,
    created_at timestamp with time zone,
    last_update_at timestamp with time zone
);
"""
import typing
import discord

from utils.checks import *

"""

commands:
!addnote <note>
!notes <user_id (optional, if not given it is the user id of the modmail channel where the command is issued)>
!editnote <note_id> <new_text> **ONLY ACCESSIBLE BY MOD WHO MADE THE NOTE**
!note <note_id>
!deletenote <note_id> **ONLY ACCESSIBLE BY MOD WHO MADE THE NOTE**

"""


class notesCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db_conn = bot.db_conn

    # addnote takes note str
    #  Creates note for user in current modmail thread
    #  Checks if in modmail thread
    #  Returns confirmation on success, error on failure
    @commands.command()
    @is_owner()
    async def addnote(self, ctx, *, note: str) -> None:
        conv = await self.db_conn.fetchrow(
            "SELECT conversation_id, user_id FROM modmail.conversations WHERE channel_id = $1",
            ctx.channel.id)
        if not conv:
            await ctx.send("You aren't in a valid modmail channel, if this is incorrect please contact my makers")
            return

        try:
            await self.db_conn.execute('INSERT INTO modmail.notes '
                                       '(conversation_id, user_id, made_by_id, note) VALUES ($1, $2, $3, $4)',
                                       conv[0], conv[1], ctx.author.id, note)

        finally:
            await ctx.send(f"Inserted the note for user id: {conv[1]}")

    @addnote.error
    async def addnote_error(self, ctx, err: any) -> None:
        if isinstance(err, commands.CheckFailure):
            await ctx.send("Sorry, you don't have permission to run this command")

        elif isinstance(err, commands.BadArgument):
            await ctx.send("I'm missing the note argument, please try again")

        else:
            await ctx.send(f"Unknown error occurred.\n{str(err)}")

    # Notes takes an optional user [discord.Member, str].
    #   if user is not provided it looks for a modmail thread.
    #   retrieves all notes made for user in database.
    #   returns results on success, error on failure.
    @commands.command()
    @is_owner()
    async def notes(self, ctx, user: typing.Optional[typing.Union[discord.Member, str]]) -> None:
        if user is None:
            result = await self.db_conn.fetchrow("SELECT user_id FROM modmail.conversations WHERE channel_id = $1",
                                                 ctx.channel.id)
            if not result:  # Sorry for this spaghetti code
                await ctx.send("Unable to locate modmail thread, please specify the id")
                return

            user = await self.bot.fetch_user(result[0])

        elif isinstance(user, str):
            try:
                user = await self.bot.fetch_user(int(user))
            except (commands.CommandInvokeError, ValueError, discord.NotFound):
                await ctx.send("Unable to locate user, please check if the id is correct")
                return

        try:
            db_notes = await self.db_conn.fetch(
                "SELECT id, user_id, made_by_id, note FROM modmail.notes WHERE user_id = $1 ORDER BY id", user.id)

            paginator = commands.Paginator()
            for row in db_notes:
                user = await self.bot.fetch_user(row[1])
                created_by = await self.bot.fetch_user(row[2])
                paginator.add_line(f'ID: {row[0]}\n\n'
                                   f'User: {user}\n'
                                   f'Created By: {created_by}\n'
                                   f'Note: "{str(row[3])}"\n'
                                   f'--------------------------------\n')

        finally:
            for page in paginator.pages:
                await ctx.send(embed=discord.Embed(color=discord.Color.red(), description=page))

    @notes.error
    async def notes_error(self, ctx, err: any) -> None:
        if isinstance(err, commands.CheckFailure):
            await ctx.send("Sorry, you don't have permission to run this command")
        else:
            await ctx.send(f"Unknown error occurred.\n{str(err)}")

    # editnote takes note_id int and new_text str
    #  Checks if user has access to edit this note,
    #  if user has access edits note in database.
    #  returns confirmation on success, error on failure
    @commands.command()
    @is_owner()
    async def editnote(self, ctx, note_id: int, *, new_text: str) -> None:
        results = await self.db_conn.fetchrow("SELECT made_by_id FROM modmail.notes WHERE id = $1", note_id)
        if results[0] != ctx.author.id:
            await ctx.send("You do not have access to edit this note, or the note doesn't exist")
            return

        try:
            await self.db_conn.execute("UPDATE modmail.notes SET note = $1 WHERE id = $2",
                                       new_text, note_id)
        finally:
            await ctx.send(f"Updated `{note_id}` to \"{new_text}\"")

    @editnote.error
    async def editnote_error(self, ctx, err: any) -> None:
        if isinstance(err, commands.CheckFailure):
            await ctx.send("Sorry, you don't have permission to run this command")
        elif isinstance(err, commands.BadArgument):
            await ctx.send("I'm missing an argument, please check if both the id and the new text are provided")
        else:
            await ctx.send(f"Unknown error occurred.\n{str(err)}")

    # note takes note_id int
    #  retrieves note information from database
    #  returns results on success, error on failure
    @commands.command()
    @is_owner()
    async def note(self, ctx, note_id: int) -> None:
        results = await self.db_conn.fetchrow("SELECT id, user_id, made_by_id, note FROM modmail.notes WHERE id = $1",
                                              note_id)
        if not results:
            await ctx.send("Unable to locate note, please check the id and try again")

        try:
            user = await self.bot.fetch_user(results[1])
            created_by = await self.bot.fetch_user(results[2])
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f'`ID: {results[0]}\n\n'
                                              f'User: {user}\n'
                                              f'Created By: {created_by}\n'
                                              f'Note: "{str(results[3])}"\n`')
        finally:
            await ctx.send(embed=embed)

    @note.error
    async def note_error(self, ctx, err: any):
        if isinstance(err, commands.CheckFailure):
            await ctx.send("Sorry, you don't have permission to run this command")
        elif isinstance(err, commands.BadArgument):
            await ctx.send("I'm missing an argument, please check if the id is provided")
        else:
            await ctx.send(f"Unknown error occurred.\n{str(err)}")

    # note takes note_id int
    #  Checks if user has access to delete this note,
    #  if user has access deletes note from database.
    #  returns confirmation on success, error on failure
    @commands.command()
    @is_owner()
    async def deletenote(self, ctx, note_id: int):
        results = await self.db_conn.fetchrow("SELECT made_by_id FROM modmail.notes WHERE id = $1", note_id)
        if results[0] != ctx.author.id:
            await ctx.send("You do not have access to delete this note, or the note doesn't exist")
            return

        try:
            await self.db_conn.execute("DELETE FROM modmail.notes WHERE id = $1", note_id)
        finally:
            await ctx.send(f'Successfully deleted note with id: `{note_id}`')

    @deletenote.error
    async def deletenote_error(self, ctx, err: any):
        if isinstance(err, commands.CheckFailure):
            await ctx.send("Sorry, you don't have permission to run this command")
        elif isinstance(err, commands.BadArgument):
            await ctx.send("I'm missing an argument, please check if the id is provided")
        else:
            await ctx.send(f"Unknown error occurred.\n{str(err)}")


def setup(bot):
    bot.add_cog(notesCog(bot))
