import discord
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import random
import traceback
import re
import warnings
from discord.ext import tasks
import datetime

# Nastavení časového pásma pro Českou republiku
try:
    from zoneinfo import ZoneInfo
    CZ_TZ = ZoneInfo("Europe/Prague")
except Exception:
    CZ_TZ = datetime.timezone(datetime.timedelta(hours=1))

RUN_TIME = datetime.time(hour=7, minute=0, tzinfo=CZ_TZ)

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_soup(url, allow_redirects=False):
    """Pomocná funkce pro získání BeautifulSoup objektu s ošetřením chyb."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=allow_redirects)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser"), response
    except Exception as e:
        print(f"Chyba při stahování {url}: {e}")
        return None, None

def get_merriam_webster():
    """Získá Word of the Day z Merriam-Webster."""
    url = "https://www.merriam-webster.com/word-of-the-day"
    soup, _ = get_soup(url)
    if not soup:
        return "Neznámé slovo", "Chyba načítání."
    try:
        word_elem = soup.find("h2", class_="word-header-txt")
        word = word_elem.text.strip() if word_elem else "Neznámé slovo"

        def_elem = soup.find("div", class_="wod-definition-container")
        if def_elem:
            p_elem = def_elem.find("p")
            definition = p_elem.text.strip() if p_elem else "Definice nenalezena."
        else:
            definition = "Definice nenalezena."

        return word, definition
    except Exception as e:
        print(f"Chyba při parsování MW: {e}")
        return "Neznámé slovo", "Chyba načítání."

def get_czech_wikipedia():
    """Získá Článek týdne z české Wikipedie, případně náhodný článek jako fallback."""
    main_page_url = "https://cs.wikipedia.org/wiki/Hlavn%C3%AD_strana"
    soup, _ = get_soup(main_page_url)
    
    if soup:
        try:
            article_box = soup.find("div", id="mainpage-featured-article")
            if article_box:
                header_elem = article_box.find(["h2", "h3"])
                link = header_elem.find("a") if header_elem else None
                if not link:
                    link = article_box.find("b").find("a") if article_box.find("b") else article_box.find("a")

                if link and link.get("title"):
                    title = link.get("title")
                    paragraphs = article_box.find_all("p")
                    desc = ""
                    for p in paragraphs:
                        text = p.text.strip()
                        if len(text) > 50:
                            desc = text
                            break
                    if not desc and paragraphs:
                        desc = paragraphs[0].text.strip()

                    desc = re.sub(r"\[\d+\]", "", desc)
                    if len(desc) > 300:
                        desc = desc[:297] + "..."

                    full_url = f"https://cs.wikipedia.org{link.get('href')}"
                    return f"[{title}]({full_url})", desc, True
        except Exception as e:
            print(f"Chyba při parsování Článku týdne: {e}")

    random_url = "https://cs.wikipedia.org/wiki/Speci%C3%A1ln%C3%AD:N%C3%A1hodn%C3%A1_str%C3%A1nka"
    soup, response = get_soup(random_url, allow_redirects=True)
    if soup and response:
        try:
            title_elem = soup.find("h1", id="firstHeading")
            title = title_elem.text.strip() if title_elem else "Článek"
            p_elem = soup.find("div", class_="mw-parser-output").find("p")
            desc = p_elem.text.strip() if p_elem else "Popis není k dispozici."
            desc = re.sub(r"\[\d+\]", "", desc)
            if len(desc) > 300:
                desc = desc[:297] + "..."
            return f"[{title}]({response.url})", desc, False
        except Exception:
            pass

    return "[Wikipedie](https://cs.wikipedia.org)", "Informace se nepodařilo načíst.", False

def get_random_kym():
    """Získá náhodný meme z Know Your Meme."""
    url = "https://knowyourmeme.com/random"
    soup, response = get_soup(url, allow_redirects=True)
    if not soup or not response:
        return "Neznámý Meme", "https://knowyourmeme.com", "Chyba načítání."
    try:
        title_elem = soup.find("h1")
        title = title_elem.text.strip() if title_elem else "Náhodný Meme"
        body = soup.find("section", class_="bodycopy")
        desc = "Popis není k dispozici."
        if body:
            p = body.find("p")
            if p:
                desc = p.text.strip()
                if len(desc) > 250:
                    desc = desc[:247] + "..."
        return title, response.url, desc
    except Exception as e:
        print(f"Chyba při parsování KYM: {e}")
        return "Neznámý Meme", "https://knowyourmeme.com", "Chyba načítání."

def get_useless_fact():
    """Získá náhodný fakt z Useless Facts API."""
    url = "https://uselessfacts.jsph.pl/api/v2/facts/today?language=en"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data.get("text", "Fakt se nepodařilo načíst.")
    except Exception as e:
        print(f"Chyba při získávání Useless Fact: {e}")
    return "Dnes žádný fakt není k dispozici."

def get_latest_limc_rss():
    """Získá nejnovější video z YouTube kanálu Lessons in Meme Culture pomocí proxy rss2json."""
    proxy_url = "https://api.rss2json.com/v1/api.json?rss_url=https://www.youtube.com/feeds/videos.xml?channel_id=UCIsbLox_y9dCIMLd8mbC6jg"
    try:
        res = requests.get(proxy_url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "ok" and data.get("items"):
                first_video = data["items"][0]
                title = first_video.get("title", "Nové video")
                link = first_video.get("link", "https://www.youtube.com/@LessonsInMemeCulture")
                thumbnail = first_video.get("thumbnail")
                return title, link, thumbnail
    except Exception as e:
        print(f"Chyba při parsování Lessons in Meme Culture přes proxy: {e}")
    return "Nové video", "https://www.youtube.com/@LessonsInMemeCulture", None

async def send_daily_brainrot(client, channel_id):
    """Hlavní funkce, která posbírá data a odešle embed do daného kanálu."""
    channel = client.get_channel(channel_id)
    if not channel:
        print(f"Kanál s ID {channel_id} nebyl nalezen pro odeslání Brainrotu.")
        return

    try:
        mw_word, mw_def = get_merriam_webster()
        wiki_title, wiki_desc, is_cotd = get_czech_wikipedia()
        kym_title, kym_url, kym_desc = get_random_kym()
        useless_fact = get_useless_fact()
        limc_title, limc_url, limc_thumb = get_latest_limc_rss()

        embed = discord.Embed(
            title="Ranní dávka informací a zajímavostí",
            description="Shrnutí vybraných zajímavostí pro dnešní den:",
            color=discord.Color.from_rgb(255, 105, 180),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        embed.add_field(
            name=f"Merriam-Webster: {mw_word}",
            value=mw_def,
            inline=False
        )

        wiki_field_name = "Česká Wikipedie: Článek týdne" if is_cotd else "Česká Wikipedie: Náhodný článek"
        embed.add_field(
            name=wiki_field_name,
            value=f"**{wiki_title}**\n{wiki_desc}",
            inline=False
        )

        embed.add_field(
            name="Know Your Meme (Náhodný)",
            value=f"**[{kym_title}]({kym_url})**\n*{kym_desc}*",
            inline=False
        )

        embed.add_field(
            name="Zbytečný fakt dne",
            value=f"{useless_fact}",
            inline=False
        )
        
        embed.add_field(
            name="Lessons in Meme Culture",
            value=f"**[{limc_title}]({limc_url})**",
            inline=False
        )

        if limc_thumb:
            embed.set_image(url=limc_thumb)

        await channel.send(embed=embed)
        print("Ranní přehled úspěšně odeslán.")

    except Exception as e:
        print(f"Došlo k chybě při odesílání ranního přehledu: {e}")
        traceback.print_exc()

@tasks.loop(time=RUN_TIME)
async def brainrot_task_loop(client, channel_id):
    """Smyčka, která se spustí každý den přesně v 7:00."""
    print("Je 7:00, odesílám ranní přehled.")
    await send_daily_brainrot(client, channel_id)

def start_brainrot_timer(client, channel_id):
    """Spustí plánovač pro každodenní zprávy, pokud ještě neběží."""
    if not brainrot_task_loop.is_running():
        brainrot_task_loop.start(client, channel_id)
        print("Plánovač ranních přehledů byl spuštěn a je nastaven na 7:00 ráno.")
