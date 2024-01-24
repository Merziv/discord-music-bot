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
max_retries = 5
processing_song = False

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'extract_flat': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn -threads 1',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin -preset ultrafast'
}


@bot.command(aliases=['playtop', 'ptop', "pt"])
async def play_top(ctx, *, query):
    global playlist_queue
    if r"youtube.com/playlist?list=" not in query:
        playlist_queue = [query] + playlist_queue
        await ctx.send(f"Dodano '{query}' na początek kolejki <:notoco:906996516487581697>")


@bot.command(aliases=['p'])
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

    async with ctx.typing():
        if r"youtube.com/playlist?list=" not in query:
            playlist_queue.append(query)

        else:
            playlist_id = extract_playlist_id(query)
            if not playlist_id:
                await ctx.send("Nieprawidłowy link do playlisty.")
                return

            playlist_info = get_playlist_info(playlist_id)
            if not playlist_info:
                await ctx.send("Nie można pobrać informacji o playliście.")
                return

            if not len(playlist_info) > 0:
                await ctx.send("Nie znaleziono utworów w playliście.")
                return

            playlist_queue.extend(playlist_info)
            await ctx.send(f"Odtwarzanie playlisty: {query} <:notoco:906996516487581697>")

        if not voice_client.is_playing():
            await play_song(ctx)
        else:
            await ctx.send(f"Dodano '{query}' na koniec kolejki <:notoco:906996516487581697>")


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
                    title = item['snippet']['title']
                    if title == ("Deleted video" or "Private video"):
                        continue
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
    global processing_song

    if processing_song:
        return

    if ctx.voice_client.is_playing():
        return

    if not playlist_queue:
        return

    async with ctx.typing():
        processing_song = True
        voice_client = ctx.voice_client

        song = playlist_queue.pop(0)
        retries = 0

        while retries < max_retries:
            try:
                ydl = youtube_dl.YoutubeDL(ydl_opts)

                if 'url' in song and "youtube.com/watch?v=" in song['url']:
                    video_info = ydl.extract_info(song['url'], download=False)
                elif "youtube.com/watch?v=" in song:
                    video_info = ydl.extract_info(song, download=False)
                else:
                    video_info = ydl.extract_info(f"ytsearch:{song}", download=False)
                    if 'entries' in video_info:
                        video_info = video_info['entries'][0]
                    video_info = ydl.extract_info(video_info['url'], download=False)

                video_url = video_info['url']
                print_url = video_info['webpage_url']
                title = video_info['title']

                await ctx.send(f"Odtwarzanie muzyki:\n{title} <:notoco:906996516487581697>\n{print_url}")

                source = discord.FFmpegPCMAudio(executable=ffmpeg_path,
                                                source=video_url,
                                                options=ffmpeg_options)

                voice_client.play(source, after=lambda _: bot.loop.create_task(next_song(ctx)))
                break

            except (youtube_dl.utils.ExtractorError, youtube_dl.utils.DownloadError) as e:
                print(f"Error processing video: {e}")
                unavailable_reasons = ["Video unavailable", "Private video"]
                if any(reason in str(e) for reason in unavailable_reasons):
                    await ctx.send("Ten utwór jest niedostępny. Przechodzę do następnego utworu.")
                    bot.loop.create_task(next_song(ctx))
                    processing_song = False
                    return
                retries += 1
                await ctx.send(
                    f"Problemy z utworem, spróbuję jeszcze raz [{retries}/{max_retries}] <:notoco:906996516487581697>")
                await asyncio.sleep(3)

        if retries >= max_retries:
            if 'title' in song:
                song = song['title']
            await ctx.send(f"Nie udało się odtworzyć: {song}")
            bot.loop.create_task(next_song(ctx))

        processing_song = False


@bot.command()
async def next_song(ctx):
    if not playlist_queue:
        try:
            await ctx.send("Bot czeka na komendę. Masz 5 minut na wpisanie nowej komendy <:notoco:906996516487581697>")
            message = await bot.wait_for('message', timeout=300)
        except asyncio.TimeoutError:
            await ctx.send("Minął limit czasu. Rozłączam się.")
            voice_client = ctx.voice_client
            await voice_client.disconnect()
            return
    await play_song(ctx)


@bot.command(aliases=['mix'])
async def shuffle(ctx):
    if not playlist_queue:
        await ctx.send("Kolejka utworów jest pusta.")
        return

    random.shuffle(playlist_queue)
    await ctx.send("Kolejka utworów została przemieszana <:notoco:906996516487581697>")


@bot.command(aliases=['remove', 'rm'])
async def remove_from_queue(ctx, index):
    index = int(index) - 1
    if index >= len(playlist_queue):
        await ctx.send("Nie ma tylu utworów w kolejce <:notoco:906996516487581697>")
    element = playlist_queue.pop(index)
    if 'title' in element:
        element = element['title']
    await ctx.send(f"Usunąłem {element} z kolejki <:notoco:906996516487581697>")


@bot.command(aliases=['q'])
async def queue(ctx, queue_size=10):
    if not playlist_queue:
        await ctx.send("Kolejka utworów jest pusta.")
        return

    if queue_size > 100:
        queue_size = 100

    num_tracks = min(len(playlist_queue), queue_size)
    track_list = []

    for i in range(num_tracks):
        song = playlist_queue[i]
        if 'title' in song:
            masked_title = f"<{song['title']}>"
        else:
            masked_title = f"<{song}>"

        track_list.append(f"{i + 1}. {masked_title}")

    track_list = "\n".join(track_list)

    await ctx.send(f"Kolejka utworów ({len(playlist_queue)} utworów):\n{track_list}")


@bot.command(aliases=['next'])
async def skip(ctx):
    voice_client = ctx.voice_client

    if voice_client.is_playing():
        voice_client.stop()
        await ctx.send("Pomijam bieżący utwór. Przechodzę do następnego... <:notoco:906996516487581697>")
    else:
        await ctx.send("Aktualnie nie odtwarzam żadnego utworu.")

    if len(playlist_queue) > 0:
        await next_song(ctx)
    else:
        await ctx.send("Nie mam już nic w kolejce do odtworzenia.")


@bot.command()
async def clear(ctx):
    playlist_queue.clear()
    await ctx.send("Kolejka utworów została wyczyszczona <:notoco:906996516487581697>")


@bot.command()
async def leave(ctx):
    playlist_queue.clear()
    voice_channel = ctx.voice_client
    if voice_channel and voice_channel.is_connected():
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