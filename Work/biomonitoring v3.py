# Tento soubor definuje skupinu příkazů `/biosk` pro Discord bota.
# Zodpovídá za vyhledávání informací o druzích mravenců na portálu Biomonitoring.sk
# a generování odkazů na karty druhů a nálezové mapy SR.
# Nově také vyhledává a zobrazuje fotografii druhu z iNaturalist.
#
# Funkce:
# - Příkaz `/biosk hledat`: Umožňuje uživateli zadat rod a druh mravce.
#   Pokusí se získat ID druhu z Biomonitoring.sk pomocí web scrapingu.
#   Pokud je ID nalezeno, vytvoří přímý odkaz na kartu druhu s mapou a zobrazí
#   informace o chráněnosti a společenské hodnotě.
#   Pokud ID není nalezeno, poskytne obecný odkaz na vyhledávání na Biomonitoring.sk.
#   Současně vyhledá relevantní fotografii z iNaturalist a přidá ji do embedu.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, beautifulsoup4.
# - Standardní knihovny: urllib.parse, re.

import discord
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import asyncio # Pro asynchronní operace, pokud by byly potřeba, i když requests je synchronní

# Základní URL pro Biomonitoring.sk
BIOMONITORING_BASE_URL = "https://www.biomonitoring.sk"
BIOMONITORING_SEARCH_URL = f"{BIOMONITORING_BASE_URL}/Search/Search"
BIOMONITORING_DETAIL_URL_BASE = f"{BIOMONITORING_BASE_URL}/Registration/AtlasAnimal/Detail"
BIOMONITORING_MAP_URL_BASE = f"{BIOMONITORING_BASE_URL}/Registration/AtlasAnimal/AtlasMap"

# Základní URL pro iNaturalist API
INATURALIST_API_URL = "https://api.inaturalist.org/v1/taxa"

# Vytvoření skupiny příkazů pro Biomonitoring.sk
biosk_group = app_commands.Group(name="biosk", description="Vyhledávání informací o druzích na Biomonitoring.sk.")

async def get_inat_image_url(species_name: str) -> str | None:
    """
    Vyhledá fotografii druhu na iNaturalist API a vrátí URL prvního obrázku.
    """
    params = {
        "q": species_name,
        "rank": "species",
        "per_page": 1, # Chceme jen jeden nejlepší výsledek
        "photos": "true" # Chceme jen výsledky s fotkami
    }
    try:
        response = requests.get(INATURALIST_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if data and data.get('results'):
            for result in data['results']:
                if result.get('default_photo') and result['default_photo'].get('medium_url'):
                    # Vracíme URL střední velikosti fotky
                    print(f"Nalezena fotka z iNaturalist pro {species_name}: {result['default_photo']['medium_url']}")
                    return result['default_photo']['medium_url']
        print(f"Fotka z iNaturalist pro {species_name} nenalezena.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování dat z iNaturalist API: {e}")
        return None
    except Exception as e:
        print(f"Neočekávaná chyba při zpracování iNaturalist dat: {e}")
        return None


@biosk_group.command(name="hledat", description="Vyhledá druh mravence na Biomonitoring.sk a zobrazí detaily.")
@app_commands.describe(rod="Rod mravence (např. Camponotus)", druh="Druh mravence (např. vagus)")
async def biosk_hledat(interaction: discord.Interaction, rod: str, druh: str):
    """
    Vyhledá zadaný rod a druh mravence na Biomonitoring.sk, získá ID a zobrazí detaily.
    Současně vyhledá fotografii z iNaturalist.
    """
    await interaction.response.defer() # Odloží odpověď, protože web scraping a API volání může chvíli trvat

    full_species_name = f"{rod.capitalize()} {druh.lower()}"
    species_id = None
    species_details = {}
    inat_image_url = None
    
    # Krok 1: Vyhledání druhu a získání ID z Biomonitoring.sk
    search_query = urllib.parse.quote_plus(full_species_name)
    search_url = f"{BIOMONITORING_SEARCH_URL}?words={search_query}"

    try:
        response = requests.get(search_url)
        response.raise_for_status() # Vyvolá HTTPError pro špatné odpovědi (4xx nebo 5xx)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Hledáme odkaz na detail druhu v tabulce výsledků
        detail_link = soup.find('table', id='searchResultsTable')
        if detail_link:
            detail_link = detail_link.find('a', href=re.compile(r'/Registration/AtlasAnimal/Detail/\d+'))
        
        if detail_link:
            href = detail_link.get('href')
            # Extrahujeme ID z URL
            match = re.search(r'/Detail/(\d+)', href)
            if match:
                species_id = match.group(1)
                print(f"Nalezeno ID druhu na Biomonitoring.sk: {species_id}")
            else:
                print(f"ID druhu nenalezeno v odkazu na Biomonitoring.sk: {href}")
        else:
            print(f"Detailní odkaz pro '{full_species_name}' nenalezen na vyhledávací stránce Biomonitoring.sk.")

    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování vyhledávací stránky Biomonitoring.sk: {e}")
        await interaction.followup.send(f"Nepodařilo se připojit k Biomonitoring.sk pro vyhledávání. Zkuste to prosím později. ({e})")
        return

    # Krok 2: Pokud máme ID, získáme detaily druhu z Biomonitoring.sk
    if species_id:
        detail_url = f"{BIOMONITORING_DETAIL_URL_BASE}/{species_id}"
        try:
            response = requests.get(detail_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Získání chráněnosti
            protected_status_div = soup.find('div', class_='object')
            if protected_status_div:
                protected_status_h3 = protected_status_div.find('h3', string='Chránenosť')
                if protected_status_h3:
                    species_details['Chránenosť'] = protected_status_h3.find_next_sibling('p').get_text(strip=True)
                
                # Získání společenské hodnoty
                social_value_h3 = protected_status_div.find('h3', string='Spoločenská hodnota')
                if social_value_h3:
                    species_details['Společenská hodnota'] = social_value_h3.find_next_sibling('p').get_text(strip=True)
            
            print(f"Nalezené detaily druhu z Biomonitoring.sk: {species_details}")

        except requests.exceptions.RequestException as e:
            print(f"Chyba při stahování detailní stránky Biomonitoring.sk: {e}")
            # Pokračujeme i bez detailů, pokud se nepodařilo stáhnout detailní stránku
            species_id = None # Nastavíme ID na None, aby se zobrazil obecný odkaz

    # Krok 3: Vyhledání fotky na iNaturalist (provádíme vždy, nezávisle na Biomonitoring.sk výsledku)
    inat_image_url = await get_inat_image_url(full_species_name)

    # Krok 4: Vytvoření embedu s výsledky
    embed = discord.Embed(
        title=f"Informace o druhu {full_species_name}",
        color=discord.Color.blue()
    )

    if species_id:
        embed.description = f"Zde jsou nalezené informace pro **{full_species_name}** z Biomonitoring.sk:"
        
        # Přidání získaných detailů
        if species_details.get('Chránenosť'):
            embed.add_field(name="Chráněnost", value=species_details['Chránenosť'], inline=False)
        if species_details.get('Společenská hodnota'):
            embed.add_field(name="Společenská hodnota", value=species_details['Společenská hodnota'], inline=False)
        
        # Odkazy na Biomonitoring.sk
        detail_url_for_embed = f"{BIOMONITORING_DETAIL_URL_BASE}/{species_id}"
        map_url_for_embed = f"{BIOMONITORING_MAP_URL_BASE}/{species_id}"
        
        embed.add_field(name="Karta druhu na Biomonitoring.sk", value=f"[:page_facing_up: Odkaz]({detail_url_for_embed})", inline=False)
        embed.add_field(name="Nálezová mapa SR", value=f"[:map: Odkaz]({map_url_for_embed})", inline=False)
    else:
        embed.description = f"Bohužel se nepodařilo najít přímou kartu druhu pro **{full_species_name}** na Biomonitoring.sk. Zde je odkaz na obecné vyhledávání:"
        search_url_fallback = f"{BIOMONITORING_SEARCH_URL}?words={search_query}"
        embed.add_field(name="Odkaz na vyhledávání Biomonitoring.sk", value=f"[:mag: Vyhledat na Biomonitoring.sk]({search_url_fallback})", inline=False)

    # Přidání fotky z iNaturalist, pokud byla nalezena
    if inat_image_url:
        embed.set_thumbnail(url=inat_image_url)
        embed.set_image(url=inat_image_url) # Můžeš si vybrat, jestli chceš thumbnail nebo větší obrázek

    embed.set_footer(text="Data z Informačného systému ochrany prírody (Biomonitoring.sk) a iNaturalist.org")
    
    await interaction.followup.send(embed=embed)

# --- Instrukce pro integraci do hlavního souboru (main.py) ---
# 1. Ujisti se, že máš nainstalované knihovny `requests` a `beautifulsoup4`:
#    `pip install requests beautifulsoup4`
# 2. V souboru `main.py` přidej na začátek import:
#    `from biomonitoring_commands import biosk_group`
# 3. V `main.py` uvnitř funkce `setup_hook` (nebo tam, kde registruješ ostatní skupiny příkazů) přidej:
#    `tree.add_command(biosk_group)`
