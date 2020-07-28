from discord.ext import tasks, commands
import discord
from datetime import datetime
from modmailmain import Config


class verifyCategoriesTasks(commands.Cog):
    def __init__(self, bot):
        self.bot: discord.Client = bot
        self.db_conn = bot.db_conn
        self.verify_categories.start()

    @tasks.loop(minutes=5.0)
    async def verify_categories(self) -> None:
        try:
            results = await self.db_conn.fetch("SELECT category_id, category_name \
                                               FROM modmail.categories \
                                               WHERE active=true")
            print(results)
            for row in results:
                print(row, "one for loop")
                category = self.bot.get_channel(row[0])
                print(category.name.lower() != row[1].lower())
                if category is None:
                    # channel_id = int(Config.conf.get('global', 'modmail_commands_channel_id'))
                    chnl = self.bot.get_channel(702188203955978346)
                    embed: discord.Embed = discord.Embed(title="Categories not correctly synced!", color=0xB00B69)
                    embed.timestamp = datetime.now()
                    embed.description = f"Category ID: `{row[0]}` is not correctly synced.\n\n" \
                                        f"**Category '{row[1]}' does not exist or isn't accessible by the bot.\n\n**" \
                                        f"Please fix this issue as soon as possible"
                    embed.set_image(url='https://i.imgur.com/b8y71CJ.gif')
                    await chnl.send(embed=embed)
                    await chnl.send("<@357918459058978816>")

                elif category.name.lower() != row[1].lower():
                    chnl = self.bot.get_channel(702188203955978346)

                    embed: discord.Embed = discord.Embed(title="Categories not correctly synced!", color=0xB00B69)
                    embed.timestamp = datetime.now()
                    embed.description = f"Category {row[0]} is not correctly synced.\n\n" \
                                        f"**Category is named '{row[1]}' in database but is actually called '{category.name}'\n\n**" \
                                        f"Please fix this as soon as possible"
                    embed.set_image(url='https://i.imgur.com/b8y71CJ.gif')
                    await chnl.send(embed=embed)
                    await chnl.send("<@357918459058978816>")
        except Exception as e:
            raise e

    @verify_categories.before_loop
    async def before_verify_categories(self) -> None:
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(verifyCategoriesTasks(bot))
