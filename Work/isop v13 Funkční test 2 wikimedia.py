# Tento soubor definuje skupinu příkazů `/isop` pro Discord bota.
# Vyhledává informace o druzích z portálu ISOP (portal.nature.cz)
# a zároveň získává ilustrace druhu z Wikimedia Commons (přes API).
#
# Závislosti:
# - discord.py, requests, beautifulsoup4, aiohttp
# - standardní: urllib, asyncio, json, re

import discord
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import io
import aiohttp
import asyncio
import json

# Základní URL pro ISOP portál
ISOP_BASE_URL = "https://portal.nature.cz"
ISOP_SEARCH_URL = f"{ISOP_BASE_URL}/hledej"
ISOP_MAP_URL_BASE = "https://sitovemapy.nature.cz/mapy/druh-vyskyt/"
ISOP_SPECIES_CARD_URL_BASE = f"{ISOP_BASE_URL}/w/druh-"

# Wikimedia Commons API endpoint
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"


# --- Skupina příkazů pro ISOP ---
isop_group = app_commands.Group(
    name="isop",
    description="Vyhledávání informací o druzích na ISOP portálu."
)


# --- Vyhledávání druhu na ISOP ---
async def get_isop_species_info(rod: str, druh: str) -> dict | None:
    search_query = f"{rod} {druh}"
    encoded_query = urllib.parse.quote_plus(search_query)
    search_url_with_query = f"{ISOP_SEARCH_URL}?q={encoded_query}"

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(search_url_with_query, timeout=10))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        target_url = None
        canonical_link = soup.find('link', {'rel': 'canonical'})
        og_url_meta = soup.find('meta', {'property': 'og:url'})

        if canonical_link and canonical_link.get('href') and "/w/druh-" in canonical_link['href']:
            target_url = canonical_link['href']
        elif og_url_meta and og_url_meta.get('content') and "/w/druh-" in og_url_meta['content']:
            target_url = og_url_meta['content']

        if target_url:
            match = re.search(r'/druh-(\d+)', target_url)
            if match:
                return {"id": match.group(1), "species_card_url": target_url}

        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href and "/w/druh-" in href:
                link_text = link.get_text().strip()
                if search_query.lower() in link_text.lower():
                    match = re.search(r'/druh-(\d+)', href)
                    if match:
                        full_species_card_url = urllib.parse.urljoin(ISOP_BASE_URL, href)
                        return {"id": match.group(1), "species_card_url": full_species_card_url}

        return None

    except Exception as e:
        print(f"Chyba při komunikaci s ISOP portálem pro dotaz '{search_query}': {e}")
        return None


# --- Extrakce detailů z karty druhu ---
async def get_species_card_details(species_card_url: str) -> dict:
    details = {
        "Říše": "N/A", "Řád": "N/A", "Čeleď": "N/A",
        "Ochrana": "N/A", "Hodnocení": "N/A"
    }
    print(f"Pokouším se získat detaily z karty druhu: {species_card_url}")
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(species_card_url, timeout=10))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        taxonomic_data_container = soup.find('div', class_='sc-header__items')
        if taxonomic_data_container:
            for item_div in taxonomic_data_container.find_all('div', class_='sc-header__item'):
                desc_span = item_div.find('span', class_='sc-header__desc')
                value_br = item_div.find('br')
                if desc_span and value_br:
                    label_text = desc_span.get_text(strip=True).replace(':', '')
                    value_text = value_br.next_sibling.strip() if value_br.next_sibling else "N/A"
                    if label_text in details:
                        details[label_text] = value_text

        def parse_protection_evaluation_section(section_class: str, soup_obj: BeautifulSoup) -> str:
            section_value = []
            section_container = soup_obj.find('div', class_=f'list-icon {section_class}')
            if section_container:
                list_icon_list = section_container.find('ul', class_='list-icon__list')
                if list_icon_list:
                    for img_tag in list_icon_list.find_all('img', class_='list-icon__img'):
                        description_text = img_tag.get('data-original-title') or img_tag.get('title')
                        if description_text:
                            section_value.append(description_text.strip())
            return ", ".join(section_value) if section_value else "N/A"

        details["Ochrana"] = parse_protection_evaluation_section("species-card__protection", soup)
        details["Hodnocení"] = parse_protection_evaluation_section("species-card__evaluation", soup)

        print(f"Nalezené detaily: {details}")
        return details

    except Exception as e:
        print(f"Chyba při získávání detailů z karty druhu: {e}")
        return details


# --- Nový scraping z Wikimedia Commons (API) ---
async def get_wikimedia_image_url(species_name: str) -> str | None:
    """
    Vyhledá první obrázek druhu na Wikimedia Commons pomocí API.
    Pokud nenajde přímý obrázek, zkusí najít kategorii,
    a pokud ani to ne, vytáhne první <img> ze stránky výsledků.
    """
    print(f"--- Spouštím vyhledávání obrázku na Wikimedia Commons pro '{species_name}' ---")

    headers = {
        "User-Agent": "ISOPDiscordBot/1.0 (https://github.com/yourname; contact: your@email.com)"
    }
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        try:
            # 1️⃣ Primární hledání přímých obrázků
            search_api = (
                "https://commons.wikimedia.org/w/api.php"
                "?action=query"
                "&format=json"
                "&generator=search"
                f"&gsrsearch={urllib.parse.quote_plus(species_name)}"
                "&gsrnamespace=6"
                "&gsrlimit=1"
                "&prop=imageinfo"
                "&iiprop=url"
            )
            async with session.get(search_api) as response:
                response.raise_for_status()
                data = await response.json()

            pages = data.get("query", {}).get("pages", {})
            if pages:
                for _, page_data in pages.items():
                    imageinfo = page_data.get("imageinfo")
                    if imageinfo and len(imageinfo) > 0:
                        img_url = imageinfo[0].get("url")
                        if img_url:
                            print(f"ÚSPĚCH! Nalezena URL obrázku: {img_url}")
                            return img_url

            # 2️⃣ Fallback – zkusíme najít kategorii
            print("Primární hledání nic nenašlo, zkouším vyhledat kategorii…")
            cat_search = (
                "https://commons.wikimedia.org/w/api.php"
                "?action=query"
                "&list=search"
                f"&srsearch=Category:{urllib.parse.quote_plus(species_name)}"
                "&format=json"
            )
            async with session.get(cat_search) as response:
                response.raise_for_status()
                cat_data = await response.json()

            search_results = cat_data.get("query", {}).get("search", [])
            if search_results:
                category_title = search_results[0].get("title")
                print(f"Nalezena kategorie: {category_title}")

                files_api = (
                    "https://commons.wikimedia.org/w/api.php"
                    "?action=query"
                    "&format=json"
                    "&generator=categorymembers"
                    f"&gcmtitle={urllib.parse.quote_plus(category_title)}"
                    "&gcmnamespace=6"
                    "&gcmlimit=1"
                    "&prop=imageinfo"
                    "&iiprop=url"
                )
                async with session.get(files_api) as response:
                    response.raise_for_status()
                    files_data = await response.json()

                pages = files_data.get("query", {}).get("pages", {})
                for _, page_data in pages.items():
                    imageinfo = page_data.get("imageinfo")
                    if imageinfo and len(imageinfo) > 0:
                        img_url = imageinfo[0].get("url")
                        if img_url:
                            print(f"ÚSPĚCH! Obrázek z kategorie: {img_url}")
                            return img_url

            # 3️⃣ Poslední fallback – parsování HTML stránky
            print("Ani kategorie nic nenašla, zkouším parsovat HTML výsledky…")
            search_html = (
                f"https://commons.wikimedia.org/w/index.php?search={urllib.parse.quote_plus(species_name)}&title=Special:Search&profile=images"
            )
            async with session.get(search_html) as response:
                response.raise_for_status()
                html = await response.text()

            soup = BeautifulSoup(html, "html.parser")
            img_tag = soup.find("div", class_="searchResultImage-thumbnail")
            if img_tag:
                first_img = img_tag.find("img")
                if first_img and first_img.get("src"):
                    img_url = first_img["src"]
                    # převeď thumbnail na plné rozlišení (odstraníme /thumb/ část)
                    if "/thumb/" in img_url:
                        img_url = re.sub(r"/thumb/(.*?)/(?:[^/]+)$", r"/\1", img_url)
                    print(f"✅ Obrázek nalezen parsováním HTML: {img_url}")
                    return img_url

            print("⚠️ Nepodařilo se najít žádný obrázek ani v HTML.")
            return None

        except Exception as e:
            print(f"Chyba při vyhledávání na Wikimedia Commons: {e}")
            return None

    """
    Vyhledá první obrázek druhu na Wikimedia Commons pomocí MediaSearch API.
    Vrací URL obrázku ve vysokém rozlišení.
    """
    print(f"--- Spouštím vyhledávání obrázku na Wikimedia Commons pro '{species_name}' ---")

    api_url = (
        f"{WIKIMEDIA_API_URL}"
        "?action=query"
        "&format=json"
        "&generator=search"
        f"&gsrsearch={urllib.parse.quote_plus(species_name)}"
        "&gsrlimit=1"
        "&prop=imageinfo"
        "&iiprop=url"
    )

    headers = {
        "User-Agent": "ISOPDiscordBot/1.0 (https://github.com/sidlocz; contact: antsczech@seznam.cz)"
    }
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        try:
            async with session.get(api_url) as response:
                response.raise_for_status()
                data = await response.json()

            pages = data.get("query", {}).get("pages", {})
            if not pages:
                print("⚠️ API nevrátilo žádné výsledky.")
                return None

            for page_id, page_data in pages.items():
                imageinfo = page_data.get("imageinfo")
                if imageinfo and len(imageinfo) > 0:
                    img_url = imageinfo[0].get("url")
                    if img_url:
                        print(f"ÚSPĚCH! Nalezena URL obrázku: {img_url}")
                        return img_url

            print("Nebyly nalezeny žádné platné obrázky v API odpovědi.")
            return None

        except Exception as e:
            print(f"Chyba při vyhledávání na Wikimedia Commons: {e}")
            return None


# --- Slash příkaz ---
@isop_group.command(name="hledat", description="Zobrazí kartu druhu a nálezovou mapu ČR z ISOP portálu.")
@app_commands.describe(rod="Rod (např. Camponotus)", druh="Druh (např. vagus)")
async def isop_hledat(interaction: discord.Interaction, rod: str, druh: str):
    await interaction.response.defer(ephemeral=False)

    full_species_name = f"{rod.capitalize()} {druh.lower()}"
    isop_info = await get_isop_species_info(rod, druh)
    species_details = await get_species_card_details(isop_info["species_card_url"]) if isop_info else None
    wikimedia_image_url = await get_wikimedia_image_url(full_species_name)

    embed = discord.Embed(
        title=f"Karta druhu a nálezová mapa ČR pro {full_species_name}",
        description="Zde jsou odkazy na ISOP portál a nálezovou mapu:",
        color=discord.Color.green()
    )

    if wikimedia_image_url:
        embed.set_image(url=wikimedia_image_url)
    else:
        embed.set_thumbnail(url="https://placehold.co/128x128/ADD8E6/000000?text=Mapa")
        print("Nepodařilo se získat obrázek z Wikimedia Commons, používám zástupný obrázek mapy.")

    if species_details:
        embed.add_field(name="Říše", value=species_details["Říše"], inline=True)
        embed.add_field(name="Řád", value=species_details["Řád"], inline=True)
        embed.add_field(name="Čeleď", value=species_details["Čeleď"], inline=True)

        if (len(embed.fields) % 3) != 0:
            embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(name="Ochrana", value=species_details["Ochrana"], inline=False)
        embed.add_field(name="Hodnocení", value=species_details["Hodnocení"], inline=False)

    if isop_info:
        map_url_for_browser = f"{ISOP_MAP_URL_BASE}{isop_info['id']}"
        embed.add_field(name="Karta druhu na ISOP", value=f"[:page_facing_up: Odkaz]({isop_info['species_card_url']})", inline=False)
        embed.add_field(name="Nálezová mapa ČR", value=f"[:map: Odkaz]({map_url_for_browser})", inline=False)
    else:
        search_url = f"{ISOP_SEARCH_URL}?q={urllib.parse.quote_plus(full_species_name)}"
        embed.add_field(name="Odkaz na vyhledávání ISOP", value=f"[:mag: Vyhledat na ISOP portálu]({search_url})", inline=False)

    embed.set_footer(text="Data z Informačního systému ochrany přírody (ISOP) a Wikimedia Commons")
    await interaction.followup.send(embed=embed)
