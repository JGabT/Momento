import asyncio
from typing import Union
import aiohttp
import discord
import re
import wavelink
import datetime
import humanize
import itertools
from discord.ext import commands, menus, buttons

RURL = re.compile('https?:\/\/(?:www\.)?.+')


class MusicController:

    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.channel = None

        self.next = asyncio.Event()
        self.queue = asyncio.Queue()

        self.volume = 40
        self.now_playing = None

        self.bot.loop.create_task(self.controller_loop())

    async def controller_loop(self):
        await self.bot.wait_until_ready()

        player = self.bot.wavelink.get_player(self.guild_id)
        await player.set_volume(self.volume)

        while True:
            if self.now_playing:
                await self.now_playing.delete()

            self.next.clear()

            song = await self.queue.get()
            await player.play(song)
            self.now_playing = await self.bot.get_channel(self.guild_id).send(f'Now playing: `{song}`')

            await self.next.wait()


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.controllers = {}

        if not hasattr(bot, 'wavelink'):
            self.bot.wavelink = wavelink.Client(bot=self.bot)

        self.bot.loop.create_task(self.start_nodes())

    async def start_nodes(self):
        await self.bot.wait_until_ready()

        # Initiate our nodes. For this example we will use one server.
        # Region should be a discord.py guild.region e.g sydney or us_central (Though this is not technically required)
        node = await self.bot.wavelink.initiate_node(host='198.37.25.234',
                                              port=2333,
                                              rest_uri='http://198.37.25.234:2333',
                                              password='youshallnotpass',
                                              identifier='TEST',
                                              region='sydney')

        node.set_hook(self.on_event_hook)

    async def on_event_hook(self, event):
        """Node hook callback."""
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            controller = self.get_controller(event.player)
            controller.next.set()


    def get_controller(self, value: Union[commands.Context, wavelink.Player]):
        if isinstance(value, commands.Context):
            gid = value.guild.id
        else:
            gid = value.guild_id

        try:
            controller = self.controllers[gid]
        except KeyError:
            controller = MusicController(self.bot, gid)
            self.controllers[gid] = controller

        return controller

    async def cog_check(self, ctx):
        """A local check which applies to all commands in this cog."""
        if not ctx.guild:
            raise commands.NoPrivateMessage
        return True

    @commands.guild_only()
    @commands.command(name="connect", pass_context=True)
    async def connect(self, ctx, *, channel: discord.VoiceChannel=None):
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise discord.DiscordException('No channel to join. Please either specify a valid channel or join one.')
        
        player = self.bot.wavelink.get_player(ctx.guild.id)
        message = await ctx.send(f'Connecting to **`{channel.name}`**...')
        await player.connect(channel.id)
        if channel:
            try:
                await message.edit(content=f"Connected to **`{channel.name}`**")
            except PermissionError:
                await message.edit(content=f"<:redTick:596576672149667840> An error occured, Owner has been notified...")


    @commands.guild_only()
    @commands.command()
    async def play(self, ctx, *, query: str):
        """Search for and add a song to the Queue."""
        if not RURL.match(query):
            query = f'ytsearch:{query}'

        tracks = await self.bot.wavelink.get_tracks(f'{query}')

        if not tracks:
            return await ctx.send('Could not find any songs with that query.')

        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not player.is_connected:
            await ctx.invoke(self.connect)

        track = tracks[0]

        controller = self.get_controller(ctx)
        await controller.queue.put(track)
        await ctx.send(f'Added {str(track)} to the queue.', delete_after=15)

    @play.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        raise error

    @commands.command()
    async def pause(self, ctx):
        """Pause the player."""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not player.is_playing:
            return await ctx.send('I am not currently playing anything!', delete_after=15)

        await ctx.send('Pausing the song!', delete_after=15)
        await player.set_pause(True)
    @pause.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        raise error    

    @commands.command()
    async def resume(self, ctx):
        """Resume the player from a paused state."""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not player.paused:
            return await ctx.send('I am not currently paused!', delete_after=15)

        await ctx.send('Resuming the player!', delete_after=15)
        await player.set_pause(False)

    @resume.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        raise error

    @commands.command()
    async def skip(self, ctx):
        """Skip the currently playing song."""
        player = self.bot.wavelink.get_player(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('I am not currently playing anything!', delete_after=15)

        await ctx.send('Skipping the song!', delete_after=15)
        await player.stop()

    @skip.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"<:redTick:596576672149667840> {error}")
        raise error

    @commands.command()
    async def volume(self, ctx, *, vol: int):
        """Set the player volume."""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        controller = self.get_controller(ctx)

        vol = max(min(vol, 1000), 0)
        controller.volume = vol

        await ctx.send(f'Setting the player volume to `{vol}`')
        await player.set_volume(vol)

    @commands.command(aliases=['np', 'current', 'nowplaying'])
    async def now_playing(self, ctx):
        """Retrieve the currently playing song."""
        player = self.bot.wavelink.get_player(ctx.guild.id)

        if not player.current:
            return await ctx.send('I am not currently playing anything!')

        controller = self.get_controller(ctx)
        #await controller.now_playing.delete()

        controller.now_playing = await ctx.send(f'Now playing: `{player.current}`')
    
    @commands.command(aliases=['q'])
    async def queue(self, ctx):
        """Retrieve information on the next 5 songs from the queue."""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        controller = self.get_controller(ctx)

        if not player.current or not controller.queue._queue:
            return await ctx.send('There are no songs currently in the queue.', delete_after=20)

        upcoming = list(itertools.islice(controller.queue._queue, 0, 5))

        fmt = '\n'.join(f'**`{str(song)}`**' for song in upcoming)
        embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=fmt)

        await ctx.send(embed=embed)

    @commands.command(name="m-info")
    async def m_info(self, ctx):
        """Retrieve various Node/Server/Player information."""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        node = player.node

        used = humanize.naturalsize(node.stats.memory_used)
        total = humanize.naturalsize(node.stats.memory_allocated)
        free = humanize.naturalsize(node.stats.memory_free)
        cpu = node.stats.cpu_cores

        fmt = f'**WaveLink:** `{wavelink.__version__}`\n\n' \
              f'Connected to `{len(self.bot.wavelink.nodes)}` nodes.\n' \
              f'Best available Node `{self.bot.wavelink.get_best_node().__repr__()}`\n' \
              f'`{len(self.bot.wavelink.players)}` players are distributed on nodes.\n' \
              f'`{node.stats.players}` players are distributed on server.\n' \
              f'`{node.stats.playing_players}` players are playing on server.\n\n' \
              f'Server Memory: `{used}/{total}` | `({free} free)`\n' \
              f'Server CPU: `{cpu}`\n\n' \
              f'Server Uptime: `{datetime.timedelta(milliseconds=node.stats.uptime)}`'
        await ctx.send(fmt)

        @commands.command(aliases=['disconnect', 'dc'])
        async def stop(self, ctx):
            """Stop and disconnect the player and controller."""
            player = self.bot.wavelink.get_player(ctx.guild.id)

            try:
                del self.controllers[ctx.guild.id]
            except KeyError:
                await player.disconnect()
                return await ctx.send('There was no controller to stop.')

            await player.disconnect()
            await ctx.send('Disconnected player and killed controller.', delete_after=20)


def setup(bot):
    bot.add_cog(Music(bot))