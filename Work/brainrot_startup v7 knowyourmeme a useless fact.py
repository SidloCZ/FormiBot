# Tento soubor zajišťuje odeslání "Brainrot" embedu.
# Nyní obsahuje plánovač pro automatické odesílání každý den v 7:00 ráno.
# Zdroje: Merriam-Webster, Česká Wikipedie (Článek týdne/Náhodný), Know Your Meme, Useless Facts API, YouTube (Lessons in Meme Culture).
# UPDATE: Obejita 404 blokace z YouTube při běhu na hostingu pomocí proxy služby rss2json.
# UPDATE: Odstraněn Urban Dictionary, přidán náhodný meme (KYM) a dnešní zbytečný fakt.

import discord
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import random
import traceback
import re
import warnings
from discord.ext import tasks
import datetime

# Nastavení časového pásma pro Českou republiku (zohledňuje zimní/letní čas)
try:
    from zoneinfo import ZoneInfo
    CZ_TZ = ZoneInfo("Europe/Prague")
except ImportError:
    CZ_TZ = datetime.timezone(datetime.timedelta(hours=1))

# Nastavení času na 7:00 ráno
RUN_TIME = datetime.time(hour=7, minute=0, tzinfo=CZ_TZ)

# Skrytí neškodného varování při parsování XML pomocí HTML parseru
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Hlavičky pro requesty, aby nás weby neblokovaly jako robota
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_soup(url, allow_redirects=False):
    """Pomocná funkce pro získání BeautifulSoup objektu s ošetřením chyb."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=allow_redirects)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser'), response
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
        
        # Zkrácení definice, pokud je příliš dlouhá
        if len(definition) > 300:
            definition = definition[:297] + "..."
            
        return word, definition
    except Exception as e:
        print(f"Chyba u Merriam-Webster: {e}")
        return "Neznámé slovo", "Chyba při parsování."

def get_czech_wikipedia():
    """Získá Článek týdne z české Wikipedie. Pokud selže, vrátí odkaz na náhodný článek."""
    fallback_title = "Dozvi se něco nového"
    fallback_desc = "[Náhodný článek z Wikipedie](https://cs.wikipedia.org/wiki/Special:Random)"
    url = "https://cs.wikipedia.org/wiki/Hlavn%C3%AD_strana"
    soup, _ = get_soup(url)
    
    if not soup:
        return fallback_title, fallback_desc
        
    try:
        # Článek týdne je většinou pod elementem s id="Článek_týdne"
        header = soup.find(id=re.compile(r"Článek_týdne", re.IGNORECASE))
        if header:
            # Najdeme nadřazený element h2 nebo h3 (Wikipedia často používá <span id="..."> uvnitř <h2>)
            heading = header if header.name in ['h2', 'h3'] else header.find_parent(['h2', 'h3'])
            
            if heading:
                # Obsah bývá hned v dalším divu
                content_container = heading.find_next_sibling('div')
                
                # Fallback pro starší rozložení (kdyby to byla tabulka)
                if not content_container:
                    content_container = heading.find_parent('td') or heading.find_parent('div')

                if content_container:
                    # Získáme první odstavce v kontejneru
                    paragraphs = content_container.find_all('p')
                    text_content = ""
                    for p in paragraphs:
                        text = p.get_text().strip()
                        if text:
                            text_content += text + " "
                            if len(text_content) > 100: # Stačí nám úvod
                                break

                    if text_content:
                        # Očištění textu od referencí typu [1], [2]
                        text_content = re.sub(r'\[\d+\]', '', text_content)

                        # Získání titulku z tučného textu
                        title_elem = content_container.find('b')
                        title = title_elem.get_text() if title_elem else "Článek týdne"

                        # Zkrácení na max 150 znaků pro čistý embed
                        short_text = (text_content[:147] + "...") if len(text_content) > 150 else text_content
                        return title.strip(), short_text.strip()
    except Exception as e:
        print(f"Chyba při parsování Wikipedie: {e}")

    # Pokud cokoliv z parsování selže, bezpečně vrátíme tvůj fallback
    return fallback_title, fallback_desc

def get_know_your_meme():
    """Získá náhodný meme z Know Your Meme."""
    url = "https://knowyourmeme.com/random"
    try:
        soup, response = get_soup(url, allow_redirects=True)
        if not soup or not response:
            return "Chyba načítání", "https://knowyourmeme.com", "Nepodařilo se připojit k serveru KYM."
        
        # Získání názvu z meta tagu
        title_meta = soup.find("meta", property="og:title")
        title = title_meta["content"] if title_meta else "Náhodný Meme"
        title = title.replace(" | Know Your Meme", "").replace(" - Know Your Meme", "")

        # Získání URL (po přesměrování z /random)
        meme_url = response.url

        # Získání popisu
        desc_meta = soup.find("meta", property="og:description")
        description = desc_meta["content"] if desc_meta else "Popis není k dispozici."

        # Oříznutí popisu pro embed
        if len(description) > 200:
            description = description[:197] + "..."

        return title.strip(), meme_url, description.strip()

    except Exception as e:
        print(f"Chyba u Know Your Meme: {e}")
        return "Chyba zpracování", "https://knowyourmeme.com", "Nepodařilo se načíst náhodný meme."

def get_useless_fact():
    """Získá dnešní zbytečný fakt z Useless Facts API."""
    url = "https://uselessfacts.jsph.pl/api/v2/facts/today"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "text" in data:
            return data["text"]
        return "Dnes se nic zbytečného nedozvíš."
    except Exception as e:
        print(f"Chyba u Useless Facts API: {e}")
        return "Nepodařilo se načíst dnešní fakt."

def get_limc_video():
    """Získá nejnovější video z Lessons in Meme Culture.
    Používá proxy api.rss2json.com k obejití blokování datacentra (Wispbyte) ze strany YouTube."""
    # Enkódovaná RSS URL pro Lessons in Meme Culture
    proxy_url = "https://api.rss2json.com/v1/api.json?rss_url=https%3A%2F%2Fwww.youtube.com%2Ffeeds%2Fvideos.xml%3Fchannel_id%3DUCaHT88aobpcvRFEuy4v5Clg"
    
    try:
        response = requests.get(proxy_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Ověříme, že proxy server vrátil validní data ze struktury JSONu
        if data.get('status') == 'ok' and len(data.get('items', [])) > 0:
            latest = data['items'][0]
            title = latest.get('title', 'Nové video od LIMC')
            link = latest.get('link', 'https://youtube.com/@LIMC')
            thumbnail = latest.get('thumbnail', '')
            
            # Pojistka pro thumbnail, kdyby v API náhodou chyběl
            if not thumbnail and "v=" in link:
                video_id = link.split("v=")[1][:11]
                thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                
            return title, link, thumbnail
    except Exception as e:
        print(f"Chyba při parsování YouTube pomocí rss2json proxy: {e}")

    # Fallback, pokud selže i proxy
    return "Nepodařilo se načíst video", "https://youtube.com/@LIMC", ""

async def send_daily_brainrot(client, channel_id):
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            print(f"Nenalezen kanál s ID {channel_id} pro Brainrot.")
            return

        print("Generuji Brainrot embed...")
        
        # Získávání obsahu
        mw_word, mw_def = get_merriam_webster()
        wiki_title, wiki_desc = get_czech_wikipedia()
        kym_title, kym_url, kym_desc = get_know_your_meme()
        useless_fact = get_useless_fact()
        limc_title, limc_url, limc_thumb = get_limc_video()

        # Vytvoření Embedu
        embed = discord.Embed(
            title="🧠 Ranní Brainrot",
            description="Vše, co nepotřebuješ vědět.",
            color=discord.Color.from_rgb(255, 105, 180) # Hot Pink
        )

        embed.add_field(
            name=f"🇬🇧 Word of the Day (Merriam-Webster)",
            value=f"**{mw_word}**\n*{mw_def}*",
            inline=False
        )
        
        # Dynamicky měníme název pole podle toho, zda je to fallback nebo ne
        wiki_field_name = "🇨🇿 Česká Wikipedie: Článek týdne" if wiki_title != "Dozvi se něco nového" else "🇨🇿 Česká Wikipedie"
        embed.add_field(
            name=wiki_field_name,
            value=f"**{wiki_title}**\n{wiki_desc}",
            inline=False
        )

        embed.add_field(
            name=f"🎭 Know Your Meme (Náhodný)",
            value=f"**[{kym_title}]({kym_url})**\n*{kym_desc}*",
            inline=False
        )

        embed.add_field(
            name=f"💡 Zbytečný fakt dne",
            value=f"{useless_fact}",
            inline=False
        )
        
        embed.add_field(
            name=f"▶️ Lessons in Meme Culture",
            value=f"**[{limc_title}]({limc_url})**",
            inline=False
        )

        if limc_thumb:
            embed.set_image(url=limc_thumb)

        await channel.send(embed=embed)
        print("Brainrot embed úspěšně odeslán.")

    except Exception as e:
        print(f"Došlo k chybě při odesílání Brainrotu: {e}")
        traceback.print_exc()

@tasks.loop(time=RUN_TIME)
async def brainrot_task_loop(client, channel_id):
    """Smyčka, která se spustí každý den přesně v 7:00."""
    print("⏰ Je 7:00, odesílám ranní Brainrot!")
    await send_daily_brainrot(client, channel_id)

def start_brainrot_timer(client, channel_id):
    """Spustí plánovač pro každodenní zprávy, pokud ještě neběží."""
    if not brainrot_task_loop.is_running():
        brainrot_task_loop.start(client, channel_id)
        print("✅ Brainrot plánovač byl spuštěn a je nastaven na 7:00 ráno.")