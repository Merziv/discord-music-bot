import random
import discord
import youtube_dl
from discord.ext import commands
import requests
import re
import json
import asyncio

with open("config.json", "r", encoding="utf-8") as config_file:
    config_data = json.load(config_file)

bot_token = config_data["bot_token"]
api_token = config_data["api_token"]
ffmpeg_path = config_data["ffmpeg_path"]

intents = discord.Intents().all()
bot = commands.Bot(command_prefix='!', intents=intents)

playlist_queue = []

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'default_search': 'auto',
    'socket_timeout': 10,
}


@bot.command()
async def play(ctx, *, query):
    print(f"Query: {query}")

    voice_channel = ctx.author.voice.channel
    if voice_channel is None:
        await ctx.send("Musisz być na kanale głosowym, aby używać tej komendy.")
        return

    if ctx.voice_client is None:
        voice_client = await voice_channel.connect()
    else:
        voice_client = ctx.voice_client

    if r"playlist?list=" in query:
        playlist_id = extract_playlist_id(query)
        if not playlist_id:
            await ctx.send("Nieprawidłowy link do playlisty.")
            return

        playlist_info = get_playlist_info(playlist_id)
        if not playlist_info:
            await ctx.send("Nie można pobrać informacji o playliście.")
            return

        if len(playlist_info) > 0:
            await ctx.send(f"Odtwarzanie playlisty z YouTube: {query} <:notoco:906996516487581697>")
        else:
            await ctx.send("Nie znaleziono utworów w playliście.")

        playlist_queue.extend(playlist_info)

        if not voice_client.is_playing():
            await play_song(ctx)

    else:
        playlist_queue.append(query)
        if not voice_client.is_playing():
            await play_song(ctx)


def extract_playlist_id(url):
    pattern = r"(?:list=|/playlist\?list=)([a-zA-Z0-9_-]{34})"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_playlist_info(playlist_id):
    try:
        api_key = api_token
        playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
        response = requests.get(playlist_url)
        if response.status_code == 200:
            playlist_items = response.json().get('items')
            if playlist_items:
                playlist_info_list = []
                for item in playlist_items:
                    print(item)
                    title = item['snippet']['title']
                    url = f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}"
                    song = {
                        'title': title,
                        'url': url,
                    }
                    playlist_info_list.append(song)
                return playlist_info_list
        return None
    except requests.exceptions.RequestException:
        return None


async def play_song(ctx):
    if not playlist_queue:
        return

    if ctx.voice_client.is_playing():
        return

    song = playlist_queue.pop(0)
    voice_client = ctx.voice_client

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        search_results = ydl.extract_info(f"ytsearch:{song}", download=False)

        if 'entries' in search_results:
            video_info = search_results['entries'][0]
        else:
            video_info = search_results

        video_url = video_info['url']
        print_url = video_info['webpage_url']

        await ctx.send(f"Odtwarzanie muzyki z YouTube: {print_url} <:notoco:906996516487581697>\n")

        source = discord.FFmpegPCMAudio(executable=ffmpeg_path,
                                        source=video_url)

        voice_client.play(source, after=lambda _: bot.loop.create_task(next_song(ctx)))


async def next_song(ctx):
    if not playlist_queue:
        voice_client = ctx.voice_client
        await voice_client.disconnect()
        return
    await asyncio.sleep(1)
    await play_song(ctx)


@bot.command()
async def shuffle(ctx):
    if not playlist_queue:
        await ctx.send("Kolejka utworów jest pusta.")
        return

    random.shuffle(playlist_queue)
    await ctx.send("Kolejka utworów została przemieszana.")


@bot.command()
async def queue(ctx):
    if not playlist_queue:
        await ctx.send("Kolejka utworów jest pusta.")
        return

    num_tracks = min(len(playlist_queue), 10)
    track_list = "\n".join([f"{i + 1}. {playlist_queue[i]['title']}" for i in range(num_tracks)])

    await ctx.send(f"Kolejka utworów ({len(playlist_queue)} utworów):\n{track_list}")


@bot.command()
async def skip(ctx):
    voice_client = ctx.voice_client

    if voice_client.is_playing():
        voice_client.stop()
        await ctx.send("Pominięto bieżący utwór. Przechodzę do następnego...")
        await asyncio.sleep(3)
        await next_song(ctx)
    else:
        await ctx.send("Aktualnie nie odtwarzam żadnego utworu.")


@bot.command()
async def leave(ctx):
    voice_channel = ctx.voice_client
    if voice_channel.is_connected():
        playlist_queue.clear()
        await voice_channel.disconnect()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')


@bot.event
async def on_interrupt():
    print("Bot został przerwany. Zamykanie...")
    playlist_queue.clear()
    await bot.close()


if __name__ == "__main__":
    bot.run(bot_token)
