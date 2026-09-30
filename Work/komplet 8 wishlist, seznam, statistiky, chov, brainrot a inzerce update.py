# Tento soubor je hlavním spouštěcím bodem pro Discord bota "FormiBot".
#
# Funkce:
# - Inicializuje klienta Discordu a strom příkazů.
# - Načítá a spravuje konfiguraci (token).
# - Načítá a ukládá data z JSON souborů (skóre, historická data, kvízové otázky).
# - Definuje a registruje hlavní slash příkazy (/ping, /restart, atd.).
# - Spravuje hlavní události bota, jako je on_ready.
# - Zaregistrováno trvalé tlačítko (AdInteractionView) pro inzerci.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, matplotlib, tabulate.
# - Lokální moduly (mohou být umístěny v Příkazy.), nejedná se o celý výčet:
#   - `quiz_commands.py`: Pro příkazy a logiku kvízu.
#   - `wishlist_commands.py`: Pro příkazy týkající se wishlistů.
#   - `formikaristika_commands.py`: Pro příkazy k procházení webu Formikaristika.cz.
#   - `info_commands.py`: Pro příkazy k vyhledávání na externích fórech. (vypnuto)
#   - `statistiky.py`: Pro příkazy statistik.
#   - `seznam_commands.py`: Pro příkazy a správu seznamu mravenců.
#   - `utils.py`: Pro sdílené utility, jako je PaginatorView.
#   - `quiz_questions.json`: Datový soubor s otázkami pro kvíz.
#   - `wishlists.json`: Datový soubor s wishlisty lidí.
#   - `isop_commands.py`: Pro příkazy s ISOP kartami druhů.
#   - `chov_commands.py`: Pro příkaz chov který najde info o každém druhu.

# snad je tato verze ok, byla celá vygenerována gemini

import discord
from discord import app_commands
import os
import json
import time
import asyncio
import random
import datetime
import requests
from tabulate import tabulate
import re
import matplotlib.pyplot as plt
import io
import sys # Import pro ukončení programu



# --- Import příkazových modulů ---
from Příkazy.wishlist_commands import wishlist_group, load_wishlists, save_wishlists
# UPRAVENO: Importujeme třídu místo instance
from Příkazy.formikaristika_commands import FormikaristikaCommands 
# from info_commands import info_group
from statistiky import statistiky_group
from quiz_commands import QuizCommands 
from utils import PaginatorView
from Příkazy.isop_commands import isop_group 
#from biomonitoring_commands import biosk_group
from slovnik_commands import slovnik_group, load_dictionary_data
from patch_notes_commands import patch_notes_group, load_patch_notes
from fauna_commands import fauna_group
from Příkazy.map_command import map_command
from Příkazy.seznam_commands import seznam_group, load_user_ants, user_ants, save_user_ants, load_species_database
from Příkazy.udalosti_commands import udalosti_group, setup_udalosti
from Příkazy.inzerce_commands import inzerce_group, setup_inzerce, process_chat_message, AdInteractionView
from Příkazy.chov_commands import chov_command, load_chov_data
from Příkazy import brainrot_startup


# --- Konfigurace ---
try:
    with open('token.txt', 'r') as f:
        TOKEN = f.read().strip()
except FileNotFoundError:
    print("CHYBA: Soubor 'token.txt' nenalezen. Vytvořte prosím soubor a vložte do něj token Vašeho bota.")
    TOKEN = None

if not TOKEN:
    exit("Token bota nebyl nalezen. Ukončuji program.")

# --- Načtení otázek pro kvíz z JSON souboru ---
def load_quiz_questions():
    """Načte otázky pro kvíz z JSON souboru."""
    try:
        with open('quiz_questions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("CHYBA: Soubor 'quiz_questions.json' nenalezen nebo je poškozený.")
        print("Vytvářím prázdný slovník otázek, kvíz nebude fungovat správně.")
        return {}

quiz_questions = load_quiz_questions()

# --- Nastavení bota ---
intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- Správa skóre ---
scores = {
    "total_scores": {},
    "weekly_scores": {}
}

def save_scores():
    """Uloží aktuální stav skóre do souboru scores.json."""
    try:
        with open('scores.json', 'w', encoding='utf-8') as f:
            json.dump(scores, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání skóre: {e}")

def load_scores():
    """Načte skóre ze souboru scores.json při startu bota."""
    global scores
    try:
        with open('scores.json', 'r', encoding='utf-8') as f:
            loaded_scores = json.load(f)
            
            # Migrace staré struktury na novou, pokud je potřeba
            new_total_scores = {}
            new_weekly_scores = {}

            if "total_scores" not in loaded_scores and "weekly_scores" not in loaded_scores:
                for user_id, score in loaded_scores.items():
                    if isinstance(score, int):
                        new_total_scores[user_id] = {"overall": score, "hints": 0}
                    elif isinstance(score, dict) and user_id.isdigit():
                        new_weekly_scores[user_id] = {}
                        for uid, s in score.items():
                            new_weekly_scores[user_id][uid] = {"overall": s}
            else:
                new_total_scores = loaded_scores.get("total_scores", {})
                new_weekly_scores = loaded_scores.get("weekly_scores", {})
                
                for user_id in new_total_scores:
                    if not isinstance(new_total_scores[user_id], dict):
                        new_total_scores[user_id] = {"overall": new_total_scores[user_id]}
                    if "hints" not in new_total_scores[user_id]:
                        new_total_scores[user_id]["hints"] = 0
                
                for week_num in new_weekly_scores:
                    for user_id in new_weekly_scores[week_num]:
                        if not isinstance(new_weekly_scores[week_num][user_id], dict):
                            new_weekly_scores[week_num][user_id] = {"overall": new_weekly_scores[week_num][user_id]}

            scores["total_scores"] = new_total_scores
            scores["weekly_scores"] = new_weekly_scores
            
            save_scores()
    except (FileNotFoundError, json.JSONDecodeError):
        print("Soubor scores.json nenalezen nebo je poškozený. Vytvářím novou databázi skóre.")
        scores = {"total_scores": {}, "weekly_scores": {}}

# --- Správa historických dat ---
# Poznámka: user_ants je nyní importováno ze seznam_commands.py
historical_ants_data = {}

def save_historical_ants_data():
    """Uloží aktuální historická data do souboru historical_ants_data.json."""
    try:
        with open('historical_ants_data.json', 'w', encoding='utf-8') as f:
            json.dump(historical_ants_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání historických dat mravenců: {e}")

def load_historical_ants_data():
    """Načte historická data mravenců ze souboru historical_ants_data.json při startu bota."""
    global historical_ants_data
    try:
        with open('historical_ants_data.json', 'r', encoding='utf-8') as f:
            historical_ants_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Soubor historical_ants_data.json nenalezen nebo je poškozený. Vytvářím novou databázi historických dat.")
        historical_ants_data = {}

# Asynchronní úloha pro pravidelné ukládání historických dat
async def periodic_save_historical_data():
    await client.wait_until_ready()
    while not client.is_closed():
        current_date = datetime.date.today().isoformat()
        
        last_saved_date = max(historical_ants_data.keys()) if historical_ants_data else None

        should_save = True
        if last_saved_date:
            last_date_obj = datetime.date.fromisoformat(last_saved_date)
            if (datetime.date.today() - last_date_obj).days < 60:
                should_save = False

        if should_save:
            print(f"Ukládám historická data pro datum: {current_date}")
            # Používáme user_ants importované ze seznam_commands
            historical_ants_data[current_date] = user_ants.copy()
            save_historical_ants_data()
        
        await asyncio.sleep(60 * 60 * 24 * 60) # 60 dní

# --- Pomocné funkce ---
def check_if_moderator(interaction: discord.Interaction) -> bool:
    """Zkontroluje, zda má uživatel roli moderátora nebo administrátora."""
    mod_roles = ["Trubec - mod", "Královna - ultra mod", "Antkeeper - ADMIN"]
    return any(role.name in mod_roles for role in interaction.user.roles)

# Funkce pro kontrolu role podle ID
def has_role_by_id(member: discord.Member, role_id: int) -> bool:
    """Zkontroluje, zda má člen serveru danou roli podle ID."""
    return any(role.id == role_id for role in member.roles)

# --- Události (Events) ---
@client.event
async def on_ready():
    """
    Funkce se zavolá, když je bot připraven a připojen k Discordu.
    """
    global formikaristika_group # Definujeme jako globální, abychom k ní měli přístup (pro jistotu)

    # Načtení dat pro ostatní moduly
    load_scores()
    load_user_ants() 
    load_wishlists()
    load_historical_ants_data()
    load_chov_data()
    await load_dictionary_data() 
    load_patch_notes() 
    
    # Předání dat do client objektu pro přístup z jiných modulů
    client.user_ants = user_ants 
    client.historical_ants_data = historical_ants_data

    # --- INICIALIZACE SKUPIN PŘÍKAZŮ ---
    
    # 1. Formikaristika (Instanciace a načtení dat pro autocomplete)
    # Vytvoříme instanci třídy FormikaristikaCommands
    print("Inicializuji FormikaristikaCommands...")
    formikaristika_group = FormikaristikaCommands(client)
    # Zavoláme on_ready metodu třídy pro načtení sitemapy
    await formikaristika_group.on_ready() 
    
    # Registrace příkazů do stromu (Tree)
    tree.add_command(wishlist_group)
    tree.add_command(formikaristika_group) 
    # tree.add_command(info_group)
    tree.add_command(statistiky_group)
    tree.add_command(isop_group)
    # tree.add_command(biosk_group)
    tree.add_command(slovnik_group)
    tree.add_command(patch_notes_group) 
    tree.add_command(fauna_group) 
    tree.add_command(map_command)
    tree.add_command(seznam_group) 
    tree.add_command(udalosti_group)
    tree.add_command(inzerce_group)
    tree.add_command(chov_command)

    # Spuštění kontroly expirace
    setup_inzerce(client) 
    client.add_view(AdInteractionView()) # Přidáno pro fungování tlačítek u inzerátů po restartu
    
    # Inicializace kvízových příkazů
    client.quiz_commands = QuizCommands(client, tree, scores, save_scores, quiz_questions)

    # Synchronizace příkazů se serverem
    await tree.sync()

    # Spuštění periodické úlohy
    client.loop.create_task(periodic_save_historical_data())

    print(f'Přihlášen jako {client.user} (ID: {client.user.id})')
    print('Bot je připraven a příkazy jsou synchronizovány.')
    print('------')

    brainrot_messages = [
        "FormiBot připojen! 🐜"
    ]
    
    target_channel_id = 662424508266840080
    target_channel = client.get_channel(target_channel_id)

    if target_channel:
        await target_channel.send(random.choice(brainrot_messages))
    else:
        print(f"CHYBA: Kanál s ID {target_channel_id} nebyl nalezen.")
    
    BRAINROT_CHANNEL_ID = 662424508266840080 
    brainrot_startup.start_brainrot_timer(client, BRAINROT_CHANNEL_ID)


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """
    Globální listener pro reakce, který deleguje zpracování na QuizCommands.
    """
    if hasattr(client, 'quiz_commands'):
        await client.quiz_commands.on_raw_reaction_add(payload)

# NOVÉ: Listener pro sledování zpráv v inzertním kanálu
@client.event
async def on_message(message: discord.Message):
    # Důležité: Nechat bota zpracovat i ostatní příkazy
    # Ale protože používáme slash commands (tree), process_commands není nutné,
    # pokud nepoužíváme prefixové příkazy. Pokud bys používal prefixové, odkomentuj:
    # await client.process_commands(message)

    # Předáme zprávu funkci pro zpracování inzerce v chatu
    await process_chat_message(message)
    
    
# --- Příkaz /restart ---
RESTART_ROLE_ID = 661971700556234753 # ID role, která může použít příkaz /restart

@tree.command(name="restart", description="Restartuje bota (pouze pro oprávněné role).")
async def restart_command(interaction: discord.Interaction):
    # Kontrola, zda má uživatel požadovanou roli
    if not has_role_by_id(interaction.user, RESTART_ROLE_ID):
        await interaction.response.send_message("Nemáš oprávnění k použití tohoto příkazu.", ephemeral=True)
        return

    # Oznámení v kanále
    await interaction.channel.send("Bot se aktuálně ukládá a nebude chvilku fungovat. Prosím, vyčkejte.")

    # Uložení všech dat před restartem
    save_scores()
    save_user_ants() # Uloží data ze seznam_commands
    save_wishlists()
    save_historical_ants_data()
    if hasattr(client, 'quiz_commands'):
        client.quiz_commands.save_suggestions()
        client.quiz_commands.save_quiz_questions()
    
    print("Všechna data uložena. Vypínám bota pro restart.")
    await interaction.channel.send("Všechna data uložena. Vypínám bota pro restart.")
  
    # Ukončení klienta Discordu
    await client.close()
    # Ukončení Python procesu
    sys.exit(0) # Použijeme sys.exit(0) pro čisté ukončení

# --- Zbytek souboru main.py ---

@tree.command(name="ping", description="Zobrazí latenci bota.")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    if latency <= 50: color = 0x44ff44
    elif latency <= 100: color = 0xffd000
    elif latency <= 200: color = 0xff6600
    else: color = 0x990000

    embed = discord.Embed(title="PONG!", description=f":ping_pong: Aktuální ping je **{latency}** ms!", color=color)
    await interaction.response.send_message(embed=embed)

# Původní příkazy pro seznam byly přesunuty do seznam_commands.py

@tree.command(name="help", description="Zobrazí seznam všech dostupných příkazů.")
async def help_command(interaction: discord.Interaction):
    command_info_list = []
    for command in tree.walk_commands():
        cmd_name = f"/{command.parent.name} {command.name}" if command.parent else f"/{command.name}"
        cmd_description = command.description or "Bez popisu."
        command_info_list.append((cmd_name, cmd_description))

    command_info_list.sort(key=lambda x: x[0].lower())

    pages = []
    current_page_fields = []
    MAX_COMMANDS_PER_PAGE = 8 

    for i, (cmd_name, cmd_desc) in enumerate(command_info_list):
        current_page_fields.append((cmd_name, cmd_desc))
        if len(current_page_fields) == MAX_COMMANDS_PER_PAGE or i == len(command_info_list) - 1:
            embed = discord.Embed(title="Dostupné příkazy bota", description="Seznam všech příkazů:", color=discord.Color.gold())
            for name, value in current_page_fields:
                embed.add_field(name=name, value=value, inline=False)
            pages.append(embed)
            current_page_fields = []

    view = PaginatorView(pages, interaction)
    await interaction.response.send_message(embed=pages[0], view=view)
    view.message = await interaction.original_response()

if __name__ == "__main__":
    if TOKEN:
        client.run(TOKEN)
        
# Tento soubor definuje skupinu příkazů `/biosk` pro Discord bota, nicméně tento příkaz není v botu aktuálně zavedený, web špatně odpovídá.
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

# Tento soubor definuje skupinu příkazů `/formikaristika` pro Discord bota.
# Umožňuje uživatelům interaktivně procházet obsah webu Formikaristika CZ
# a nově i Návod na chov s pokročilým stránkováním a detekcí obrázků.

import discord
from discord import app_commands, ui
import requests
import xml.etree.ElementTree as ET
import re
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
import math

# URL sitemap souboru webu a Návodu na chov
SITEMAP_URL = "https://formikaristika.wordpress.com/sitemap.xml"
CARE_GUIDE_URL = "https://formikaristika.wordpress.com/mravenci/chov/navod/"
DEFAULT_IMAGE_URL = "https://formikaristika.wordpress.com/wp-content/uploads/2016/06/cropped-logo-1.png"

# --- Pomocné funkce pro parsování ---

def clean_html_text(soup_element):
    """
    Převede HTML element na text vhodný pro Discord.
    Zachová odkazy ve formátu [text](url) a obrázky.
    """
    text_parts = []
    
    # Procházíme obsah elementu
    for content in soup_element.contents:
        if content.name == 'a' and content.get('href'):
            # Odkazy
            link_text = content.get_text(strip=True)
            if link_text:
                text_parts.append(f"[{link_text}]({content['href']})")
        elif content.name == 'img':
            # Obrázky - vložíme jako odkaz na obrázek s ikonou (pro textovou verzi)
            img_src = content.get('src')
            if img_src:
                text_parts.append(f"\n🖼️ [Obrázek]({img_src})\n")
        elif content.name in ['strong', 'b']:
            text_parts.append(f"**{content.get_text(strip=True)}**")
        elif content.name in ['em', 'i']:
            text_parts.append(f"*{content.get_text(strip=True)}*")
        elif content.name == 'br':
            text_parts.append("\n")
        elif isinstance(content, str):
            text_parts.append(content)
        else:
            # Rekurzivně pro ostatní tagy, pokud nejsou nahoře
            text_parts.append(content.get_text(strip=True) if hasattr(content, 'get_text') else str(content))

    return "".join(text_parts).strip()

def extract_images_from_element(soup_element):
    """
    Vrátí seznam URL všech obrázků v daném elementu.
    Upřednostňuje odkazy (<a>) na obrázky, protože bývají ve vyšší kvalitě.
    """
    images = []
    
    # 1. Hledání odkazů na obrázky (často full-size verze ve WordPressu)
    if hasattr(soup_element, 'find_all'):
        for a in soup_element.find_all('a'):
            href = a.get('href')
            if href and href.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                images.append(href)
    
    # 2. Hledání img tagů (pokud jsme nenašli odkazy, nebo jako doplněk)
    if hasattr(soup_element, 'find_all'):
        for img in soup_element.find_all('img'):
            src = img.get('src')
            if src:
                # Jednoduchá de-duplikace
                if src not in images:
                    images.append(src)
    
    # 3. Přímý element je img
    if soup_element.name == 'img' and soup_element.get('src'):
         if soup_element.get('src') not in images:
            images.append(soup_element.get('src'))

    return images

# --- Třídy pro UI (Views) ---

class ParagraphSelectorView(discord.ui.View):
    """View pro výběr konkrétních odstavců k odeslání do chatu."""
    def __init__(self, paragraphs, title):
        super().__init__(timeout=180)
        self.paragraphs = paragraphs
        self.title = title

        # Discord limituje options na 25. Pokud je odstavců víc, ořízneme to.
        options = []
        for i, para in enumerate(self.paragraphs[:25]):
            label = (para[:90] + '...') if len(para) > 90 else para
            if not label: label = "Obrázek nebo formátování..."
            
            options.append(discord.SelectOption(
                label=f"{i+1}. {label}",
                value=str(i),
                description="Klikni pro výběr"
            ))

        if options:
            self.select = discord.ui.Select(
                placeholder="Vyber odstavce k odeslání (Multi-select)",
                min_values=1,
                max_values=len(options),
                options=options
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        final_text = f"**{self.title}**\n\n"
        selected_values = [int(v) for v in self.select.values]
        selected_values.sort()
        
        for idx in selected_values:
            final_text += self.paragraphs[idx] + "\n\n"

        if len(final_text) > 2000:
            parts = [final_text[i:i+2000] for i in range(0, len(final_text), 2000)]
            for part in parts:
                await interaction.channel.send(part)
        else:
            await interaction.channel.send(final_text)
            
        await interaction.followup.send("✅ Text byl odeslán do kanálu.", ephemeral=True)


class CareGuideView(discord.ui.View):
    """
    View pro procházení strukturovaného návodu na chov se stránkováním.
    Zahrnuje dropdown pro kapitoly, navigaci stránek a tlačítka akcí.
    """
    def __init__(self, guide_data, main_browser_view_class, cog_instance):
        super().__init__(timeout=300)
        self.guide_data = guide_data
        self.main_browser_view_class = main_browser_view_class
        self.cog = cog_instance
        self.current_section = None
        self.page = 0
        self.items_per_page = 25
        self.max_pages = math.ceil(len(self.guide_data) / self.items_per_page)

        self.update_components()

    def update_components(self):
        """Aktualizuje Select menu a tlačítka podle aktuální stránky."""
        self.clear_items()
        
        # 1. Select Menu s kapitolami (stránkované)
        options = []
        start_idx = self.page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_batch = self.guide_data[start_idx:end_idx]

        for i, section in enumerate(current_batch):
            global_index = start_idx + i
            indent = "⠀" * ((section['level'] - 1) * 2) 
            label = f"{indent}{section['title']}"
            if len(label) > 100: label = label[:97] + "..."
            
            options.append(discord.SelectOption(
                label=label,
                value=str(global_index),
                description=f"Sekce {global_index + 1}"
            ))

        if options:
            select = discord.ui.Select(
                placeholder=f"Vyber kapitolu (Strana {self.page + 1}/{self.max_pages})",
                options=options,
                custom_id="chapter_select",
                row=0
            )
            select.callback = self.select_callback
            self.add_item(select)

        # 2. Stránkovací tlačítka (jen pokud je víc stránek)
        if self.max_pages > 1:
            prev_btn = discord.ui.Button(
                label="⬅️ Předchozí", 
                style=discord.ButtonStyle.secondary, 
                custom_id="prev_page", 
                disabled=(self.page == 0),
                row=1
            )
            next_btn = discord.ui.Button(
                label="Další ➡️", 
                style=discord.ButtonStyle.secondary, 
                custom_id="next_page", 
                disabled=(self.page >= self.max_pages - 1),
                row=1
            )
            self.add_item(prev_btn)
            self.add_item(next_btn)

        # 3. Akční tlačítka
        # Tlačítko pro obsah (užitečné při mnoha stránkách)
        self.add_item(discord.ui.Button(label="📖 Obsah", style=discord.ButtonStyle.primary, custom_id="toc_btn", row=2))
        self.add_item(discord.ui.Button(label="Vybrat text", style=discord.ButtonStyle.success, custom_id="send_text_btn", row=2))
        self.add_item(discord.ui.Button(label="Zpět do menu", style=discord.ButtonStyle.grey, custom_id="back_btn", row=2))


    async def select_callback(self, interaction: discord.Interaction):
        index = int(interaction.data['values'][0])
        self.current_section = self.guide_data[index]
        embed = self.create_section_embed(self.current_section)
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if "custom_id" in interaction.data:
            cid = interaction.data["custom_id"]
            
            if cid == "prev_page":
                self.page -= 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            
            elif cid == "next_page":
                self.page += 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            
            elif cid == "toc_btn":
                # Vygeneruje jednoduchý textový seznam kapitol
                lines = ["**Obsah návodu:**"]
                for i, sec in enumerate(self.guide_data):
                    indent = "-" * (sec['level'] - 1)
                    lines.append(f"`{i+1}.` {indent} {sec['title']}")
                
                content = "\n".join(lines)
                # Ošetření délky zprávy
                if len(content) > 2000:
                    content = content[:1900] + "\n... (a další)"
                
                await interaction.response.send_message(content, ephemeral=True)
                return False

            elif cid == "send_text_btn":
                if not self.current_section or not self.current_section['paragraphs']:
                    await interaction.response.send_message("Nejdřív vyber kapitolu, která má nějaký text.", ephemeral=True)
                    return False
                
                view = ParagraphSelectorView(self.current_section['paragraphs'], self.current_section['title'])
                await interaction.response.send_message("Vyber, které části textu chceš odeslat:", view=view, ephemeral=True)
                return False

            elif cid == "back_btn":
                embed = discord.Embed(
                    title="Formikaristika Prohlížeč",
                    description="Vítej v prohlížeči webu Formikaristika CZ.\nVyber kategorii pro procházení článků nebo použij rychlá tlačítka:",
                    color=discord.Color.green()
                )
                view = self.main_browser_view_class(self.cog)
                await interaction.response.edit_message(embed=embed, view=view)
                return False

        return True

    def create_section_embed(self, section):
        embed = discord.Embed(
            title=section['title'],
            color=discord.Color.dark_green(),
            url=CARE_GUIDE_URL
        )
        
        full_text = "\n\n".join(section['paragraphs'])
        
        if len(full_text) > 3500:
            description = full_text[:3500] + "\n\n*[Text je příliš dlouhý, pro zbytek použij 'Vybrat text']*..."
        elif len(full_text) == 0:
            description = "*Tato sekce obsahuje pouze podkapitoly, vyberte jednu z nich v menu.*"
        else:
            description = full_text

        embed.description = description
        
        # Obrázek: Snažíme se najít obrázek přímo v sekci
        # Pokud je nalezen, dáme ho jako velký (set_image)
        if section.get('images'):
            embed.set_image(url=section['images'][0])
            # Logo dáme jako thumbnail pro zachování značky
            embed.set_thumbnail(url=DEFAULT_IMAGE_URL)
        else:
            # Pokud není obrázek v sekci, dáme logo jako thumbnail
            embed.set_thumbnail(url=DEFAULT_IMAGE_URL)

        subsections = section.get('subsections', [])
        if subsections:
            sub_titles = [sub['title'] for sub in subsections]
            embed.add_field(name="Podkapitoly", value="\n".join(f"• {t}" for t in sub_titles), inline=False)
            
        embed.set_footer(text=f"Formikaristika.wordpress.com | Návod na chov | {section['title']}")
        return embed


class CategoryArticlesView(discord.ui.View):
    """View pro zobrazení článků v konkrétní kategorii."""
    def __init__(self, articles, category_name, main_view_class, cog):
        super().__init__(timeout=180)
        self.articles = articles # Seznam URL
        self.category_name = category_name
        self.main_view_class = main_view_class
        self.cog = cog
        self.page = 0
        self.items_per_page = 25
        self.max_pages = math.ceil(len(articles) / self.items_per_page)
        
        self.update_components()
        
    def update_components(self):
        self.clear_items()
        
        # Select menu článků
        options = []
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        batch = self.articles[start:end]
        
        for i, url in enumerate(batch):
            # Zkusíme získat hezké jméno z URL
            parsed = urlparse(url)
            slug = parsed.path.strip('/').split('/')[-1]
            label = slug.replace('-', ' ').capitalize()
            if len(label) > 100: label = label[:97] + "..."
            
            # OPRAVA: Používáme index jako value, protože URL může být > 100 znaků
            global_index = start + i
            options.append(discord.SelectOption(
                label=label,
                value=str(global_index),
                description="Klikni pro zobrazení"
            ))
            
        if options:
            select = discord.ui.Select(placeholder=f"Vyber článek ({self.page+1}/{self.max_pages})", options=options, custom_id="article_select")
            select.callback = self.article_select_callback
            self.add_item(select)
            
        # Navigace
        if self.max_pages > 1:
            self.add_item(discord.ui.Button(label="⬅️", custom_id="prev", disabled=(self.page==0), style=discord.ButtonStyle.secondary))
            self.add_item(discord.ui.Button(label="➡️", custom_id="next", disabled=(self.page>=self.max_pages-1), style=discord.ButtonStyle.secondary))
            
        self.add_item(discord.ui.Button(label="Zpět do kategorií", custom_id="back", style=discord.ButtonStyle.grey))

    async def article_select_callback(self, interaction: discord.Interaction):
        # OPRAVA: Načítáme URL podle indexu ze seznamu
        index = int(interaction.data['values'][0])
        url = self.articles[index]
        await interaction.response.defer()
        await self.cog.send_article_embed(interaction, url)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if "custom_id" in interaction.data:
            cid = interaction.data["custom_id"]
            if cid == "prev":
                self.page -= 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            elif cid == "next":
                self.page += 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            elif cid == "back":
                embed = discord.Embed(
                    title="Formikaristika Prohlížeč",
                    description="Vítej v prohlížeči webu Formikaristika CZ.\nVyber kategorii pro procházení článků nebo použij rychlá tlačítka:",
                    color=discord.Color.green()
                )
                view = self.main_view_class(self.cog)
                await interaction.response.edit_message(embed=embed, view=view)
                return False
        return True


class FormikaristikaBrowserView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance
        
        # Přidání Select Menu pro kategorie (Původní procházení)
        # Prioritně na prvním místě (row=0)
        self.add_category_select()

    def add_category_select(self):
        # Pokud kategorie nejsou načteny, zobrazíme placeholder
        if not self.cog.categories:
            self.add_item(discord.ui.Select(
                placeholder="Načítám kategorie... (zkus to za chvíli)",
                options=[discord.SelectOption(label="Načítání...", value="loading")],
                disabled=True,
                row=0
            ))
            return

        options = []
        # Seřadíme kategorie a vybereme prvních 25
        sorted_cats = sorted(self.cog.categories.keys())
        for cat in sorted_cats[:25]:
            count = len(self.cog.categories[cat])
            # OPRAVA: Oříznutí value na 100 znaků pro jistotu
            options.append(discord.SelectOption(
                label=f"{cat} ({count})",
                value=cat[:100]
            ))

        select = discord.ui.Select(
            placeholder="📂 Procházet kategorie webu",
            options=options,
            custom_id="category_select",
            row=0 # První řádek
        )
        select.callback = self.category_callback
        self.add_item(select)

    async def category_callback(self, interaction: discord.Interaction):
        cat_name = interaction.data['values'][0]
        articles = self.cog.categories.get(cat_name, [])
        
        embed = discord.Embed(
            title=f"Kategorie: {cat_name}",
            description=f"Nalezeno {len(articles)} článků. Vyber si jeden ze seznamu níže.",
            color=discord.Color.blue()
        )
        view = CategoryArticlesView(articles, cat_name, FormikaristikaBrowserView, self.cog)
        await interaction.response.edit_message(embed=embed, view=view)

    # Tlačítka (Řádek 1 - Rychlé volby)
    @discord.ui.button(label="Náhodný článek", style=discord.ButtonStyle.primary, emoji="🎲", row=1)
    async def random_article(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.cog.sitemap_urls:
            await interaction.followup.send("Sitemap zatím není načtena.", ephemeral=True)
            return
        import random
        url = random.choice(self.cog.sitemap_urls)
        await self.cog.send_article_embed(interaction, url)

    @discord.ui.button(label="Nejnovější článek", style=discord.ButtonStyle.success, emoji="🆕", row=1)
    async def latest_article(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.cog.sitemap_urls:
            await interaction.followup.send("Sitemap zatím není načtena.", ephemeral=True)
            return
        # Předpokládáme, že první v sitemap je nejnovější
        url = self.cog.sitemap_urls[0] 
        await self.cog.send_article_embed(interaction, url)

    @discord.ui.button(label="Návod na chov", style=discord.ButtonStyle.secondary, emoji="🐜", row=1)
    async def care_guide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.care_guide_data:
            await interaction.response.send_message("Návod se načítá...", ephemeral=True)
            await self.cog.load_care_guide() # Zkusit znovu
            return

        embed = discord.Embed(
            title="Návod na chov mravenců",
            description="Kompletní průvodce pro začínající i pokročilé chovatele.\n\nVyber si kapitolu z nabídky níže.",
            color=discord.Color.dark_green()
        )
        embed.set_thumbnail(url=DEFAULT_IMAGE_URL)

        view = CareGuideView(self.cog.care_guide_data, FormikaristikaBrowserView, self.cog)
        await interaction.response.edit_message(embed=embed, view=view)


class FormikaristikaCommands(app_commands.Group):
    def __init__(self, bot: discord.Client):
        super().__init__(name="formikaristika", description="Příkazy pro web Formikaristika CZ")
        self.bot = bot
        self.sitemap_urls = []
        self.categories = {} # {"Mravenci": [url1, ...], "Technika": [...]}
        self.species_map = {}
        self.care_guide_data = []
        
    async def on_ready(self):
        print("Načítám sitemapu Formikaristika CZ...")
        await self.load_sitemap()
        print("Načítám Návod na chov...")
        await self.load_care_guide()

    async def load_sitemap(self):
        try:
            response = requests.get(SITEMAP_URL)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                self.sitemap_urls = []
                self.species_map = {}
                self.categories = {}

                for url_elem in root.findall('sm:url', ns):
                    loc = url_elem.find('sm:loc', ns).text
                    self.sitemap_urls.append(loc)
                    
                    # 1. Kategorie pro procházení
                    parsed = urlparse(loc)
                    # OPRAVA: Filtrujeme prázdné stringy, aby nevznikla kategorie "" (prázdná)
                    path_parts = [p for p in parsed.path.strip('/').split('/') if p]
                    
                    if path_parts:
                        # První část cesty jako kategorie (např. 'mravenci', 'technika')
                        cat = path_parts[0].capitalize()
                        if cat.isdigit() and len(cat) == 4:
                            cat = "Blog (Archiv)"
                        
                        if cat not in self.categories:
                            self.categories[cat] = []
                        self.categories[cat].append(loc)

                    # 2. Autocomplete mapa
                    if 'mravenci' in path_parts and len(path_parts) >= 3:
                        slug = path_parts[-1]
                        name = slug.replace('-', ' ').capitalize()
                        self.species_map[name] = loc

                print(f"Sitemap: {len(self.sitemap_urls)} URL, {len(self.categories)} kategorií.")
            else:
                print(f"Chyba sitemap: {response.status_code}")
        except Exception as e:
            print(f"Výjimka sitemap: {e}")

    async def load_care_guide(self):
        try:
            response = requests.get(CARE_GUIDE_URL)
            if response.status_code != 200:
                return

            soup = BeautifulSoup(response.content, 'html.parser')
            content_div = soup.find('div', class_='entry-content')

            if not content_div: return

            structure = []
            current_section = {
                'title': "Úvod", 'level': 1, 'paragraphs': [], 'subsections': [], 'images': []
            }
            structure.append(current_section)
            section_stack = [current_section]

            elements = content_div.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'figure'])

            for el in elements:
                if el.name in ['h1', 'h2', 'h3', 'h4']:
                    level = int(el.name[1])
                    title = el.get_text(strip=True)
                    
                    new_section = {
                        'title': title, 'level': level, 'paragraphs': [], 'subsections': [], 'images': []
                    }
                    structure.append(new_section)
                    
                    while section_stack and section_stack[-1]['level'] >= level:
                        section_stack.pop()
                    if section_stack:
                        section_stack[-1]['subsections'].append(new_section)
                    section_stack.append(new_section)
                    current_section = new_section
                    
                else:
                    # Extrakce obrázků pro Embed
                    imgs = extract_images_from_element(el)
                    if imgs:
                        current_section['images'].extend(imgs)

                    # Extrakce textu
                    text = clean_html_text(el)
                    if text:
                        current_section['paragraphs'].append(text)

            self.care_guide_data = structure
            print(f"Návod načten: {len(structure)} sekcí.")

        except Exception as e:
            print(f"Výjimka návod: {e}")


    async def send_article_embed(self, interaction: discord.Interaction, url: str):
        details = await self.fetch_article_details(url)
        embed = discord.Embed(color=discord.Color.green())
        embed.title = details['title']
        embed.url = details['url']
        embed.description = details['excerpt']
        
        if details['image_url']:
            embed.set_image(url=details['image_url'])
            
        last_modified = details.get('modified_time')
        if last_modified:
            try:
                dt_object = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                formatted_date = dt_object.strftime("%d.%m.%Y")
                embed.add_field(name="Poslední úprava", value=formatted_date, inline=False)
            except ValueError:
                pass
        
        embed.set_footer(text="Data z formikaristika.wordpress.com")
        await interaction.followup.send(embed=embed)


    async def fetch_article_details(self, url: str):
        def blocking_io():
            try:
                r = requests.get(url)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, 'html.parser')
                    title = soup.find("meta", property="og:title")
                    title = title["content"] if title else soup.title.string
                    desc = soup.find("meta", property="og:description")
                    excerpt = desc["content"] if desc else "Bez popisu."
                    image = soup.find("meta", property="og:image")
                    image_url = image["content"] if image else None
                    mod_time = soup.find("meta", property="article:modified_time")
                    modified_time = mod_time["content"] if mod_time else None
                    return {"title": title, "url": url, "excerpt": excerpt, "image_url": image_url, "modified_time": modified_time}
            except Exception as e:
                return {"title": "Chyba", "url": url, "excerpt": str(e), "image_url": None, "modified_time": None}
            return {"title": "Neznámý", "url": url, "excerpt": "", "image_url": None, "modified_time": None}
        return await asyncio.to_thread(blocking_io)

    # --- PŘÍKAZY ---

    @app_commands.command(name="prochazet", description="Otevře interaktivní prohlížeč webu Formikaristika")
    async def browser(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Formikaristika Prohlížeč",
            description="Vítej v prohlížeči webu Formikaristika CZ.\nVyber kategorii pro procházení článků nebo použij rychlá tlačítka:",
            color=discord.Color.green()
        )
        view = FormikaristikaBrowserView(self)
        await interaction.response.send_message(embed=embed, view=view)


    async def species_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not self.species_map: return []
        choices = []
        for name, url in self.species_map.items():
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=url))
                if len(choices) >= 25: break
        return choices

    @app_commands.command(name="profil", description="Zobrazí profil konkrétního druhu mravence")
    @app_commands.autocomplete(url=species_autocomplete)
    @app_commands.describe(url="Začni psát jméno druhu (např. Lasius niger)")
    async def profile(self, interaction: discord.Interaction, url: str):
        if not url.startswith("http"):
            await interaction.response.send_message(f"Druh '{url}' nebyl nalezen. Použij prosím našeptávač.", ephemeral=True)
            return

        await interaction.response.defer()
        
        slug = url.strip('/').split('/')[-1]
        genus_species = slug.split('-')
        
        if len(genus_species) >= 2:
            genus = genus_species[0].capitalize()
            species = genus_species[1]
            antweb_url = f"https://www.antweb.org/description.do?genus={genus.lower()}&species={species.lower()}&rank=species"
            antwiki_url = f"https://www.antwiki.org/wiki/{genus}_{species}"
        else:
            antweb_url = "https://www.antweb.org"
            antwiki_url = "https://www.antwiki.org"

        details = await self.fetch_article_details(url)
        embed = discord.Embed(color=discord.Color.green())
        embed.title = details['title']
        embed.url = details['url'] 
        embed.description = details['excerpt']
        
        if details['image_url']: embed.set_image(url=details['image_url'])
        
        last_modified = details.get('modified_time')
        if last_modified:
            try:
                dt_object = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                formatted_date = dt_object.strftime("%d.%m.%Y")
                embed.add_field(name="Poslední úprava", value=formatted_date, inline=False)
            except ValueError:
                embed.add_field(name="Poslední úprava", value=last_modified, inline=False)
    
        links_text = (f"🔬 [AntWeb]({antweb_url}) | 📚 [AntWiki]({antwiki_url})")
        embed.add_field(name="Externí zdroje", value=links_text, inline=False)
        embed.set_footer(text="Data z formikaristika.wordpress.com")
        await interaction.followup.send(embed=embed)

# Tento soubor definuje skupinu příkazů `/info` pro Discord bota.
# Jeho hlavním úkolem je umožnit vyhledávání informací o mravencích
# na různých externích myrmekologických fórech.
#
# Funkce:
# - Definuje seznam fór (`ANT_FORUMS`) s jejich URL a parametry pro vyhledávání.
# - `search_forum_sync`: Synchronní funkce pro provedení web scrapingu na daném
#   fóru. Stáhne stránku s výsledky vyhledávání a parsuje ji pomocí
#   BeautifulSoup, aby získala relevantní odkazy, názvy a úryvky.
# - Příkaz `/info vyhledat`: Asynchronní příkaz, který přijímá dotaz od
#   uživatele. Spouští `search_forum_sync` v odděleném vlákně, aby
#   neblokoval bota, a postupně zobrazuje výsledky v Discord embed zprávě.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, beautifulsoup4
# - Standardní knihovny: urllib.parse, typing, datetime, asyncio

import discord
from discord import app_commands
import urllib.parse
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
import datetime
import asyncio # Nový import pro asynchronní čekání

# Seznam fór k prohledávání
# Každé fórum má nyní 'search_path' pro specifickou vyhledávací URL a 'searchable' flag.
ANT_FORUMS: List[dict] = [
    {"name": "Myrmecofourmis (FR)", "url": "www.myrmecofourmis.org/", "search_path": "forum/search.php?keywords=", "link_prefix": "https://www.myrmecofourmis.org/", "searchable": True},
    {"name": "Ameiseninfos (DE)", "url": "ameiseninfos.de/Forum/app.php/portal", "searchable": False, "reason": "Vyhledávání není povoleno."}, # Toto fórum nelze prohledávat
    {"name": "Ameisenhaltung (DE)", "url": "www.ameisenhaltung.de/cafe/", "search_path": "search.php?keywords=", "link_prefix": "https://www.ameisenhaltung.de/cafe/", "searchable": True},
    {"name": "Ameisenforum (DE)", "url": "ameisenforum.de/", "search_path": "search.php?keywords=", "link_prefix": "https://ameisenforum.de/", "searchable": True}, # Opravená search_path
    {"name": "Antstore (DE/EN)", "url": "www.antstore.net/forum/", "search_path": "search.php?keywords=", "link_prefix": "https://www.antstore.net/forum/", "searchable": True},
    {"name": "Eusozial (DE)", "url": "eusozial.de/", "search_path": "search.php?keywords=", "link_prefix": "https://eusozial.de/", "searchable": True},
    {"name": "AntForum (NL)", "url": "www.antforum.nl/", "search_path": "search.php?keywords=", "link_prefix": "https://www.antforum.nl/", "searchable": True},
    {"name": "Paco Alarcon Hormigas (ES)", "url": "pacoalarcon-hormigas.blogspot.com/", "search_path": "search?q=", "link_prefix": "https://pacoalarcon-hormigas.blogspot.com/", "searchable": True},
    {"name": "Termites and Ants (EN)", "url": "termitesandants.blogspot.com/", "search_path": "search?q=", "link_prefix": "https://termitesandants.blogspot.com/", "searchable": True},
    # Formiculture nyní používá Google vyhledávání pro spolehlivější výsledky
    {"name": "Formiculture (EN)", "url": "www.google.com/", "search_path": "search?q=site%3Aformiculture.com+", "link_prefix": "", "searchable": True, "is_google_search": True},
]

# Vytvoření nové skupiny příkazů
info_group = app_commands.Group(name="info", description="Příkazy pro získávání informací o mravencích a hmyzu.")

# Funkce pro prohledávání fóra
# Zůstává synchronní, protože používá knihovnu requests
def search_forum_sync(forum_data: dict, query: str) -> List[dict]:
    """
    Prohledá dané fórum pro zadaný dotaz.
    Vrací seznam slovníků s 'title', 'link' a 'snippet'.
    """
    search_results = []
    found_links = set() # Použijeme sadu pro sledování již nalezených URL adres

    # Zkontrolujeme, zda je fórum prohledávatelné
    if not forum_data.get("searchable", True):
        return [] # Pokud není prohledávatelné, vrátíme prázdný seznam

    forum_url_base = forum_data["url"]
    search_path = forum_data.get("search_path")
    link_prefix = forum_data.get("link_prefix")
    is_google_search = forum_data.get("is_google_search", False)

    if not search_path:
        print(f"Chyba: Pro fórum {forum_data['name']} není definována 'search_path'.")
        return []

    # Pro Formiculture (Google vyhledávání)
    if is_google_search:
        # Dotaz pro Google bude "site:formiculture.com <uživatelský dotaz>"
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://{forum_url_base}{search_path}{encoded_query}"
    else:
        # Pro ostatní fóra zůstává původní logika
        encoded_query = urllib.parse.quote(query.replace(" ", "+"))
        search_url = f"https://{forum_url_base}{search_path}{encoded_query}"
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status() # Vyvolá HTTPError pro špatné odpovědi (4xx nebo 5xx)
        soup = BeautifulSoup(response.text, 'html.parser')

        print(f"DEBUG: Google Search URL: {search_url}")
        print(f"DEBUG: Google Response Status: {response.status_code}")
        if response.status_code != 200:
            print(f"DEBUG: Google Response Text (partial): {response.text[:500]}")

        if is_google_search:
            # Nové parsování pro Google výsledky na základě poskytnutého HTML
            # Hledáme hlavní kontejnery výsledků, což je často div s class='MjjYud'
            result_containers = soup.find_all('div', class_='MjjYud')

            print(f"DEBUG: Found {len(result_containers)} Google result containers.")

            for result_block in result_containers:
                title = ""
                href = ""
                snippet = ""

                # Hledáme odkaz a titulek. Odkaz je často v <a> tagu, titulek pak v <h3> uvnitř <a>.
                # Zkoušíme různé cesty k nalezení odkazu a titulku.
                # První pokus: a tag s h3 uvnitř (nejběžnější)
                title_link_tag = result_block.find('a')
                if title_link_tag:
                    title_h3 = title_link_tag.find('h3')
                    if title_h3:
                        title = title_h3.get_text(strip=True)
                        href = title_link_tag['href']
                    else:
                        # Druhý pokus: titulek je přímo v a tagu
                        title = title_link_tag.get_text(strip=True)
                        href = title_link_tag['href']

                    # Google někdy obaluje skutečnou URL do /url?q=...&sa=U...
                    if "/url?q=" in href:
                        try:
                            href = urllib.parse.unquote(href.split("/url?q=")[1].split("&sa=")[0])
                        except IndexError:
                            pass # Použijeme původní href, pokud je formát nečekaný

                # Hledáme snippet (popisek)
                # Snippet je často v divu s třídou 'VwiC3b' nebo v jiných textových elementech v rámci bloku.
                snippet_tag = result_block.find('div', class_='VwiC3b')
                if not snippet_tag:
                    # Alternativní třídy pro snippet, pokud 'VwiC3b' není nalezeno
                    snippet_tag = result_block.find('span', class_='aCOpNe') or \
                                  result_block.find('div', class_='lEBKkf') or \
                                  result_block.find('span', class_='st')
                
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                print(f"DEBUG: Found result - Title: {title}, Link: {href}, Snippet: {snippet[:50]}")

                # Zajištění, že odkaz je z Formiculture.com a není prázdný
                if title and href and "formiculture.com" in href:
                    if href in found_links:
                        continue

                    search_results.append({
                        "title": title,
                        "link": href,
                        "snippet": snippet
                    })
                    found_links.add(href)
                    if len(search_results) >= 3: # Omezíme na 3 výsledky
                        break
        else:
            # Původní parsování pro ostatní fóra
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                href = link['href']

                if not href.startswith(('http://', 'https://')):
                    if link_prefix:
                        href = urllib.parse.urljoin(link_prefix, href)
                    else:
                        continue

                if query.lower() in title.lower() or query.lower() in href.lower():
                    if href in found_links:
                        continue

                    snippet = ""
                    parent = link.find_parent()
                    if parent:
                        for sibling in parent.find_next_siblings():
                            if sibling.name == 'p' and sibling.get_text(strip=True):
                                snippet = sibling.get_text(strip=True)
                                break
                        if not snippet:
                            full_text = parent.get_text(strip=True)
                            snippet = (full_text[:100] + '...') if len(full_text) > 100 else full_text

                    if title and href:
                        search_results.append({
                            "title": title,
                            "link": href,
                            "snippet": snippet
                        })
                        found_links.add(href)
                        if len(search_results) >= 3:
                            break
    except requests.exceptions.RequestException as e:
        print(f"Chyba při prohledávání {forum_data['name']} ({forum_url_base}): {e}")
    return search_results


@info_group.command(name="vyhledat", description="Vyhledá informace o mravencích na vybraných fórech.")
@app_commands.describe(dotaz="Co chceš vyhledat?", forum_name="Volitelně vyber konkrétní fórum k prohledání.")
@app_commands.choices(forum_name=[
    app_commands.Choice(name=f["name"], value=f["name"]) for f in ANT_FORUMS
])
async def info_vyhledat(interaction: discord.Interaction, dotaz: str, forum_name: Optional[app_commands.Choice[str]] = None):
    await interaction.response.defer()

    embed = discord.Embed(
        title=f"Vyhledávání: \"{dotaz}\"",
        description="Probíhá vyhledávání na fórech...",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    embed.set_thumbnail(url="https://placehold.co/128x128/ADD8E6/000000?text=Mravenec") 

    all_results_found = False
    
    forums_to_search = []
    if forum_name:
        selected_forum_name_str = forum_name.value
        found_forum = next((f for f in ANT_FORUMS if f["name"] == selected_forum_name_str), None)
        if found_forum:
            forums_to_search.append(found_forum)
        else:
            await interaction.edit_original_response(embed=discord.Embed(
                title="Chyba",
                description=f"Fórum '{selected_forum_name_str}' nebylo nalezeno v seznamu.",
                color=discord.Color.red()
            ))
            return
    else:
        forums_to_search = ANT_FORUMS

    for i, forum_data in enumerate(forums_to_search):
        forum_name_display = forum_data["name"]
        
        if not forum_data.get("searchable", True):
            reason = forum_data.get("reason", "Není dostupné pro vyhledávání.")
            embed.add_field(name=f"Výsledky z: {forum_name_display}", value=f"⚠️ Fórum nelze prohledat: {reason}", inline=False)
            await interaction.edit_original_response(embed=embed)
            if not forum_name and i < len(forums_to_search) - 1:
                await asyncio.sleep(1)
            continue

        embed.description = f"Probíhá vyhledávání na fóru: **{forum_name_display}**..."
        await interaction.edit_original_response(embed=embed)

        results = await asyncio.to_thread(search_forum_sync, forum_data, dotaz)
        
        if results:
            all_results_found = True
            forum_results_text = ""
            for res in results:
                snippet = (res['snippet'][:100] + '...') if len(res['snippet']) > 100 else res['snippet']
                forum_results_text += f"**[{res['title']}]({res['link']})**\n> {snippet}\n"
            
            if len(forum_results_text) > 900:
                forum_results_text = forum_results_text[:900] + "... (pokračování zkráceno)"

            embed.add_field(name=f"Výsledky z: {forum_name_display}", value=forum_results_text, inline=False)
        else:
            embed.add_field(name=f"Výsledky z: {forum_name_display}", value="Žádné výsledky.", inline=False)

        if not forum_name and i < len(forums_to_search) - 1:
            await asyncio.sleep(1)

    if all_results_found:
        embed.description = "Zde jsou nejlepší výsledky nalezené na jednotlivých fórech:"
        embed.color = discord.Color.green()
    else:
        embed.description = "Bohužel se nepodařilo najít žádné relevantní výsledky. Zkuste prosím jiný dotaz."
        embed.color = discord.Color.red()

    embed.set_footer(text=f"Vyhledávání provedl: {interaction.user.display_name}")
    
    await interaction.edit_original_response(embed=embed)

# --- Instrukce pro integraci do hlavního souboru --
# 1. Ulož tento soubor jako `info_commands.py` ve stejné složce jako tvůj hlavní bot soubor.
# 2. Ujisti se, že máš nainstalované potřebné knihovny: pip install requests beautifulsoup4 discord.py
# 3. V hlavním souboru bota (např. main.py) importuj skupinu příkazů:
#    from info_commands import info_group
# 4. A zaregistruj ji do tree (stromu příkazů):
#    tree.add_command(info_group)



# Tento soubor definuje skupinu příkazů `/isop` pro Discord bota.
# Zodpovídá za vyhledávání informací o druzích mravenců na portálu ISOP
# a generování odkazů na karty druhů a nálezové mapy ČR.
#
# Funkce:
# - Příkaz `/isop hledat`: Umožňuje uživateli zadat rod a druh mravce.
#   Pokusí se získat ID druhu z ISOP portálu pomocí web scrapingu.
#   Pokud je ID nalezeno, vytvoří přímý odkaz na kartu druhu s mapou.
#   Pokud ID není nalezeno, poskytne obecný odkaz na vyhledávání na ISOP.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, beautifulsoup4.
# - Standardní knihovny: urllib.parse.

import discord
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import io # Ponecháváme pro případné budoucí použití, i když pro obrázky mapy již není přímo využíváno


# Základní URL pro ISOP portál
ISOP_BASE_URL = "https://portal.nature.cz"
ISOP_SEARCH_URL = f"{ISOP_BASE_URL}/hledej"

# Nová URL pro nálezovou mapu, která uses ID
ISOP_MAP_URL_BASE = "https://sitovemapy.nature.cz/mapy/druh-vyskyt/"
# URL pro kartu druhu na ISOP portálu, která uses ID
ISOP_SPECIES_CARD_URL_BASE = f"{ISOP_BASE_URL}/w/druh-"

# URL pro iNaturalist API
INATURALIST_API_TAXA_SEARCH_URL = "https://api.inaturalist.org/v1/taxa"
INATURALIST_BASE_URL = "https://www.inaturalist.org/taxa/"


# Vytvoření skupiny příkazů pro ISOP
isop_group = app_commands.Group(name="isop", description="Vyhledávání informací o druzích na ISOP portálu.")

async def get_isop_species_info(rod: str, druh: str) -> dict | None:
    """
    Pokusí se získat ID druhu a URL karty druhu z ISOP portálu pro daný rod a druh.
    Používá web scraping, protože ISOP nemá přímé API pro získání ID z názvu.
    Vrací slovník s 'id' (str) a 'species_card_url' (str) nebo None, pokud není nalezeno.
    """
    search_query = f"{rod} {druh}"
    encoded_query = urllib.parse.quote_plus(search_query)
    search_url_with_query = f"{ISOP_SEARCH_URL}?q={encoded_query}"

    try:
        response = requests.get(search_url_with_query, timeout=10)
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
                        # Zajištění, že URL je absolutní
                        full_species_card_url = urllib.parse.urljoin(ISOP_BASE_URL, href)
                        return {"id": match.group(1), "species_card_url": full_species_card_url}

        return None

    except requests.exceptions.Timeout:
        print(f"Chyba: Vypršel časový limit při připojování k ISOP portálu pro dotaz '{search_query}'.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Chyba při komunikaci s ISOP portálem pro dotaz '{search_query}': {e}")
        return None
    except Exception as e:
        print(f"Neočekávaná chyba při získávání ID druhu z ISOP pro '{search_query}': {e}")
        return None

async def get_species_card_details(species_card_url: str) -> dict:
    """
    Navštíví URL karty druhu na portal.nature.cz a pokusí se extrahovat
    informace jako Říše, Řád, Čeleď, Ochrana a Hodnocení.
    Vrací slovník s nalezenými detaily.
    """
    details = {
        "Říše": "N/A",
        "Řád": "N/A",
        "Čeleď": "N/A",
        "Ochrana": "N/A",
        "Hodnocení": "N/A"
    }
    print(f"Pokouším se získat detaily z karty druhu: {species_card_url}")
    try:
        response = requests.get(species_card_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Vylepšené hledání Říše, Řádu, Čeledi
        # Hledáme div s třídou 'sc-header__items' a pak uvnitř 'sc-header__item'
        taxonomic_data_container = soup.find('div', class_='sc-header__items')
        if taxonomic_data_container:
            for item_div in taxonomic_data_container.find_all('div', class_='sc-header__item'):
                desc_span = item_div.find('span', class_='sc-header__desc')
                value_br = item_div.find('br')
                if desc_span and value_br:
                    label_text = desc_span.get_text(strip=True).replace(':', '')
                    # Získání textu po <br> tagu
                    value_text = value_br.next_sibling.strip() if value_br.next_sibling else "N/A"
                    
                    if label_text == "Říše":
                        details["Říše"] = value_text
                    elif label_text == "Řád":
                        details["Řád"] = value_text
                    elif label_text == "Čeleď":
                        details["Čeleď"] = value_text
        
        # Ochrana a Hodnocení - vylepšené parsování
        # Hledáme div s třídou 'list-icon' a uvnitř 'list-icon__list' a pak 'img' tagy
        
        # Funkce pro parsování sekcí Ochrana/Hodnocení
        def parse_protection_evaluation_section(section_class: str, soup_obj: BeautifulSoup) -> str:
            section_value = []
            # Hledáme div s třídou 'list-icon' a specifickou třídou pro sekci
            section_container = soup_obj.find('div', class_=f'list-icon {section_class}')
            if section_container:
                list_icon_list = section_container.find('ul', class_='list-icon__list')
                if list_icon_list:
                    for img_tag in list_icon_list.find_all('img', class_='list-icon__img'):
                        # Prioritně získáme data-original-title
                        description_text = img_tag.get('data-original-title')
                        
                        # Pokud data-original-title není, zkusíme title
                        if not description_text:
                            description_text = img_tag.get('title')
                        
                        if description_text:
                            section_value.append(description_text.strip())
            return ", ".join(section_value) if section_value else "N/A"

        details["Ochrana"] = parse_protection_evaluation_section("species-card__protection", soup)
        details["Hodnocení"] = parse_protection_evaluation_section("species-card__evaluation", soup)

        print(f"Nalezené detaily: {details}")
        return details

    except requests.exceptions.Timeout:
        print(f"Chyba: Vypršel časový limit při získávání detailů z karty druhu: {species_card_url}")
        return details # Vracíme defaultní hodnoty
    except requests.exceptions.RequestException as e:
        print(f"Chyba při komunikaci s ISOP portálem (karta druhu): {e}")
        return details
    except Exception as e:
        print(f"Neočekávaná chyba při získávání detailů z karty druhu: {e}")
        return details

async def get_inaturalist_image_url(species_name: str) -> str | None:
    """
    Pokusí se získat URL obrázku druhu z iNaturalist.org pomocí iNaturalist API.
    """
    print(f"Hledám obrázek z iNaturalist API pro: {species_name}")
    try:
        # Krok 1: Vyhledání taxonu pomocí iNaturalist API
        params = {"q": species_name, "rank": "species", "per_page": 1}
        response_api = requests.get(INATURALIST_API_TAXA_SEARCH_URL, params=params, timeout=10)
        response_api.raise_for_status()
        data = response_api.json()

        if data and data.get('results'):
            # Získáme ID taxonu z prvního výsledku
            taxon_id = data['results'][0]['id']
            print(f"Nalezeno iNaturalist taxon ID: {taxon_id}")

            # Krok 2: Získání detailů taxonu, které obsahují defaultní obrázek
            # Můžeme použít buď /taxa/{id} endpoint nebo přímo z výsledku vyhledávání
            # Pokud je `default_photo` k dispozici přímo ve výsledku vyhledávání:
            default_photo = data['results'][0].get('default_photo')
            if default_photo and default_photo.get('medium_url'):
                image_url = default_photo['medium_url']
                print(f"Nalezena iNaturalist obrázková URL z API: {image_url}")
                return image_url
            else:
                print("Defaultní fotografie nenalezena v API výsledku.")
                return None
        else:
            print("Nenalezen žádný taxon na iNaturalist API pro daný druh.")
            return None

    except requests.exceptions.Timeout:
        print(f"Chyba: Vypršel časový limit při připojování k iNaturalist API pro '{species_name}'.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Chyba při komunikaci s iNaturalist API pro '{species_name}': {e}")
        return None
    except Exception as e:
        print(f"Neočekávaná chyba při získávání obrázku z iNaturalist API pro '{species_name}': {e}")
        return None


@isop_group.command(name="hledat", description="Zobrazí kartu druhu a nálezovou mapu ČR z ISOP portálu.")
@app_commands.describe(rod="Rod mravence (např. Camponotus)", druh="Druh mravence (např. vagus)")
async def isop_hledat(interaction: discord.Interaction, rod: str, druh: str):
    await interaction.response.defer(ephemeral=False)

    full_species_name = f"{rod.capitalize()} {druh.lower()}"
    
    # Získání ID a URL karty druhu z ISOP
    isop_info = await get_isop_species_info(rod, druh)

    # Získání detailů z karty druhu na ISOP
    species_details = await get_species_card_details(isop_info["species_card_url"]) if isop_info else None

    # Pokus o získání obrázku z iNaturalist
    inaturalist_image_url = await get_inaturalist_image_url(full_species_name)

    embed = discord.Embed(
        title=f"Karta druhu a nálezová mapa ČR pro {full_species_name}",
        description="Zde jsou odkazy na ISOP portál a nálezovou mapu:",
        color=discord.Color.green()
    )
    
    # Nastavení náhledového obrázku
    if inaturalist_image_url:
        embed.set_image(url=inaturalist_image_url) # Změněno z set_thumbnail na set_image
        print(f"Používám obrázek z iNaturalist: {inaturalist_image_url}")
    else:
        embed.set_thumbnail(url="https://placehold.co/128x128/ADD8E6/000000?text=Mapa") # Zástupný obrázek
        print("Nepodařilo se získat obrázek z iNaturalist, používám zástupný obrázek mapy.")

    # Přidání detailů do embedu, pokud byly získány
    if species_details:
        embed.add_field(name="Říše", value=species_details["Říše"], inline=True)
        embed.add_field(name="Řád", value=species_details["Řád"], inline=True)
        embed.add_field(name="Čeleď", value=species_details["Čeleď"], inline=True)
        
        # Prázdné pole pro zarovnání, pokud je potřeba (Discord zobrazuje 3 inline pole na řádek)
        if (len(embed.fields) % 3) != 0:
            embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(name="Ochrana", value=species_details["Ochrana"], inline=False)
        embed.add_field(name="Hodnocení", value=species_details["Hodnocení"], inline=False)

    # Přidání odkazů
    if isop_info:
        map_url_for_browser = f"{ISOP_MAP_URL_BASE}{isop_info['id']}"
        embed.add_field(name="Karta druhu na ISOP", value=f"[:page_facing_up: Odkaz]({isop_info['species_card_url']})", inline=False)
        embed.add_field(name="Nálezová mapa ČR", value=f"[:map: Odkaz]({map_url_for_browser})", inline=False)
    else:
        search_url = f"{ISOP_SEARCH_URL}?q={urllib.parse.quote_plus(full_species_name)}"
        embed.add_field(name="Odkaz na vyhledávání ISOP", value=f"[:mag: Vyhledat na ISOP portálu]({search_url})", inline=False)

    embed.set_footer(text="Data z Informačního systému ochrany přírody (ISOP) a iNaturalist.org")
    
    await interaction.followup.send(embed=embed)


# --- Instrukce pro integraci do hlavního souboru (main.py) ---
# 1. Ulož tento soubor jako `isop_commands.py` do stejné složky jako `main.py`.
# 2. V `main.py` přidej na začátek souboru import:
#    `from isop_commands import isop_group`
# 3. V `main.py` uvnitř funkce `on_ready()` (za `await load_sitemap()`) přidej registraci skupiny příkazů:
#    `tree.add_command(isop_group)`
# 4. Ujisti se, že máš nainstalované knihovny `requests` a `beautifulsoup4`:
#    `pip install requests beautifulsoup4`


# Tento soubor obsahuje veškerou logiku a příkazy související s kvízem.
# Je navržen tak, aby byl importován a inicializován z hlavního souboru (main.py).
#
# Funkce:
# - Definuje třídu `QuizCommands` pro zapouzdření stavu a logiky kvízu.
# - Definuje `QuizSelectionView` pro interaktivní výběr typu a obtížnosti kvízu.
# - Definuje `QuestionSuggestionModal` a `SuggestionSetupView` pro navrhování nových otázek.
# - Obsahuje metodu `run_quiz` pro samotný průběh kvízu.
# - Registruje příkazy `/kviz`, `/napoveda`, `/skore`, `/skore_tyden`, `/upravit_skore` a `/navrh_otazky`.
# - Spravuje schvalovací proces pro nové otázky pomocí reakcí a časového limitu.
#
# Závislosti:
# - discord.py, difflib, utils.py

import discord
from discord import app_commands, ui
import time
import asyncio
import random
import datetime
import difflib
import json
import os
from utils import PaginatorView

# --- Konstanty ---
QUIZ_QUESTIONS_FILE = 'quiz_questions.json'
QUIZ_SUGGESTIONS_FILE = 'quiz_suggestions.json'
QUIZ_ROLE_ID = 1064127470615408792
APPROVAL_THRESHOLD = 10
SUGGESTION_LIFETIME_DAYS = 3
MIN_SCORE_TO_SUGGEST = 1000

# --- Modální okno pro návrh otázky (krok 2) ---
class QuestionSuggestionModal(ui.Modal, title='Návrh nové kvízové otázky'):
    def __init__(self, cog_instance: 'QuizCommands', quiz_type: str, difficulty: str):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.quiz_type = quiz_type
        self.difficulty = difficulty

        self.question_text = ui.TextInput(
            label="Znění nové otázky",
            style=discord.TextStyle.paragraph,
            placeholder="Napište sem celou otázku...",
            required=True
        )
        self.add_item(self.question_text)

        self.answers_text = ui.TextInput(
            label="Správné odpovědi (oddělené čárkou)",
            placeholder="např. odpověď 1, odpověď 2, ...",
            required=True
        )
        self.add_item(self.answers_text)

        self.points_text = ui.TextInput(
            label="Počet bodů za správnou odpověď",
            placeholder="např. 25",
            required=True
        )
        self.add_item(self.points_text)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            points = int(self.points_text.value)
            
            # Validace bodů podle obtížnosti
            if (self.difficulty == "lehká" and not (10 <= points <= 30)) or \
               (self.difficulty == "střední" and not (40 <= points <= 60)) or \
               (self.difficulty == "těžká" and not (70 <= points <= 90)):
                await interaction.response.send_message(f"Počet bodů ({points}) neodpovídá zvolené obtížnosti '{self.difficulty.capitalize()}'. Zkuste to prosím znovu.", ephemeral=True)
                return

        except ValueError:
            await interaction.response.send_message("Počet bodů musí být celé číslo. Zkuste to prosím znovu.", ephemeral=True)
            return

        quiz_role = interaction.guild.get_role(QUIZ_ROLE_ID)
        answers = [ans.strip() for ans in self.answers_text.value.split(',')]

        embed = discord.Embed(
            title="🆕 Nový návrh na kvízovou otázku",
            description=f"Uživatel {interaction.user.mention} navrhl novou otázku.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Typ", value=self.quiz_type.capitalize(), inline=True)
        embed.add_field(name="Obtížnost", value=self.difficulty.capitalize(), inline=True)
        embed.add_field(name="Body", value=points, inline=True)
        embed.add_field(name="Otázka", value=self.question_text.value, inline=False)
        embed.add_field(name="Odpovědi", value="||`" + "`, `".join(answers) + "`||", inline=False)
        embed.set_footer(text=f"Pro schválení je potřeba {APPROVAL_THRESHOLD} reakcí 👍. Návrh vyprší za {SUGGESTION_LIFETIME_DAYS} dny.")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.response.send_message("Děkujeme za návrh! Byl odeslán ke schválení.", ephemeral=True)
        
        suggestion_message = await interaction.channel.send(
            content=quiz_role.mention if quiz_role else "",
            embed=embed
        )
        await suggestion_message.add_reaction("👍")
        await suggestion_message.add_reaction("👎")

        suggestion_data = {
            "author_id": interaction.user.id,
            "channel_id": interaction.channel.id,
            "timestamp": suggestion_message.created_at.isoformat(),
            "question_data": {
                "type": self.quiz_type,
                "difficulty": self.difficulty,
                "question": self.question_text.value,
                "answer": answers,
                "points": points
            }
        }
        
        self.cog.pending_suggestions[str(suggestion_message.id)] = suggestion_data
        self.cog.save_suggestions()

# --- View pro nastavení návrhu (krok 1) ---
class SuggestionSetupView(ui.View):
    def __init__(self, cog_instance: 'QuizCommands'):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.selected_type = None
        self.selected_difficulty = None

        # Select menu pro typ
        self.type_select = ui.Select(
            placeholder="Vyberte typ kvízu...",
            options=[
                discord.SelectOption(label="Mravenci", value="mravenci"),
                discord.SelectOption(label="Hmyz", value="hmyz"),
                discord.SelectOption(label="Obecný", value="obecny"),
            ],
            custom_id="suggest_type"
        )
        self.type_select.callback = self.on_type_select
        self.add_item(self.type_select)

        # Select menu pro obtížnost
        self.difficulty_select = ui.Select(
            placeholder="Vyberte obtížnost...",
            options=[
                discord.SelectOption(label="Lehká (10-30 bodů)", value="lehká"),
                discord.SelectOption(label="Střední (40-60 bodů)", value="střední"),
                discord.SelectOption(label="Těžká (70-90 bodů)", value="těžká"),
            ],
            custom_id="suggest_difficulty"
        )
        self.difficulty_select.callback = self.on_difficulty_select
        self.add_item(self.difficulty_select)

        # Tlačítko pro pokračování
        self.continue_button = ui.Button(label="Pokračovat k zadání otázky", style=discord.ButtonStyle.green, custom_id="suggest_continue", disabled=True)
        self.continue_button.callback = self.on_continue
        self.add_item(self.continue_button)

    async def on_type_select(self, interaction: discord.Interaction):
        self.selected_type = interaction.data['values'][0]
        self.check_if_ready()
        await interaction.response.edit_message(view=self)

    async def on_difficulty_select(self, interaction: discord.Interaction):
        self.selected_difficulty = interaction.data['values'][0]
        self.check_if_ready()
        await interaction.response.edit_message(view=self)

    def check_if_ready(self):
        if self.selected_type and self.selected_difficulty:
            self.continue_button.disabled = False

    async def on_continue(self, interaction: discord.Interaction):
        if not self.selected_type or not self.selected_difficulty:
            await interaction.response.send_message("Musíte vybrat typ i obtížnost.", ephemeral=True)
            return
        
        modal = QuestionSuggestionModal(self.cog, self.selected_type, self.selected_difficulty)
        await interaction.response.send_modal(modal)
        
        # Deaktivujeme view po odeslání modalu
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)


class QuizSelectionView(discord.ui.View):
    """
    View pro výběr typu a obtížnosti kvízu a jeho spuštění.
    """
    def __init__(self, cog_instance: 'QuizCommands'):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.quiz_questions_data = self.cog.quiz_questions
        self.selected_type = None
        self.selected_difficulty = None

        # Vytvoření select menu pro typ kvízu
        quiz_type_options = [discord.SelectOption(label=quiz_type.capitalize(), value=quiz_type) for quiz_type in self.quiz_questions_data.keys()]
        self.quiz_type_select = discord.ui.Select(
            placeholder="Vyberte typ kvízu...",
            options=quiz_type_options,
            custom_id="quiz_type_select"
        )
        self.add_item(self.quiz_type_select)
        self.quiz_type_select.callback = self.on_quiz_type_select

        # Tlačítko pro spuštění kvízu (zpočátku zakázané)
        self.start_button = discord.ui.Button(label="Spustit kvíz", style=discord.ButtonStyle.green, custom_id="start_quiz_button", disabled=True)
        self.add_item(self.start_button)
        self.start_button.callback = self.on_start_button

        # Tlačítko pro náhodný kvíz (vždy povolené)
        self.random_quiz_button = ui.Button(label="Náhodný kvíz", style=discord.ButtonStyle.grey, custom_id="random_quiz_button", disabled=False)
        self.add_item(self.random_quiz_button)
        self.random_quiz_button.callback = self.on_random_quiz_button

    async def on_quiz_type_select(self, interaction: discord.Interaction):
        self.selected_type = interaction.data['values'][0]
        
        difficulty_options = []
        if self.selected_type in self.quiz_questions_data:
            difficulty_keys = list(self.quiz_questions_data[self.selected_type].keys())
            for difficulty in difficulty_keys:
                difficulty_options.append(discord.SelectOption(label=difficulty.capitalize(), value=difficulty))
        
        # Odebrání starého selectu pro obtížnost, pokud existuje
        for item in self.children[:]:
            if isinstance(item, discord.ui.Select) and item.custom_id == "quiz_difficulty_select":
                self.remove_item(item)
        
        self.quiz_difficulty_select = ui.Select(
            placeholder="Vyberte obtížnost...",
            options=difficulty_options,
            custom_id="quiz_difficulty_select",
            disabled=False
        )
        self.quiz_difficulty_select.callback = self.on_quiz_difficulty_select
        self.add_item(self.quiz_difficulty_select)
        
        # Seřazení prvků, aby selecty byly nahoře
        self.children.sort(key=lambda x: 0 if isinstance(x, ui.Select) else 1)
        await interaction.response.edit_message(view=self)

    async def on_quiz_difficulty_select(self, interaction: discord.Interaction):
        self.selected_difficulty = interaction.data['values'][0]
        self.start_button.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_start_button(self, interaction: discord.Interaction):
        if self.cog.quiz_active:
            await interaction.response.send_message("Kvíz již probíhá! Počkejte prosím, až skončí aktuální kvíz.", ephemeral=True)
            return

        if not self.selected_type or not self.selected_difficulty:
            await interaction.response.send_message("Prosím, vyberte typ a obtížnost kvízu.", ephemeral=True)
            return
        
        selected_questions = self.cog.quiz_questions.get(self.selected_type, {}).get(self.selected_difficulty, {})
        
        if not selected_questions:
            await interaction.response.send_message(f"Pro typ '{self.selected_type}' a obtížnost '{self.selected_difficulty}' nejsou k dispozici žádné otázky.", ephemeral=True)
            return

        self.cog.quiz_active = True
        self.cog.active_quiz_channel = interaction.channel
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Spouštím kvíz: **{self.selected_type.capitalize()} - {self.selected_difficulty.capitalize()}**!", view=self)
        
        announcement_channel = interaction.channel
        quiz_role = interaction.guild.get_role(QUIZ_ROLE_ID)
        if (time.time() - self.cog.last_quiz_start_message_time) >= 10800: # 3 hodiny
            await announcement_channel.send(f"Byl spuštěn kvíz: **{self.selected_type.capitalize()} - {self.selected_difficulty.capitalize()}**! {quiz_role.mention if quiz_role else ''} připojte se a ukažte své znalosti!")
            self.cog.last_quiz_start_message_time = time.time()

        try:
            await self.run_quiz(interaction.channel, selected_questions, self.selected_type)
        finally:
            self.cog.quiz_active = False
            self.cog.active_quiz_channel = None
            self.cog.current_quiz_question_data = None

    async def on_random_quiz_button(self, interaction: discord.Interaction):
        if self.cog.quiz_active:
            await interaction.response.send_message("Kvíz již probíhá! Počkejte prosím, až skončí aktuální kvíz.", ephemeral=True)
            return

        if not self.cog.quiz_questions:
            await interaction.response.send_message("Kvíz nelze spustit, chybí otázky.", ephemeral=True)
            return

        random_type = random.choice(list(self.cog.quiz_questions.keys()))
        random_difficulty = random.choice(list(self.cog.quiz_questions[random_type].keys()))
        selected_questions = self.cog.quiz_questions.get(random_type, {}).get(random_difficulty, {})
        
        if not selected_questions:
            await interaction.response.send_message(f"Pro náhodně vybraný typ '{random_type}' a obtížnost '{random_difficulty}' nejsou k dispozici žádné otázky.", ephemeral=True)
            return

        self.cog.quiz_active = True
        self.cog.active_quiz_channel = interaction.channel
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Spouštím náhodný kvíz: **{random_type.capitalize()} - {random_difficulty.capitalize()}**!", view=self)
        
        announcement_channel = interaction.channel
        quiz_role = interaction.guild.get_role(QUIZ_ROLE_ID)
        if (time.time() - self.cog.last_quiz_start_message_time) >= 1200: # 20 minut
            await announcement_channel.send(f"Byl spuštěn náhodný kvíz: **{random_type.capitalize()} - {random_difficulty.capitalize()}**! {quiz_role.mention if quiz_role else ''} připojte se a ukažte své znalosti!")
            self.cog.last_quiz_start_message_time = time.time()

        try:
            await self.run_quiz(interaction.channel, selected_questions, random_type)
        finally:
            self.cog.quiz_active = False
            self.cog.active_quiz_channel = None
            self.cog.current_quiz_question_data = None

    async def run_quiz(self, channel: discord.TextChannel, questions_data: dict, quiz_type: str):
        current_week = str(datetime.datetime.now(datetime.timezone.utc).isocalendar().week)
        
        questions = list(questions_data.items())
        random.shuffle(questions)
        question_count = 0
        unanswered_consecutive_count = 0

        for question, data in questions:
            if question_count >= 10 or unanswered_consecutive_count >= 3:
                break
            
            self.cog.current_quiz_question_data = {"question": question, "answers": data["answer"]}
            await channel.send(f"**Otázka:** {question}")
            possible_answers = data["answer"]
            points = data["points"]
            
            answered_correctly_this_round = False
            incorrect_responders = set()
            start_time = time.time()
            QUIZ_TIMEOUT = 30.0

            while time.time() - start_time < QUIZ_TIMEOUT:
                try:
                    remaining_time = QUIZ_TIMEOUT - (time.time() - start_time)
                    if remaining_time <= 0:
                        break

                    message = await self.cog.client.wait_for(
                        'message',
                        timeout=remaining_time,
                        check=lambda msg: msg.channel == channel and not msg.author.bot
                    )
                    
                    user_id = str(message.author.id)
                    user_answer_lower = message.content.lower()
                    
                    is_correct = False
                    for correct_ans in possible_answers:
                        similarity = difflib.SequenceMatcher(None, user_answer_lower, correct_ans.lower()).ratio()
                        if similarity >= 0.83:
                            is_correct = True
                            break
                    
                    if is_correct:
                        time_taken = time.time() - start_time
                        gained_points = max(1, round(points - (time_taken / 2)))

                        old_overall_score = self.cog.scores["total_scores"].get(user_id, {}).get("overall", 0)

                        if user_id not in self.cog.scores["total_scores"]:
                            self.cog.scores["total_scores"][user_id] = {"overall": 0, "hints": 0}
                        if quiz_type not in self.cog.scores["total_scores"][user_id]:
                            self.cog.scores["total_scores"][user_id][quiz_type] = 0
                        if "hints" not in self.cog.scores["total_scores"][user_id]:
                            self.cog.scores["total_scores"][user_id]["hints"] = 0

                        self.cog.scores["total_scores"][user_id]["overall"] += gained_points
                        self.cog.scores["total_scores"][user_id][quiz_type] += gained_points
                        
                        new_overall_score = self.cog.scores["total_scores"][user_id]["overall"]
                        hints_earned_this_turn = (new_overall_score // 1000) - (old_overall_score // 1000)
                        
                        if hints_earned_this_turn > 0:
                            current_hints = self.cog.scores["total_scores"][user_id]["hints"]
                            self.cog.scores["total_scores"][user_id]["hints"] = min(3, current_hints + hints_earned_this_turn)
                            if self.cog.scores["total_scores"][user_id]["hints"] > current_hints:
                                await channel.send(f"{message.author.mention}, získal jsi {self.cog.scores['total_scores'][user_id]['hints'] - current_hints} nápověd! Celkem máš {self.cog.scores['total_scores'][user_id]['hints']} nápověd (max 3).")

                        if current_week not in self.cog.scores["weekly_scores"]:
                            self.cog.scores["weekly_scores"][current_week] = {}
                        if user_id not in self.cog.scores["weekly_scores"][current_week]:
                            self.cog.scores["weekly_scores"][current_week][user_id] = {"overall": 0}
                        if quiz_type not in self.cog.scores["weekly_scores"][current_week][user_id]:
                            self.cog.scores["weekly_scores"][current_week][user_id][quiz_type] = 0

                        self.cog.scores["weekly_scores"][current_week][user_id]["overall"] += gained_points
                        self.cog.scores["weekly_scores"][current_week][user_id][quiz_type] += gained_points
                        
                        await channel.send(
                            f'Správně, {message.author.mention}! Získal jsi **{gained_points}** bodů. '
                            f'Celkem tento týden (**{quiz_type.capitalize()}**): **{self.cog.scores["weekly_scores"][current_week][user_id].get(quiz_type, 0)}**.'
                        )
                        answered_correctly_this_round = True
                        unanswered_consecutive_count = 0
                        break
                    else:
                        if message.author.id not in incorrect_responders:
                            await channel.send(f'To není správná odpověď, {message.author.mention}. Zkus to znovu!')
                            incorrect_responders.add(message.author.id)
                except asyncio.TimeoutError:
                    break
            
            if not answered_correctly_this_round:
                unanswered_consecutive_count += 1
                await channel.send('Čas vypršel! Nikdo neodpověděl správně.')
            
            question_count += 1
            self.cog.current_quiz_question_data = None
            
        await channel.send("Kvíz je u konce! Děkuji za účast.")
        self.cog.save_scores()


class QuizCommands:
    """
    Zapouzdřuje stav a příkazy pro kvízový systém.
    """
    def __init__(self, client: discord.Client, tree: app_commands.CommandTree, scores: dict, save_scores: callable, quiz_questions: dict):
        self.client = client
        self.tree = tree
        self.scores = scores
        self.save_scores = save_scores
        self.quiz_questions = quiz_questions
        self.pending_suggestions = {}

        # Stavové proměnné pro kvíz
        self.quiz_active = False
        self.active_quiz_channel = None
        self.current_quiz_question_data = None
        self.last_quiz_start_message_time = 0

        # Načtení a registrace
        self.load_suggestions()
        self.register_commands()
        
        # Registrace úloh a posluchačů událostí
        self.client.loop.create_task(self.check_expired_suggestions())
        # self.client.add_listener(self.on_raw_reaction_add) # Registrace posluchače pro reakce - TENTO ŘÁDEK BYL ODEBRÁN

    def load_suggestions(self):
        """Načte čekající návrhy ze souboru."""
        try:
            with open(QUIZ_SUGGESTIONS_FILE, 'r', encoding='utf-8') as f:
                self.pending_suggestions = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.pending_suggestions = {}

    def save_suggestions(self):
        """Uloží čekající návrhy do souboru."""
        try:
            with open(QUIZ_SUGGESTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pending_suggestions, f, indent=4)
        except IOError as e:
            print(f"Chyba při ukládání návrhů: {e}")

    def save_quiz_questions(self):
        """Uloží aktuální sadu otázek do JSON souboru."""
        try:
            with open(QUIZ_QUESTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.quiz_questions, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Chyba při ukládání kvízových otázek: {e}")

    def get_server_stats(self):
        """Získá statistiky serveru (používá se v příkazech skóre)."""
        user_ants = getattr(self.client, 'user_ants', {})
        total_users_with_ants = len(user_ants)
        total_ant_types_across_all_users = sum(len(ants) for ants in user_ants.values())
        total_score = sum(user_data.get("overall", 0) for user_data in self.scores["total_scores"].values())
        return total_users_with_ants, total_ant_types_across_all_users, total_score

    def check_if_moderator(self, interaction: discord.Interaction) -> bool:
        """Zkontroluje, zda má uživatel roli moderátora nebo administrátora."""
        mod_roles = ["Samec - mod na zkoušku", "Královna - moderátor", "Antkeeper - ADMIN"]
        return any(role.name in mod_roles for role in interaction.user.roles)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Sleduje přidání reakcí na návrhy otázek."""
        print(f"DEBUG: Zpracovávám reakci: {payload.emoji} od uživatele {payload.user_id} na zprávu {payload.message_id}")

        # Ignorujeme reakce od samotného bota
        if payload.user_id == self.client.user.id:
            print("DEBUG: Reakce od samotného bota, ignoruji.")
            return
        
        message_id_str = str(payload.message_id)
        # Zkontrolujeme, zda se jedná o zprávu s čekajícím návrhem
        if message_id_str not in self.pending_suggestions:
            print(f"DEBUG: Zpráva {message_id_str} není v pending_suggestions, ignoruji.")
            return

        # Získáme kanál a zprávu
        channel = self.client.get_channel(payload.channel_id)
        if not channel:
            print(f"DEBUG: Kanál {payload.channel_id} nenalezen, ignoruji.")
            return
        
        try:
            print(f"DEBUG: Načítám zprávu {payload.message_id} z kanálu {channel.name}...")
            # Načteme zprávu, abychom měli aktuální stav reakcí
            message = await channel.fetch_message(payload.message_id)
            print(f"DEBUG: Zpráva načtena. Počet reakcí na zprávě: {len(message.reactions)}")
            
            # Získáme reakci 👍
            reaction = discord.utils.get(message.reactions, emoji="👍")
            print(f"DEBUG: Nalezena 👍 reakce: {reaction}")

            if reaction and str(payload.emoji) == "👍":
                print("DEBUG: Zpracovávám 👍 reakci.")
                # Počítáme unikátní uživatele (bez bota)
                unique_users_count = 0
                async for user in reaction.users():
                    if not user.bot:
                        unique_users_count += 1
                print(f"DEBUG: Unikátní počet uživatelů s 👍 reakcí (bez bota): {unique_users_count}")

                if unique_users_count >= APPROVAL_THRESHOLD:
                    print(f"DEBUG: Návrh {message_id_str} dosáhl prahu schválení ({unique_users_count} >= {APPROVAL_THRESHOLD}). Schvaluji...")
                    # Návrh byl schválen!
                    suggestion = self.pending_suggestions.pop(message_id_str)
                    q_data = suggestion["question_data"]
                    author_id = suggestion["author_id"]
                    
                    # Přidání otázky do slovníku
                    q_type = q_data["type"]
                    q_difficulty = q_data["difficulty"]
                    q_text = q_data["question"]
                    
                    if q_type not in self.quiz_questions:
                        self.quiz_questions[q_type] = {}
                    if q_difficulty not in self.quiz_questions[q_type]:
                        self.quiz_questions[q_type][q_difficulty] = {}
                        
                    self.quiz_questions[q_type][q_difficulty][q_text] = {
                        "answer": q_data["answer"],
                        "points": q_data["points"]
                    }
                    
                    self.save_quiz_questions()
                    self.save_suggestions() # Uložíme aktualizovaný seznam čekajících návrhů
                    
                    # Editace původní zprávy a oznámení autorovi
                    approved_embed = discord.Embed(
                        title="✅ Návrh schválen a přidán do kvízu",
                        description=f"Návrh od uživatele <@{author_id}> byl schválen a přidán do databáze.",
                        color=discord.Color.green()
                    )
                    approved_embed.add_field(name="Otázka", value=q_text, inline=False)
                    await message.edit(embed=approved_embed, view=None)
                    await message.clear_reactions() # Vymažeme reakce, aby se zabránilo dalším interakcím
                    
                    # Oznámení autorovi návrhu
                    author_user = self.client.get_user(author_id)
                    if author_user:
                        await channel.send(f"Gratuluji, {author_user.mention}! Tvůj návrh kvízové otázky byl schválen a přidán do kvízu!")
                    else:
                        print(f"DEBUG: Autor uživatel (ID: {author_id}) nenalezen pro oznámení.")

            elif str(payload.emoji) == "👎":
                print("DEBUG: Zpracovávám 👎 reakci (zatím bez akce).")
                # Pokud někdo přidá 👎, můžeme zvážit zamítnutí nebo jen odstranění reakce
                # Pro jednoduchost zde pouze odstraníme návrh, pokud je dostatek 👎
                # Můžeme přidat logiku pro "zamítnutí" s prahem, ale prozatím jen odstraníme
                # pokud je reakce 👎.
                # Zde je příklad, jak by se dalo zamítnout, pokud by byl nastaven práh pro zamítnutí
                # např. REJECTION_THRESHOLD = 5
                # if reaction and reaction.count >= REJECTION_THRESHOLD:
                #     suggestion = self.pending_suggestions.pop(message_id_str)
                #     author_id = suggestion["author_id"]
                #     rejected_embed = discord.Embed(...)
                #     await message.edit(embed=rejected_embed, view=None)
                #     await message.clear_reactions()
                #     author_user = self.client.get_user(author_id)
                #     if author_user:
                #         await channel.send(f"Je nám líto, {author_user.mention}. Tvůj návrh kvízové otázky byl zamítnut.")
                pass # Prozatím neděláme nic se zápornými reakcemi, jen je zaznamenáváme.

        except discord.NotFound:
            print(f"DEBUG: Zpráva návrhu {message_id_str} nebyla nalezena (pravděpodobně smazána), odstraňuji z pending_suggestions.")
            # Zpráva byla mezitím smazána, odstraníme ji z pending_suggestions
            self.pending_suggestions.pop(message_id_str, None)
            self.save_suggestions()
        except Exception as e:
            print(f"CHYBA: Chyba při zpracování reakce na návrh {message_id_str}: {e}")

    async def check_expired_suggestions(self):
        """Periodicky kontroluje a maže staré neschválené návrhy."""
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            now = datetime.datetime.now(datetime.timezone.utc)
            expiration_delta = datetime.timedelta(days=SUGGESTION_LIFETIME_DAYS)
            
            # Vytvoříme kopii klíčů, abychom mohli bezpečně mazat z původního slovníku
            for message_id_str in list(self.pending_suggestions.keys()):
                suggestion = self.pending_suggestions[message_id_str]
                timestamp = datetime.datetime.fromisoformat(suggestion["timestamp"])
                author_id = suggestion["author_id"] # Získáme ID autora
                
                if now - timestamp > expiration_delta:
                    print(f"DEBUG: Návrh {message_id_str} expiroval. Zpracovávám expiraci.")
                    try:
                        channel_id = suggestion.get("channel_id")
                        if channel_id:
                            channel = self.client.get_channel(channel_id)
                            if channel:
                                message = await channel.fetch_message(int(message_id_str))
                                expired_embed = discord.Embed(
                                    title="❌ Návrh zamítnut (expirován)",
                                    description=f"Návrh od <@{author_id}> nezískal dostatečný počet hlasů v časovém limitu.",
                                    color=discord.Color.red()
                                )
                                await message.edit(embed=expired_embed, view=None)
                                await message.clear_reactions()

                                # Oznámení autorovi návrhu
                                author_user = self.client.get_user(author_id)
                                if author_user:
                                    await channel.send(f"Je nám líto, {author_user.mention}. Tvůj návrh kvízové otázky expiroval a byl zamítnut, protože nezískal dostatek hlasů.")
                                else:
                                    print(f"DEBUG: Autor uživatel (ID: {author_id}) nenalezen pro oznámení o expiraci.")

                        self.pending_suggestions.pop(message_id_str)
                        self.save_suggestions()
                        print(f"DEBUG: Návrh {message_id_str} expiroval a byl zpracován.")

                    except discord.NotFound:
                        print(f"DEBUG: Zpráva návrhu {message_id_str} nebyla nalezena při kontrole expirace, odstraňuji z pending_suggestions.")
                        # Zpráva již neexistuje, jen ji odstraníme z pending_suggestions
                        self.pending_suggestions.pop(message_id_str)
                        self.save_suggestions()
                    except Exception as e:
                        print(f"CHYBA: Chyba při odstraňování expirovaného návrhu {message_id_str}: {e}")

            await asyncio.sleep(60 * 60 * 6) # Kontrola každých 6 hodin

    def register_commands(self):
        """
        Definuje a registruje slash příkazy pro kvíz a skóre.
        """
        @self.tree.command(name="kviz", description="Spustí vědomostní kvíz s výběrem typu a obtížnosti.")
        async def kviz(interaction: discord.Interaction):
            if self.quiz_active:
                await interaction.response.send_message("Kvíz již probíhá! Počkejte prosím, až skončí aktuální kvíz.", ephemeral=True)
                return

            if not self.quiz_questions:
                await interaction.response.send_message("Kvíz nelze spustit, chybí otázky.", ephemeral=True)
                return

            view = QuizSelectionView(self)
            await interaction.response.send_message("Vyberte typ a obtížnost kvízu:", view=view)

        @self.tree.command(name="navrh_otazky", description="Navrhni novou otázku do kvízu (vyžaduje 1000 bodů).")
        async def navrh_otazky(interaction: discord.Interaction):
            user_id = str(interaction.user.id)
            user_score = self.scores.get("total_scores", {}).get(user_id, {}).get("overall", 0)

            if user_score < MIN_SCORE_TO_SUGGEST:
                await interaction.response.send_message(f"Pro navrhování otázek potřebuješ alespoň **{MIN_SCORE_TO_SUGGEST}** bodů. Tvé aktuální skóre je **{user_score}**.", ephemeral=True)
                return
            
            view = SuggestionSetupView(self)
            await interaction.response.send_message("Nejprve vyberte typ a obtížnost pro vaši novou otázku:", view=view, ephemeral=True)

        @self.tree.command(name="napoveda", description="Použije nápovědu k odhalení odpovědi v kvízu. Získává se za 1000 bodů (max 3).")
        async def napoveda(interaction: discord.Interaction):
            user_id = str(interaction.user.id)

            if not self.quiz_active or self.active_quiz_channel != interaction.channel:
                await interaction.response.send_message("Momentálně neprobíhá žádný aktivní kvíz v tomto kanále.", ephemeral=True)
                return

            if self.current_quiz_question_data is None:
                await interaction.response.send_message("Momentálně není aktivní žádná otázka.", ephemeral=True)
                return

            user_data = self.scores["total_scores"].get(user_id, {})
            hints_available = user_data.get("hints", 0)

            if hints_available < 1:
                await interaction.response.send_message("Nemáš žádné nápovědy k dispozici.", ephemeral=True)
                return

            self.scores["total_scores"][user_id]["hints"] -= 1
            self.save_scores()

            question = self.current_quiz_question_data["question"]
            answers = self.current_quiz_question_data["answers"]
            revealed_answer = random.choice(answers)

            await interaction.response.send_message(
                f"{interaction.user.mention}, použil jsi 1 nápovědu! "
                f"Zbývající nápovědy: {self.scores['total_scores'][user_id]['hints']}.\n\n"
                f"**Otázka:** {question}\n"
                f"**Jedna ze správných odpovědí je:** ||{revealed_answer}||"
            )

        @self.tree.command(name="skore", description="Zobrazí tabulku s celkovým skóre a počtem dostupných nápověd.")
        async def skore(interaction: discord.Interaction):
            all_time_scores = self.scores["total_scores"]
            
            if not all_time_scores:
                await interaction.response.send_message("Zatím neexistuje žádné celkové skóre.")
                return

            sorted_scores = sorted(all_time_scores.items(), key=lambda item: item[1].get("overall", 0), reverse=True)
            
            pages = []
            current_page_fields = []
            MAX_FIELDS_PER_PAGE = 5
            medals = {0: "🥇", 1: "🥈", 2: "🥉"}

            for i, (user_id, user_data) in enumerate(sorted_scores):
                user = self.client.get_user(int(user_id))
                user_display_name = user.display_name if user else f"Uživatel (ID: {user_id})"
                rank_prefix = medals.get(i, f"{i + 1}.")
                
                score_details = f"**Celkové Skóre:** {user_data.get('overall', 0)}\n"
                score_details += f"**Nápovědy:** {user_data.get('hints', 0)}\n"
                for quiz_type, score in user_data.items():
                    if quiz_type not in ["overall", "hints"]:
                        score_details += f"- {quiz_type.capitalize()}: {score}\n" 
                
                current_page_fields.append((f"{rank_prefix} {user_display_name}", score_details))

                if len(current_page_fields) == MAX_FIELDS_PER_PAGE or i == len(sorted_scores) - 1:
                    embed = discord.Embed(title=":trophy: Žebříček (Celkové)", description="Nejlepší uživatelé podle celkového skóre.", color=discord.Color.gold())
                    for name, value in current_page_fields:
                        embed.add_field(name=name, value=value, inline=False)
                    
                    _, _, total_overall_score = self.get_server_stats()
                    average_score = total_overall_score / len(self.scores["total_scores"]) if self.scores["total_scores"] else 0
                    embed.add_field(name=":chart_with_upwards_trend: Statistiky serveru", value=f"**Celkem uživatelů v žebříčku:** {len(self.scores['total_scores'])}\n**Průměrné skóre:** {average_score:.2f}", inline=False)
                    embed.set_footer(text=f"Zobrazeno top {len(sorted_scores)}. {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                    pages.append(embed)
                    current_page_fields = []

            view = PaginatorView(pages, interaction)
            await interaction.response.send_message(embed=pages[0], view=view)
            view.message = await interaction.original_response()

        @self.tree.command(name="skore_tyden", description="Zobrazí tabulku se skóre pro aktuální týden.")
        async def skore_tyden(interaction: discord.Interaction):
            current_week = str(datetime.datetime.now(datetime.timezone.utc).isocalendar().week)
            
            if current_week not in self.scores["weekly_scores"] or not self.scores["weekly_scores"][current_week]:
                await interaction.response.send_message(f"Pro tento týden ({current_week}) zatím neexistuje žádné skóre.")
                return

            weekly_scores = self.scores["weekly_scores"][current_week]
            sorted_scores = sorted(weekly_scores.items(), key=lambda item: item[1].get("overall", 0), reverse=True)

            pages = []
            current_page_fields = []
            MAX_FIELDS_PER_PAGE = 5
            medals = {0: "🥇", 1: "🥈", 2: "🥉"}

            for i, (user_id, user_data) in enumerate(sorted_scores):
                user = self.client.get_user(int(user_id))
                user_display_name = user.display_name if user else f"Uživatel (ID: {user_id})"
                rank_prefix = medals.get(i, f"{i + 1}.")
                
                score_details = f"**Týdenní Skóre:** {user_data.get('overall', 0)}\n"
                for quiz_type, score in user_data.items():
                    if quiz_type != "overall":
                        score_details += f"- {quiz_type.capitalize()}: {score}\n" 
                
                current_page_fields.append((f"{rank_prefix} {user_display_name}", score_details))

                if len(current_page_fields) == MAX_FIELDS_PER_PAGE or i == len(sorted_scores) - 1:
                    embed = discord.Embed(title=f":calendar: Týdenní žebříček (Týden {current_week})", description="Nejlepší uživatelé za aktuální týden.", color=discord.Color.blue())
                    for name, value in current_page_fields:
                        embed.add_field(name=name, value=value, inline=False)
                    
                    average_weekly_score = sum(ud.get("overall", 0) for ud in weekly_scores.values()) / len(weekly_scores) if weekly_scores else 0
                    embed.add_field(name=":chart_with_upwards_trend: Statistiky serveru", value=f"**Celkem uživatelů tento týden:** {len(weekly_scores)}\n**Průměrné týdenní skóre:** {average_weekly_score:.2f}", inline=False)
                    embed.set_footer(text=f"Zobrazeno top {len(sorted_scores)}. {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                    pages.append(embed)
                    current_page_fields = []

            view = PaginatorView(pages, interaction)
            await interaction.response.send_message(embed=pages[0], view=view)
            view.message = await interaction.original_response()

        upravit_skore_group = app_commands.Group(name="upravit_skore", description="Správa skóre (jen pro mody).")

        @upravit_skore_group.command(name="nastavit", description="Nastaví celkové skóre uživatele.")
        @app_commands.describe(uzivatel="Uživatel", body="Nová hodnota skóre.")
        async def upravit_skore_nastavit(interaction: discord.Interaction, uzivatel: discord.Member, body: int):
            if not self.check_if_moderator(interaction):
                await interaction.response.send_message("K tomuto příkazu nemáš oprávnění.", ephemeral=True)
                return
            user_id = str(uzivatel.id)
            if user_id not in self.scores["total_scores"]:
                self.scores["total_scores"][user_id] = {"overall": 0, "hints": 0}
            self.scores["total_scores"][user_id]["overall"] = body
            self.save_scores()
            await interaction.response.send_message(f'Celkové skóre uživatele {uzivatel.mention} bylo nastaveno na {body}.')

        @upravit_skore_group.command(name="smazat", description="Vymaže skóre uživatele (nebo všech).")
        @app_commands.describe(uzivatel="Uživatel (nech prázdné pro všechny).")
        async def upravit_skore_smazat(interaction: discord.Interaction, uzivatel: discord.Member = None):
            if not self.check_if_moderator(interaction):
                await interaction.response.send_message("K tomuto příkazu nemáš oprávnění.", ephemeral=True)
                return
            if uzivatel:
                user_id = str(uzivatel.id)
                if user_id in self.scores["total_scores"]:
                    del self.scores["total_scores"][user_id]
                    for week_data in self.scores["weekly_scores"].values():
                        if user_id in week_data:
                            del week_data[user_id]
                    await interaction.response.send_message(f'Skóre uživatele {uzivatel.mention} bylo vymazáno.')
                else:
                    await interaction.response.send_message(f'Uživatel {uzivatel.mention} nemá žádné skóre.', ephemeral=True)
            else:
                self.scores["total_scores"].clear()
                self.scores["weekly_scores"].clear()
                await interaction.response.send_message('Všechna skóre byla vymazána.')
            self.save_scores()
        
        self.tree.add_command(upravit_skore_group)
        
# Tento soubor definuje skupinu příkazů `/statistiky` pro Discord bota.
# Zodpovídá za sběr, zpracování a vizualizaci dat o chovaných mravencích
# na serveru.
#
# Funkce:
# - Příkaz `/statistiky seznamy`: Zobrazuje souhrnné statistiky.
#   Rozlišuje mezi "Aktivními" druhy (počet > 0) a "Celkovými" záznamy (vč. historie 0).
#   Zobrazuje celkové počty kolonií, druhů, top 10 chovatelů a nejčastější druhy.
#   Generuje sloupcový graf pro top 10 druhů (podle počtu kolonií).
#
# - Příkaz `/statistiky historie`: Zobrazuje historický vývoj statistik.
#   Načítá data z `historical_ants_data.json` a generuje časové grafy.
#
# - NOVĚ: Příkaz `/statistiky zobrazit`: Zobrazí detailní profil konkrétního chovatele.
#   Ukazuje pozici v žebříčku (kolonie i druhy), dominantní rod a podíl na serveru.
#   Generuje osobní sloupcový graf chovaných druhů.
#
# Závislosti:
# - Externí knihovny: discord.py, matplotlib
# - Standardní knihovny: io, datetime, json, re, statistics
# - Lokální moduly:
#   - `utils.py`: Pro import třídy PaginatorView pro stránkování.
#   - Data o uživatelích (`user_ants`) a historická data (`historical_ants_data`)
#     jsou získávána z `interaction.client`.

import discord
from discord import app_commands
import matplotlib.pyplot as plt
import io
import datetime
import json
import re
import statistics
from typing import Optional

# Import PaginatorView z utils.py
from utils import PaginatorView

# Tato skupina příkazů bude registrována v main.py
statistiky_group = app_commands.Group(name="statistiky", description="Zobrazuje různé statistiky o chovaných mravencích.")

@statistiky_group.command(name="seznamy", description="Zobrazí statistiky aktivních i historických kolonií a druhů.")
async def statistiky_seznamy(interaction: discord.Interaction):
    # Získání user_ants z client objektu
    user_ants_data = getattr(interaction.client, 'user_ants', {})
    
    if not user_ants_data:
        await interaction.response.send_message("Zatím nejsou k dispozici žádné statistiky, nikdo si nepřidal žádné mravence.", ephemeral=True)
        return

    # Defer odpovědi pro případ, že generování grafu trvá déle
    await interaction.response.defer()

    # --- Inicializace proměnných ---
    total_colonies_server = 0
    
    # Množiny pro unikátní druhy
    unique_species_active = set() # Pouze druhy s počtem > 0
    unique_species_total = set()  # Všechny druhy v seznamu (včetně 0)

    user_with_ants_count = len(user_ants_data)
    
    # Slovníky pro žebříčky
    species_colony_counts = {} # Slovník pro počty kolonií pro každý druh (active only logic naturally applied by summing counts)
    user_colony_counts = {} # Slovník pro celkový počet kolonií pro každého uživatele

    # Seznamy pro statistické výpočty (medián, modus)
    colony_counts_per_user_list = []
    species_counts_active_per_user_list = [] # Pouze aktivní
    species_counts_total_per_user_list = []  # Celkové (vč. historie)

    # --- Iterace přes data ---
    for user_id, ants_data in user_ants_data.items():
        user_total_colonies = 0
        user_active_species_count = 0
        user_total_species_count = 0

        for ant_name, count in ants_data.items():
            # Celkové statistiky serveru
            total_colonies_server += count # Pokud je count 0, nepřičte se nic, což je správně
            
            # Unikátní druhy - Total (historie + aktivní)
            unique_species_total.add(ant_name)
            user_total_species_count += 1

            # Unikátní druhy - Aktivní
            if count > 0:
                unique_species_active.add(ant_name)
                user_active_species_count += 1
            
            # Data pro žebříčky (Top druhy)
            species_colony_counts[ant_name] = species_colony_counts.get(ant_name, 0) + count
            
            # Data pro uživatele
            user_total_colonies += count

        user_colony_counts[user_id] = user_total_colonies
        
        # Přidání do listů pro statistiku
        colony_counts_per_user_list.append(user_total_colonies)
        species_counts_active_per_user_list.append(user_active_species_count)
        species_counts_total_per_user_list.append(user_total_species_count)


    # --- Výpočty průměrů a mediánů ---
    avg_colonies = total_colonies_server / user_with_ants_count if user_with_ants_count > 0 else 0
    
    # Zde počítáme průměr pro AKTIVNÍ druhy, protože to je relevantnější ukazatel "chovatele"
    # Ale do závorky můžeme dát info o celkových seznamech
    avg_species_active = len(unique_species_active) / user_with_ants_count if user_with_ants_count > 0 else 0
    
    # Mediány a Modus pro KOLONIE
    median_colonies_per_user = statistics.median(colony_counts_per_user_list) if colony_counts_per_user_list else 0
    try:
        mode_colonies_per_user = statistics.multimode(colony_counts_per_user_list)
        mode_colonies_per_user_str = str(mode_colonies_per_user[0]) if mode_colonies_per_user else "N/A"
    except statistics.StatisticsError:
        mode_colonies_per_user_str = "N/A"

    # Mediány a Modus pro DRUHY (Počítáme z AKTIVNÍCH, aby to odráželo realitu chovu)
    average_unique_species_per_user = sum(species_counts_active_per_user_list) / user_with_ants_count if user_with_ants_count > 0 else 0
    median_species_per_user = statistics.median(species_counts_active_per_user_list) if species_counts_active_per_user_list else 0
    try:
        mode_species_per_user = statistics.multimode(species_counts_active_per_user_list)
        mode_species_per_user_str = str(mode_species_per_user[0]) if mode_species_per_user else "N/A"
    except statistics.StatisticsError:
        mode_species_per_user_str = "N/A"


    # --- Vytvoření Embedu ---
    embed = discord.Embed(
        title=":bar_chart: Statistiky chovaných mravenců",
        description="Přehled statistik na tomto serveru. Rozlišujeme **Aktivní** (aktuálně chované) a **Celkem** (včetně druhů chovaných v minulosti).",
        color=discord.Color.purple()
    )

    embed.add_field(name="Celkem uživatelů se seznamem", value=str(user_with_ants_count), inline=True)
    embed.add_field(name="Celkem chovaných kolonií", value=str(total_colonies_server), inline=True)
    
    # Upravené pole pro druhy (Aktivní / Celkem)
    embed.add_field(
        name="Unikátních druhů", 
        value=f"Aktivních: {len(unique_species_active)}\nCelkem: {len(unique_species_total)}", 
        inline=True
    )
    
    # Původní pole, které jsi chtěl zachovat (hodnoty jsou vypočteny z aktivních kolonií/druhů)
    embed.add_field(name="Kolonií na uživatele", 
                    value=f"Průměr: {avg_colonies:.2f}\nMedián: {median_colonies_per_user}\nModus: {mode_colonies_per_user_str}", 
                    inline=True)
    embed.add_field(name="Druhů na uživatele (Aktivní)", 
                    value=f"Průměr: {average_unique_species_per_user:.2f}\nMedián: {median_species_per_user}\nModus: {mode_species_per_user_str}", 
                    inline=True)
    
    # --- Top 10 nejčastějších druhů (podle počtu kolonií) ---
    # Zde dává smysl zobrazovat jen ty, co mají kolonie (tedy aktivní > 0 přispívají do sumy)
    top_10_species = []
    if species_colony_counts:
        # Filtrujeme druhy, které mají 0 kolonií (čistě historické), aby nezabíraly místo v topu
        active_species_counts = {k: v for k, v in species_colony_counts.items() if v > 0}
        
        sorted_species_counts = sorted(active_species_counts.items(), key=lambda item: item[1], reverse=True)
        top_10_species = sorted_species_counts[:10]
        
        top_species_text = ""
        for i, (species, count) in enumerate(top_10_species):
            top_species_text += f"{i+1}. {species}: {count} kolonií\n"
        
        if not top_species_text: top_species_text = "Žádné aktivní kolonie."
        embed.add_field(name="Top 10 nejčastějších druhů (aktivní)", value=top_species_text, inline=False)
    else:
        embed.add_field(name="Top 10 nejčastějších druhů", value="Zatím nejsou dostupné žádné druhy.", inline=False)

    # --- Top 10 chovatelů ---
    if user_colony_counts:
        sorted_users_by_colonies = sorted(user_colony_counts.items(), key=lambda item: item[1], reverse=True)
        top_10_users = sorted_users_by_colonies[:10]

        top_users_text = ""
        for i, (user_id, count) in enumerate(top_10_users):
            user = interaction.client.get_user(int(user_id))
            user_display_name = user.display_name if user else f"Neznámý ({user_id})"
            top_users_text += f"{i+1}. {user_display_name}: {count} kolonií\n"
        embed.add_field(name="Top 10 chovatelů (podle počtu kolonií)", value=top_users_text, inline=False)
    else:
        embed.add_field(name="Top 10 chovatelů", value="Zatím nejsou dostupní žádní chovatelé.", inline=False)
        
    # --- Nejméně zastoupené druhy (s 1 nebo 2 koloniemi) ---
    # Zde také filtrujeme jen ty aktivní, protože 0 kolonií je "historie", ne "vzácný chov"
    if species_colony_counts:
        least_common_species = []
        for species, count in species_colony_counts.items():
            if count > 0 and count <= 2: 
                least_common_species.append((species, count))
        
        if least_common_species:
            least_common_species_sorted = sorted(least_common_species, key=lambda item: item[0].lower())
            
            least_common_text = ""
            for species, count in least_common_species_sorted[:10]:
                least_common_text += f"- {species}: {count} kolonií\n"
            embed.add_field(name="Nejméně zastoupené druhy (1-2 kolonie)", value=least_common_text, inline=False)
        else:
            embed.add_field(name="Nejméně zastoupené druhy", value="Všechny aktivní druhy mají více než 2 kolonie.", inline=False)

    # --- Odeslání ---
    await interaction.followup.send(embed=embed)

    # --- Generování grafu (jen pro Top 10 aktivních) ---
    if top_10_species:
        species_names = [item[0] for item in top_10_species]
        species_counts_values = [item[1] for item in top_10_species]

        plt.figure(figsize=(10, 6))
        plt.bar(species_names, species_counts_values, color='skyblue')
        plt.xlabel('Druh mravence')
        plt.ylabel('Počet kolonií')
        plt.title('Top 10 nejčastějších mravenčích druhů (Aktivní)')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        file = discord.File(buf, filename="top_species_chart.png")
        
        original_message = await interaction.original_response()
        embed.set_image(url="attachment://top_species_chart.png")
        await original_message.edit(embed=embed, attachments=[file])


@statistiky_group.command(name="historie", description="Zobrazí historický vývoj statistik (včetně porovnání aktivních vs. historie).")
async def statistiky_historie(interaction: discord.Interaction):
    await interaction.response.defer()

    historical_data = getattr(interaction.client, 'historical_ants_data', {})

    if not historical_data:
        await interaction.followup.send("Zatím nejsou k dispozici žádná historická data.", ephemeral=True)
        return

    sorted_dates = sorted(historical_data.keys())

    # Listy pro osy grafů
    dates = []
    total_colonies_over_time = []
    
    unique_species_active_over_time = [] # NOVÉ: Jen aktivní (>0)
    unique_species_total_over_time = []  # PŮVODNÍ: Vše v seznamu (vč. 0)
    
    users_with_lists_over_time = []
    
    avg_colonies_per_user_over_time = [] 
    med_colonies_per_user_over_time = [] 

    avg_species_per_user_over_time = [] # Zde budeme počítat průměr AKTIVNÍCH
    med_species_per_user_over_time = []

    # Pro Top N druhů
    TOP_N_SPECIES = 5
    overall_species_counts = {}
    
    # 1. Průchod pro zjištění Top N druhů přes celou historii
    for date_str in sorted_dates:
        snapshot = historical_data[date_str]
        for user_id, ants_data in snapshot.items():
            for ant_name, count in ants_data.items():
                if count > 0: # Do top listu počítáme jen ty, co existují (mají kolonie)
                    overall_species_counts[ant_name] = overall_species_counts.get(ant_name, 0) + count
    
    sorted_overall_species = sorted(overall_species_counts.items(), key=lambda item: item[1], reverse=True)
    top_n_species_names = [species for species, count in sorted_overall_species[:TOP_N_SPECIES]]
    top_n_species_historical_counts = {name: [] for name in top_n_species_names}

    # 2. Průchod pro generování časových řad
    for date_str in sorted_dates:
        snapshot = historical_data[date_str]
        
        current_total_colonies = 0
        current_active_species_set = set()
        current_total_species_set = set()
        
        current_users_with_lists = len(snapshot)
        
        snapshot_colony_counts = []
        snapshot_active_species_counts = []
        
        current_snapshot_species_counts = {} # Pro Top N graf
        
        for user_id, ants_data in snapshot.items():
            user_colonies = 0
            user_active_species = 0
            
            for ant_name, count in ants_data.items():
                # Celkem kolonií
                current_total_colonies += count
                
                # Unikátní druhy - Total
                current_total_species_set.add(ant_name)
                
                # Unikátní druhy - Aktivní
                if count > 0:
                    current_active_species_set.add(ant_name)
                    current_snapshot_species_counts[ant_name] = current_snapshot_species_counts.get(ant_name, 0) + count
                    user_active_species += 1
                
                user_colonies += count
            
            snapshot_colony_counts.append(user_colonies)
            snapshot_active_species_counts.append(user_active_species)
        
        # Uložení do listů
        dates.append(date_str)
        total_colonies_over_time.append(current_total_colonies)
        
        unique_species_active_over_time.append(len(current_active_species_set))
        unique_species_total_over_time.append(len(current_total_species_set))
        
        users_with_lists_over_time.append(current_users_with_lists)

        # Průměry a Mediány
        if current_users_with_lists > 0:
            avg_colonies = current_total_colonies / current_users_with_lists
            avg_species = sum(snapshot_active_species_counts) / current_users_with_lists
        else:
            avg_colonies = 0
            avg_species = 0
        
        avg_colonies_per_user_over_time.append(avg_colonies)
        avg_species_per_user_over_time.append(avg_species)
        
        med_colonies = statistics.median(snapshot_colony_counts) if snapshot_colony_counts else 0
        med_species = statistics.median(snapshot_active_species_counts) if snapshot_active_species_counts else 0
        
        med_colonies_per_user_over_time.append(med_colonies)
        med_species_per_user_over_time.append(med_species)

        # Data pro Top N graf
        for species_name in top_n_species_names:
            top_n_species_historical_counts[species_name].append(current_snapshot_species_counts.get(species_name, 0))
        

    # --- Příprava dat pro odeslání ---
    all_embeds = []
    all_files = []

    # --- Graf 1: Celkové počty (Srovnání Aktivní vs Total druhů) ---
    plt.figure(figsize=(12, 7))
    plt.plot(dates, total_colonies_over_time, marker='o', linestyle='-', color='blue', label='Celkem kolonií')
    
    # Dvě křivky pro druhy
    plt.plot(dates, unique_species_total_over_time, marker='x', linestyle='--', color='lightgreen', label='Celkem druhů (vč. historie)')
    plt.plot(dates, unique_species_active_over_time, marker='x', linestyle='-', color='darkgreen', linewidth=2, label='Aktivních druhů')
    
    plt.plot(dates, users_with_lists_over_time, marker='s', linestyle=':', color='red', label='Uživatelů se seznamem')
    
    plt.xlabel('Datum')
    plt.ylabel('Počet')
    plt.title('Vývoj počtu kolonií a druhů (Aktivní vs. Historie)')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    buf1 = io.BytesIO()
    plt.savefig(buf1, format='png')
    buf1.seek(0)
    plt.close()

    file1 = discord.File(buf1, filename="history_total_chart.png")
    all_files.append(file1)

    embed1 = discord.Embed(
        title=":clock1: Historie: Aktivní vs. Celkové počty",
        description="Graf ukazuje rozdíl mezi celkovým počtem zaznamenaných druhů (světle zelená) a aktuálně chovanými druhy (tmavě zelená).",
        color=discord.Color.teal()
    )
    embed1.set_image(url="attachment://history_total_chart.png")
    all_embeds.append(embed1)


    # --- Graf 2: Průměr na uživatele ---
    plt.figure(figsize=(12, 7))
    plt.plot(dates, avg_colonies_per_user_over_time, marker='o', linestyle='-', color='purple', label='Průměr kolonií/uživatel')
    plt.plot(dates, med_colonies_per_user_over_time, marker='x', linestyle='--', color='darkviolet', label='Medián kolonií/uživatel')
    
    plt.plot(dates, avg_species_per_user_over_time, marker='o', linestyle='-', color='orange', label='Průměr (aktivních) druhů/uživatel')
    plt.plot(dates, med_species_per_user_over_time, marker='x', linestyle='--', color='darkorange', label='Medián (aktivních) druhů/uživatel')

    plt.xlabel('Datum')
    plt.ylabel('Počet')
    plt.title('Vývoj průměrného počtu kolonií na uživatele')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    buf2 = io.BytesIO()
    plt.savefig(buf2, format='png')
    buf2.seek(0)
    plt.close()

    file2 = discord.File(buf2, filename="history_avg_chart.png")
    all_files.append(file2)

    embed2 = discord.Embed(
        title=":clock1: Historie: Průměry na uživatele",
        description="Vývoj průměrného počtu kolonií na jednoho chovatele.",
        color=discord.Color.dark_teal()
    )
    embed2.set_image(url="attachment://history_avg_chart.png")
    all_embeds.append(embed2)

    # --- Graf 3: Top N druhů ---
    plt.figure(figsize=(12, 7))
    colors = ['blue', 'green', 'red', 'purple', 'orange']
    markers = ['o', 'x', 's', 'D', '^']

    for i, species_name in enumerate(top_n_species_names):
        plt.plot(dates, top_n_species_historical_counts[species_name], 
                 marker=markers[i % len(markers)], 
                 linestyle='-', 
                 color=colors[i % len(colors)], 
                 label=species_name)

    plt.xlabel('Datum')
    plt.ylabel('Počet kolonií')
    plt.title(f'Vývoj počtu kolonií pro Top {TOP_N_SPECIES} druhů')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()

    buf3 = io.BytesIO()
    plt.savefig(buf3, format='png')
    buf3.seek(0)
    plt.close()

    file3 = discord.File(buf3, filename="history_top_species.png")
    all_files.append(file3)

    embed3 = discord.Embed(
        title=f":clock1: Historie: Top {TOP_N_SPECIES} druhů",
        description=f"Vývoj počtu aktivních kolonií pro nejčastější druhy.",
        color=discord.Color.orange()
    )
    embed3.set_image(url="attachment://history_top_species.png")
    all_embeds.append(embed3)

    await interaction.followup.send(embeds=all_embeds, files=all_files)


@statistiky_group.command(name="zobrazit", description="Zobrazí osobní statistiky chovatele (žebříček, graf, podíl).")
@app_commands.describe(uzivatel="Chovatel, jehož statistiky chceš vidět (volitelné).")
async def statistiky_zobrazit(interaction: discord.Interaction, uzivatel: Optional[discord.Member] = None):
    # Pokud není zadán uživatel, vezmeme toho, kdo příkaz volal
    target_user = uzivatel or interaction.user
    target_id = str(target_user.id)
    
    # Načtení dat
    user_ants_data = getattr(interaction.client, 'user_ants', {})
    
    # Validace, zda má uživatel data
    if target_id not in user_ants_data or not user_ants_data[target_id]:
        msg = "Tento uživatel nemá žádné mravence v seznamu." if uzivatel else "Nemáš žádné mravence v seznamu. Použij `/seznam pridat`."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    await interaction.response.defer()

    # --- 1. Výpočet osobních dat ---
    my_ants = user_ants_data[target_id]
    
    # Filtrujeme pouze aktivní kolonie (> 0) pro většinu statistik
    active_ants = {k: v for k, v in my_ants.items() if v > 0}
    
    my_total_colonies = sum(active_ants.values())
    my_species_count = len(active_ants)
    
    # Dominantní rod (Genus)
    genera_counts = {}
    for species, count in active_ants.items():
        # Předpokládáme formát "Rod druh" (první slovo je rod)
        genus = species.split()[0].capitalize()
        genera_counts[genus] = genera_counts.get(genus, 0) + count
    
    dominant_genus = "N/A"
    if genera_counts:
        dominant_genus = max(genera_counts, key=genera_counts.get)
        dominant_genus_count = genera_counts[dominant_genus]
        dominant_percent = (dominant_genus_count / my_total_colonies) * 100
        dominant_text = f"{dominant_genus} ({dominant_percent:.1f} %)"
    else:
        dominant_text = "Žádné aktivní kolonie"

    # --- 2. Výpočet žebříčků ---
    # Potřebujeme seznam všech uživatelů seřazený podle kritérií
    
    # Seznam (ID, počet_kolonií)
    users_by_colonies = []
    # Seznam (ID, počet_druhů)
    users_by_species = []
    
    server_total_colonies = 0

    for uid, data in user_ants_data.items():
        # Pro žebříčky počítáme jen aktivní
        u_active = {k: v for k, v in data.items() if v > 0}
        u_colonies = sum(u_active.values())
        u_species = len(u_active)
        
        server_total_colonies += u_colonies
        
        users_by_colonies.append((uid, u_colonies))
        users_by_species.append((uid, u_species))
    
    # Seřazení (descending)
    users_by_colonies.sort(key=lambda x: x[1], reverse=True)
    users_by_species.sort(key=lambda x: x[1], reverse=True)
    
    # Nalezení pozice (indexu)
    rank_colonies = next((i + 1 for i, (uid, _) in enumerate(users_by_colonies) if uid == target_id), "-")
    rank_species = next((i + 1 for i, (uid, _) in enumerate(users_by_species) if uid == target_id), "-")
    
    total_users = len(user_ants_data)

    # --- 3. Podíl na serveru ---
    server_share = (my_total_colonies / server_total_colonies * 100) if server_total_colonies > 0 else 0

    # --- 4. Vytvoření Embedu ---
    embed = discord.Embed(
        title=f":bust_in_silhouette: Osobní statistiky: {target_user.display_name}",
        description=f"Detailní přehled chovu uživatele {target_user.mention}.",
        color=target_user.color if target_user.color != discord.Color.default() else discord.Color.blue()
    )
    if target_user.avatar:
        embed.set_thumbnail(url=target_user.avatar.url)

    # Pole: Souhrn
    embed.add_field(name="🏰 Kolonie", value=f"**{my_total_colonies}**", inline=True)
    embed.add_field(name="🐜 Druhy", value=f"**{my_species_count}**", inline=True)
    embed.add_field(name="👑 Dominantní rod", value=dominant_text, inline=True)
    
    # Pole: Žebříček
    rank_text = (
        f"🏆 **#{rank_colonies}** v počtu kolonií\n"
        f"🥈 **#{rank_species}** v počtu druhů\n"
        f"*(z celkem {total_users} chovatelů)*"
    )
    embed.add_field(name="Pozice na serveru", value=rank_text, inline=True)
    
    # Pole: Zajímavost
    embed.add_field(name="Podíl na serveru", value=f"Vlastníš **{server_share:.2f} %**\nvšech mravenců na serveru!", inline=True)

    # --- 5. Generování osobního grafu (Barh - horizontální) ---
    if active_ants:
        # Seřadíme druhy podle počtu (top 10)
        sorted_my_ants = sorted(active_ants.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Data pro graf
        # Pro matplotlib barh musíme data otočit, aby největší byl nahoře (pokud invertujeme osu Y) nebo dole.
        # Matplotlib vykresluje odspodu nahoru. Takže pro Top 1 nahoře musíme pole otočit.
        names = [x[0] for x in sorted_my_ants][::-1]
        values = [x[1] for x in sorted_my_ants][::-1]
        
        plt.figure(figsize=(10, 6))
        
        # Barvy - použijeme barvu uživatele, pokud ji má nastavenou na Discordu
        bar_color = target_user.color.to_rgb() if target_user.color != discord.Color.default() else (0.1, 0.5, 0.7)
        # Matplotlib chce barvy jako (R, G, B) v rozsahu 0-1
        if isinstance(bar_color, tuple) and max(bar_color) > 1:
            bar_color = tuple(c/255 for c in bar_color)
            
        bars = plt.barh(names, values, color=bar_color)
        
        plt.xlabel('Počet kolonií')
        plt.title(f'Top {len(names)} druhů uživatele {target_user.display_name}')
        plt.grid(axis='x', linestyle='--', alpha=0.7)
        
        # Přidání hodnot na konec sloupců
        for bar in bars:
            width = bar.get_width()
            plt.text(width + 0.1, bar.get_y() + bar.get_height()/2, 
                     f'{int(width)}', 
                     ha='left', va='center', fontweight='bold')

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        file = discord.File(buf, filename="user_stats.png")
        embed.set_image(url="attachment://user_stats.png")
        
        await interaction.followup.send(embed=embed, file=file)
    else:
        # Pokud nemá aktivní kolonie (jen historii s 0), pošleme bez grafu
        embed.set_footer(text="Graf nelze vygenerovat (žádné aktivní kolonie).")
        await interaction.followup.send(embed=embed)

# Tento soubor definuje skupinu příkazů `/slovnik` pro Discord bota.
# Zodpovídá za vyhledávání a zobrazování termínů ze slovníku na Formikaristika CZ.
#
# Funkce:
# - Načítá a parsuje HTML stránku slovníku při startu bota nebo na vyžádání.
# - Umožňuje uživateli vyhledávat konkrétní termíny.
# - Zobrazuje vysvětlení termínu a přidružený obrázek, pokud existuje.
# - Nabízí interaktivní výběr z nalezených termínů, pokud je shoda více.
# - **Novinka: Zpracovává odkazy "viz" a přesměrovává na cílové termíny.**
#
# Závislosti:
# - discord.py, requests, beautifulsoup4, difflib (pro fuzzy matching)
# - Lokální moduly: utils.py (pro PaginatorView)

import discord
from discord import app_commands, ui
import requests
from bs4 import BeautifulSoup
import difflib # Pro fuzzy matching
import asyncio # Pro asynchronní operace
import re # Pro regulární výrazy
from typing import List, Dict, Any, Optional

# Import PaginatorView z utils.py
from utils import PaginatorView

# URL slovníku
SLOVNIK_URL = "https://formikaristika.wordpress.com/mravenci/slovnik/"

# Globální proměnná pro uložení dat slovníku
# Bude to seznam slovníků, kde každý slovník reprezentuje řádek tabulky:
# {"term": "Termín", "explanation": "Vysvětlení", "image_url": "URL obrázku"}
dictionary_data: List[Dict[str, str]] = []

async def load_dictionary_data():
    """
    Načte a parsuje data ze slovníku na Formikaristika CZ.
    """
    global dictionary_data
    dictionary_data = [] # Resetujeme data pro případné opětovné načtení

    try:
        response = requests.get(SLOVNIK_URL)
        response.raise_for_status() # Vyvolá HTTPError pro špatné odpovědi (4xx nebo 5xx)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Najdeme tabulku se slovníkem
        # Předpokládáme, že tabulka má strukturu <thead><tr><th>Termín</th><th>Vysvětlivka</th><th>Obrázek</th></tr></thead><tbody>...
        table = soup.find('table')
        if not table:
            print("CHYBA: Tabulka se slovníkem nebyla nalezena na stránce.")
            return

        rows = table.find('tbody').find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 2: # Minimálně termín a vysvětlení
                term = cols[0].get_text(strip=True)
                explanation = cols[1].get_text(strip=True)
                image_url = None

                # Zkusíme najít obrázek ve třetím sloupci, pokud existuje
                if len(cols) >= 3:
                    img_tag = cols[2].find('img')
                    if img_tag and img_tag.get('src'):
                        image_url = img_tag['src']
                    elif cols[2].find('a', href=True): # Někdy je obrázek obalen v <a> tagu
                        img_in_a = cols[2].find('a').find('img')
                        if img_in_a and img_in_a.get('src'):
                            image_url = img_in_a['src']
                        else: # Pokud je odkaz na obrázek přímo v <a> tagu
                            link_to_image = cols[2].find('a', href=True)
                            if link_to_image and ('.jpg' in link_to_image['href'] or '.png' in link_to_image['href']):
                                image_url = link_to_image['href']

                # Přidáme termín bez ohledu na to, zda je to "viz" odkaz,
                # protože ho budeme potřebovat pro přesměrování.
                if term:
                    dictionary_data.append({
                        "term": term,
                        "explanation": explanation,
                        "image_url": image_url
                    })
        print(f"Slovník úspěšně načten. Nalezeno {len(dictionary_data)} termínů.")

    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování slovníku: {e}")
    except Exception as e:
        print(f"Neočekávaná chyba při načítání slovníku: {e}")


class DictionaryResultView(discord.ui.View):
    """
    View pro zobrazení výsledků vyhledávání ve slovníku a interaktivní výběr.
    """
    def __init__(self, terms: List[Dict[str, str]], original_interaction: discord.Interaction, timeout=180):
        super().__init__(timeout=timeout)
        self.terms = terms
        self.original_interaction = original_interaction

        # Vytvoření select menu
        options = []
        for i, term_data in enumerate(self.terms):
            options.append(discord.SelectOption(label=term_data["term"], value=str(i)))
        
        # Omezíme počet možností v select menu na 25
        if len(options) > 25:
            options = options[:25]

        self.select = discord.ui.Select(
            placeholder="Vyberte termín...",
            options=options,
            custom_id="dictionary_term_select"
        )
        self.add_item(self.select)
        self.select.callback = self.on_select_term

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Kontrola, zda může s view interagovat pouze původní uživatel.
        """
        if interaction.user != self.original_interaction.user:
            await interaction.response.send_message("Tuto navigaci může ovládat pouze původní uživatel.", ephemeral=True)
            return False
        return True

    async def on_select_term(self, interaction: discord.Interaction):
        selected_index = int(interaction.data['values'][0])
        selected_term_data = self.terms[selected_index]

        await display_dictionary_term(interaction, selected_term_data, is_redirect=False)
        self.stop() # Zastavíme view po výběru


async def display_dictionary_term(interaction: discord.Interaction, term_data: Dict[str, str], is_redirect: bool = False, original_term: Optional[str] = None):
    """
    Pomocná funkce pro zobrazení detailů termínu ve slovníku.
    """
    # If it's a redirect, the title should be the original searched term.
    # Otherwise, it's the term_data's term.
    embed_title = f"Slovník: {original_term}" if is_redirect and original_term else f"Slovník: {term_data['term']}"
    
    embed_description = term_data['explanation']
    embed_color = discord.Color.blue()
    embed_footer_text = "Zdroj: Formikaristika CZ"

    if is_redirect and original_term:
        # The explanation itself should state the redirection
        embed_description = f"**Vysvětlení tohoto termínu je součástí termínu: {term_data['term']}**\n\n" + embed_description
        embed_color = discord.Color.gold() # Change color for redirection

    embed = discord.Embed(
        title=embed_title,
        description=embed_description,
        color=embed_color
    )
    if term_data['image_url']:
        embed.set_image(url=term_data['image_url'])
        embed_footer_text += f" | Obrázek: {term_data['term']}"
    
    embed.set_footer(text=embed_footer_text)

    # If it's from interaction with DictionaryResultView, edit the message, otherwise send a new one
    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=None)
    else:
        await interaction.followup.send(embed=embed)


# Vytvoření skupiny příkazů pro slovník
slovnik_group = app_commands.Group(name="slovnik", description="Vyhledávání termínů ze slovníku Formikaristika CZ.")

@slovnik_group.command(name="hledat", description="Vyhledá termín ve slovníku Formikaristika CZ.")
@app_commands.describe(term="Termín, který chcete vyhledat.")
async def slovnik_hledat(interaction: discord.Interaction, term: str):
    await interaction.response.defer(ephemeral=False) # Defer odpovědi, protože načítání může trvat

    if not dictionary_data:
        await load_dictionary_data() # Pokusíme se načíst data, pokud ještě nejsou načtená

    if not dictionary_data:
        await interaction.followup.send("Slovník se nepodařilo načíst. Zkuste to prosím později.", ephemeral=True)
        return

    # Normalizujeme vstupní termín pro lepší shodu
    normalized_term = term.lower().strip()

    # Hledání přesné shody
    exact_match = None
    for item in dictionary_data:
        if item["term"].lower() == normalized_term:
            exact_match = item
            break

    if exact_match:
        # Zkontrolujeme, zda se jedná o "viz" odkaz
        viz_match = re.match(r"viz\s+(.+)", exact_match['explanation'].lower())
        if viz_match:
            target_term_raw = viz_match.group(1).strip()
            # Pokusíme se najít cílový termín
            target_term_data = None
            for item in dictionary_data:
                if item["term"].lower() == target_term_raw:
                    target_term_data = item
                    break
            
            if target_term_data:
                # Pass the original term for the title
                await display_dictionary_term(interaction, target_term_data, is_redirect=True, original_term=exact_match['term'])
            else:
                # Pokud cílový termín není nalezen, zobrazíme původní "viz" vysvětlení s upozorněním
                embed = discord.Embed(
                    title=f"Slovník: {exact_match['term']}", # Title is the original term
                    description=f"Vysvětlení tohoto termínu odkazuje na: **{target_term_raw.capitalize()}**.\nBohužel, cílový termín nebyl nalezen ve slovníku.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Zdroj: Formikaristika CZ")
                await interaction.followup.send(embed=embed)
        else:
            await display_dictionary_term(interaction, exact_match)
    else:
        # If no exact match, use fuzzy matching and substring matching
        
        all_terms_raw = [item["term"] for item in dictionary_data]
        
        found_terms_data = []
        found_terms_names = set() # To keep track of names already added

        # 1. Fuzzy matching using difflib
        # cutoff: minimum similarity score (0.0-1.0), 1.0 is exact match
        # Increased n to get more potential matches, lowered cutoff slightly to be more inclusive
        close_matches_difflib = difflib.get_close_matches(normalized_term, all_terms_raw, n=10, cutoff=0.5)
        
        for match_term_str in close_matches_difflib:
            for item in dictionary_data:
                if item["term"] == match_term_str and item["term"] not in found_terms_names:
                    found_terms_data.append(item)
                    found_terms_names.add(item["term"])
                    break
        
        # 2. Substring matching for broader search (e.g., single word)
        # Check if the normalized_term is a substring of any dictionary term (case-insensitive)
        for item in dictionary_data:
            if normalized_term in item["term"].lower() and item["term"] not in found_terms_names:
                found_terms_data.append(item)
                found_terms_names.add(item["term"])
        
        # Sort the results for consistent display and better relevance
        # Prioritize terms that start with the query, then terms that contain the query, then alphabetical.
        found_terms_data.sort(key=lambda x: (
            0 if x["term"].lower().startswith(normalized_term) else # Starts with
            1 if normalized_term in x["term"].lower() else # Contains
            2, # Other matches (from difflib)
            x["term"].lower() # Alphabetical as a tie-breaker
        ))

        if found_terms_data:
            # If there's only one result, or if the first result is a very strong match
            # We can consider the first result to be the "best" if it's a direct match or a very close fuzzy match.
            # For simplicity, if there's only one result after sorting, display it directly.
            # If there are multiple, offer a selection.
            if len(found_terms_data) == 1:
                single_match = found_terms_data[0]
                # Handle "viz" redirect for this single match
                viz_match = re.match(r"viz\s+(.+)", single_match['explanation'].lower())
                if viz_match:
                    target_term_raw = viz_match.group(1).strip()
                    target_term_data = None
                    for item in dictionary_data:
                        if item["term"].lower() == target_term_raw:
                            target_term_data = item
                            break
                    
                    if target_term_data:
                        await display_dictionary_term(interaction, target_term_data, is_redirect=True, original_term=single_match['term'])
                    else:
                        embed = discord.Embed(
                            title=f"Slovník: {single_match['term']} (Nejpodobnější shoda)", # Title is the original term
                            description=f"Vysvětlení tohoto termínu odkazuje na: **{target_term_raw.capitalize()}**.\nBohužel, cílový termín nebyl nalezen ve slovníku.",
                            color=discord.Color.red()
                        )
                        embed.set_footer(text="Zdroj: Formikaristika CZ")
                        await interaction.followup.send(embed=embed)
                else:
                    await display_dictionary_term(interaction, single_match)
            else: # More than one result, offer selection
                # Only show top 5 options in the select menu for clarity
                # We should ensure these are unique terms, which found_terms_names already handles.
                view = DictionaryResultView(found_terms_data[:5], interaction) # Limit to top 5 for select menu
                embed = discord.Embed(
                    title="Nalezeno více podobných termínů",
                    description="Prosím, vyberte termín ze seznamu:",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(f"Termín '{term}' nebyl nalezen ve slovníku. Zkuste prosím jiný dotaz.", ephemeral=True)

@slovnik_group.command(name="seznam", description="Zobrazí abecední seznam všech termínů ve slovníku.")
async def slovnik_seznam(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    if not dictionary_data:
        await load_dictionary_data()

    if not dictionary_data:
        await interaction.followup.send("Slovník se nepodařilo načíst. Zkuste to prosím později.", ephemeral=True)
        return

    # Seřadíme termíny abecedně
    sorted_terms = sorted(dictionary_data, key=lambda x: x["term"].lower())

    # Vytvoříme stránky pro paginátor
    pages: List[discord.Embed] = []
    current_page_description = ""
    terms_per_page = 20 # Můžete upravit počet termínů na stránku

    for i, item in enumerate(sorted_terms):
        current_page_description += f"• **{item['term']}**\n"
        if (i + 1) % terms_per_page == 0 or i == len(sorted_terms) - 1:
            embed = discord.Embed(
                title=":books: Slovník pojmů Formikaristika CZ",
                description=current_page_description,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Zdroj: Formikaristika CZ | Použijte `/slovnik hledat <termín>` pro detailní informace.")
            pages.append(embed)
            current_page_description = ""

    if not pages:
        await interaction.followup.send("Slovník je prázdný.", ephemeral=True)
        return

    view = PaginatorView(pages, interaction)
    # Odešleme první stránku s paginátorem
    message = await interaction.followup.send(embed=pages[0], view=view)
    view.message = message # Nastavíme zprávu pro PaginatorView, aby ji mohl upravovat



import discord
import re

class PaginatorView(discord.ui.View):
    """
    Generická view pro stránkování Discord embedů.
    Umožňuje procházet seznamem embedů pomocí tlačítek.
    """
    def __init__(self, pages: list[discord.Embed], original_interaction: discord.Interaction, timeout=180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.original_interaction = original_interaction
        self.message = None

        self.previous_button = discord.ui.Button(label="Předchozí", style=discord.ButtonStyle.blurple, custom_id="prev_page")
        self.next_button = discord.ui.Button(label="Další", style=discord.ButtonStyle.blurple, custom_id="next_page")
        
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

        self.previous_button.callback = self.go_to_previous_page
        self.next_button.callback = self.go_to_next_page
        
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Kontrola, zda může s paginátorem interagovat pouze původní uživatel.
        """
        if interaction.user != self.original_interaction.user:
            await interaction.response.send_message("Tuto navigaci může ovládat pouze původní uživatel.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        """
        Aktualizuje stav tlačítek (disabled/enabled) a zápatí embedů.
        """
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)
        
        for i, page in enumerate(self.pages):
            footer_text = page.footer.text if page.footer and page.footer.text else ""
            footer_icon_url = page.footer and page.footer.icon_url or None 

            footer_text = re.sub(r" \| Stránka \d+/\d+$", "", footer_text).strip()
            
            page.set_footer(text=f"{footer_text} | Stránka {i + 1}/{len(self.pages)}", 
                            icon_url=footer_icon_url) 

    async def on_timeout(self):
        """
        Zavolá se, když vyprší časový limit pro interakci.
        Odstraní tlačítka ze zprávy.
        """
        if self.message:
            # Zakážeme tlačítka místo jejich odstranění, abychom se vyhnuli chybám
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                # Zpráva byla mezitím smazána, není co dělat
                pass
        # active_paginators je globální v main.py, takže zde ho neřešíme

    async def go_to_previous_page(self, interaction: discord.Interaction):
        # Odložíme odpověď, abychom měli více času
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            # Použijeme edit_original_response, protože jsme odpověď odložili
            await interaction.edit_original_response(embed=self.pages[self.current_page], view=self)

    async def go_to_next_page(self, interaction: discord.Interaction):
        # Odložíme odpověď, abychom měli více času
        await interaction.response.defer()
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            # Použijeme edit_original_response, protože jsme odpověď odložili
            await interaction.edit_original_response(embed=self.pages[self.current_page], view=self)


# soubor pro příkazy skupiny /wishlist
#
# Funkce:
# - Umožňuje uživatelům vytvářet a spravovat seznam přání (wishlist).
# - Přidávání, mazání, zobrazování položek.
# - Zamykání wishlistu.
# - NOVINKA: Interaktivní menu pro přepínání notifikací (zapnuto/vypnuto) a volbu způsobu (DM/Veřejně).
# - UPDATE: Respektování soukromí (ephemeral) při zobrazení zamčeného wishlistu vlastníkem.
#
# Závislosti:
# - discord.py, json
# - seznam_commands (pro validaci druhů)

import discord
from discord import app_commands, ui
import json
import re
from typing import Optional

# Import PaginatorView z utils (aby se nekopíroval kód)
from utils import PaginatorView

# Import funkcí pro validaci a našeptávání ze seznam_commands
# Předpokládáme, že jsou ve složce Příkazy nebo v rootu, uprav podle struktury
try:
    from Příkazy.seznam_commands import validate_species_input, species_autocomplete
except ImportError:
    # Fallback pro případ, že je vše v jedné složce
    from seznam_commands import validate_species_input, species_autocomplete

# --- Globální proměnná pro wishlisty ---
wishlists = {}

# --- Pomocné funkce pro načítání a ukládání ---
def save_wishlists():
    """Uloží aktuální stav wishlistů do souboru wishlists.json."""
    try:
        # Ujistíme se, že složka existuje
        import os
        os.makedirs('Soubory', exist_ok=True)
        
        with open('Soubory/wishlists.json', 'w', encoding='utf-8') as f:
            json.dump(wishlists, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání wishlistů: {e}")

def load_wishlists():
    """Načte wishlisty ze souboru wishlists.json při startu bota."""
    global wishlists
    try:
        with open('Soubory/wishlists.json', 'r', encoding='utf-8') as f:
            wishlists = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Soubor wishlists.json nenalezen nebo je poškozený. Vytvářím novou databázi wishlistů.")
        wishlists = {}

# Načteme data při importu
load_wishlists()

# --- Definice skupiny příkazů ---
wishlist_group = app_commands.Group(name="wishlist", description="Správa tvého seznamu přání (wishlistu).")

# --- Příkazy ---

@wishlist_group.command(name="zobrazit", description="Zobrazí tvůj wishlist nebo wishlist jiného uživatele.")
@app_commands.describe(uzivatel="Uživatel, jehož wishlist chceš zobrazit (volitelné).")
async def wishlist_zobrazit(interaction: discord.Interaction, uzivatel: Optional[discord.Member] = None):
    target_user = uzivatel or interaction.user
    user_id = str(target_user.id)

    user_wishlist = wishlists.get(user_id)
    
    # Zjistíme stav zamčení (pokud wishlist neexistuje, není zamčený)
    is_locked = user_wishlist.get("locked", False) if user_wishlist else False

    # 1. Kontrola přístupu pro cizí uživatele
    if is_locked and target_user != interaction.user:
        await interaction.response.send_message(f"Wishlist uživatele {target_user.mention} je zamčený. 🔒", ephemeral=True)
        return

    # 2. Kontrola prázdného wishlistu
    if not user_wishlist or not user_wishlist.get("items"):
        message = f"Wishlist uživatele {target_user.mention} je prázdný." if uzivatel else "Tvůj wishlist je prázdný. Přidej si něco pomocí `/wishlist pridat`."
        # Pokud je zamčený (a vidí ho vlastník), pošleme jako ephemeral
        await interaction.response.send_message(message, ephemeral=is_locked)
        return

    items = user_wishlist.get("items", [])
    notifications_enabled = user_wishlist.get("notifications", True) # Defaultně True
    notify_pref = user_wishlist.get("notify_pref", "public") # Defaultně veřejně

    # Seřadíme tak, aby nesplněné byly nahoře
    sorted_items = sorted(items, key=lambda x: (x.get('completed', False), x['name'].lower()))

    pages = []
    page_content = ""
    items_on_page = 0
    MAX_ITEMS_PER_PAGE = 15

    for i, item in enumerate(sorted_items):
        name = item.get("name", "Neznámý druh")
        if item.get("completed", False):
            page_content += f"✅ ~~{name}~~\n"
        else:
            page_content += f"🐜 {name}\n"
        
        items_on_page += 1

        if items_on_page == MAX_ITEMS_PER_PAGE or i == len(sorted_items) - 1:
            embed = discord.Embed(
                title=f"Wishlist pro {target_user.display_name}",
                description=page_content,
                color=discord.Color.green()
            )
            if target_user.avatar:
                embed.set_thumbnail(url=target_user.avatar.url)
            
            footer_text = ""
            if is_locked:
                 footer_text += "Zamčeno 🔒 "
            
            # Pokud se dívám na svůj vlastní wishlist, ukážu stav notifikací
            if target_user == interaction.user:
                if notifications_enabled:
                    notif_status = "Zapnuto (DM) 📩" if notify_pref == "dm" else "Zapnuto (Veřejně) 📢"
                else:
                    notif_status = "Vypnuto 🔕"
                
                separator = " | " if footer_text else ""
                footer_text += f"{separator}Notifikace: {notif_status}"

            if footer_text:
                embed.set_footer(text=footer_text)

            pages.append(embed)
            page_content = ""
            items_on_page = 0

    if not pages:
        await interaction.response.send_message("Něco se pokazilo při generování wishlistu.", ephemeral=True)
        return

    view = PaginatorView(pages, interaction)
    # Zde aplikujeme logiku: Pokud je zamčený (is_locked=True), pošleme ephemeral=True (vidí jen autor)
    # Pokud není zamčený, pošleme ephemeral=False (vidí všichni)
    await interaction.response.send_message(embed=pages[0], view=view, ephemeral=is_locked)
    view.message = await interaction.original_response()


@wishlist_group.command(name="pridat", description="Přidá druh do tvého wishlistu. Použij našeptávač!")
@app_commands.describe(species="Název druhu (např. Lasius niger, Camponotus sp.)")
@app_commands.autocomplete(species=species_autocomplete)
async def wishlist_pridat(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    # Validace vstupu pomocí funkce ze seznam_commands
    is_valid, result = await validate_species_input(species)
    
    if not is_valid:
        await interaction.response.send_message(f"⛔ **Chyba v názvu:** {result}", ephemeral=True)
        return
        
    ant_name = result

    if user_id not in wishlists:
        # Defaultně zapnuté notifikace při založení
        wishlists[user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}

    # Zkontrolujeme, zda už druh na wishlistu není
    if any(item['name'] == ant_name for item in wishlists[user_id]["items"]):
        await interaction.response.send_message(f"Druh **{ant_name}** už na tvém wishlistu je.", ephemeral=True)
        return

    wishlists[user_id]["items"].append({"name": ant_name, "completed": False})
    save_wishlists()
    
    # Info o úpravě názvu (pokud se liší)
    msg_prefix = ""
    if species.strip().lower() != ant_name.strip().lower():
        msg_prefix = f"ℹ️ Název upraven na: **{ant_name}**\n"
        
    await interaction.response.send_message(f"{msg_prefix}Přidáno **{ant_name}** do tvého wishlistu! ✨")


@wishlist_group.command(name="splneno", description="Označí druh na tvém wishlistu jako splněný.")
@app_commands.describe(species="Název druhu")
@app_commands.autocomplete(species=species_autocomplete)
async def wishlist_splneno(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    # Pro smazání zkusíme najít přesnou shodu nebo validovat vstup
    target_name = species
    is_valid, validated_name = await validate_species_input(species)
    if is_valid:
        target_name = validated_name

    if user_id not in wishlists or not wishlists[user_id].get("items"):
        await interaction.response.send_message("Tvůj wishlist je prázdný.", ephemeral=True)
        return

    item_found = False
    for item in wishlists[user_id]["items"]:
        # Porovnáváme validovaný název nebo zadaný (lowercase)
        if item['name'].lower() == target_name.lower() or item['name'].lower() == species.lower():
            if item.get('completed', False):
                 await interaction.response.send_message(f"Druh **{item['name']}** je již označen jako splněný.", ephemeral=True)
                 return
            item['completed'] = True
            target_name = item['name'] # Pro správný výpis ve zprávě
            item_found = True
            break

    if item_found:
        save_wishlists()
        await interaction.response.send_message(f"Gratuluji! 🎉 Druh **{target_name}** byl označen jako splněný na tvém wishlistu. ✅")
    else:
        await interaction.response.send_message(f"Druh **{species}** (ani jako **{target_name}**) nebyl nalezen na tvém wishlistu.", ephemeral=True)


@wishlist_group.command(name="zamek", description="Přepne viditelnost tvého wishlistu (zamkne/odemkne).")
async def wishlist_zamek(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id not in wishlists:
        wishlists[user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}

    # Přepnutí stavu zámku
    current_state = wishlists[user_id].get("locked", False)
    new_state = not current_state
    wishlists[user_id]["locked"] = new_state
    
    save_wishlists()

    if new_state:
        await interaction.response.send_message("Tvůj wishlist byl úspěšně zamčen. 🔒 Ostatní ho nyní neuvidí.", ephemeral=True)
    else:
        await interaction.response.send_message("Tvůj wishlist byl úspěšně odemčen. 🔓 Ostatní ho nyní mohou vidět.", ephemeral=True)


@wishlist_group.command(name="odebrat", description="Odebere druh z tvého wishlistu.")
@app_commands.describe(species="Název druhu")
@app_commands.autocomplete(species=species_autocomplete)
async def wishlist_odebrat(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    # Validace pro lepší shodu při mazání
    target_name = species
    is_valid, validated_name = await validate_species_input(species)
    if is_valid:
        target_name = validated_name

    if user_id not in wishlists or not wishlists[user_id].get("items"):
        await interaction.response.send_message("Tvůj wishlist je prázdný.", ephemeral=True)
        return

    original_item_count = len(wishlists[user_id]["items"])
    
    # Filtrujeme (mažeme)
    wishlists[user_id]["items"] = [
        item for item in wishlists[user_id]["items"] 
        if item['name'].lower() != target_name.lower() and item['name'].lower() != species.lower()
    ]

    if len(wishlists[user_id]["items"]) < original_item_count:
        save_wishlists()
        # Pokud jsme smazali podle validovaného jména, vypíšeme to hezky, jinak původní vstup
        display_name = target_name if is_valid else species
        await interaction.response.send_message(f"Druh **{display_name}** byl odebrán z tvého wishlistu.")
    else:
        await interaction.response.send_message(f"Druh **{species}** nebyl nalezen na tvém wishlistu.", ephemeral=True)


# --- Interaktivní Menu pro nastavení Notifikací ---

class WishlistNotifyPreferenceView(ui.View):
    def __init__(self, user_id: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        user_data = wishlists.get(self.user_id, {})
        notifications_enabled = user_data.get("notifications", True)
        notify_pref = user_data.get("notify_pref", "public")

        if notifications_enabled:
            btn_toggle = ui.Button(label="Vypnout upozornění", style=discord.ButtonStyle.danger, emoji="🔕", custom_id="toggle_notif")
        else:
            btn_toggle = ui.Button(label="Zapnout upozornění", style=discord.ButtonStyle.success, emoji="🔔", custom_id="toggle_notif")
        btn_toggle.callback = self.toggle_notif_callback

        if notify_pref == "dm":
            btn_pref = ui.Button(label="Změnit na Veřejné", style=discord.ButtonStyle.secondary, emoji="📢", custom_id="toggle_pref", disabled=not notifications_enabled)
        else:
            btn_pref = ui.Button(label="Změnit na Soukromé (DM)", style=discord.ButtonStyle.primary, emoji="📩", custom_id="toggle_pref", disabled=not notifications_enabled)
        btn_pref.callback = self.toggle_pref_callback

        self.add_item(btn_toggle)
        self.add_item(btn_pref)

    def get_status_message(self):
        user_data = wishlists.get(self.user_id, {})
        notifications_enabled = user_data.get("notifications", True)
        notify_pref = user_data.get("notify_pref", "public")
        
        status = "ZAPNUTO 🔔" if notifications_enabled else "VYPNUTO 🔕"
        pref = "Soukromé zprávy (DM) 📩" if notify_pref == "dm" else "Veřejně do kanálu #boti 📢"
        
        return f"**Nastavení upozornění na tvůj wishlist:**\n\nStav notifikací: **{status}**\nTyp upozornění: **{pref}**\n\n*Vyber si pomocí tlačítek, zda chceš dostávat upozornění a jakým způsobem.*"

    async def toggle_notif_callback(self, interaction: discord.Interaction):
        if self.user_id not in wishlists:
            wishlists[self.user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}
        
        current_state = wishlists[self.user_id].get("notifications", True)
        wishlists[self.user_id]["notifications"] = not current_state
        save_wishlists()
        
        self.update_buttons()
        await interaction.response.edit_message(content=self.get_status_message(), view=self)

    async def toggle_pref_callback(self, interaction: discord.Interaction):
        if self.user_id not in wishlists:
            wishlists[self.user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}
        
        current_pref = wishlists[self.user_id].get("notify_pref", "public")
        wishlists[self.user_id]["notify_pref"] = "dm" if current_pref == "public" else "public"
        save_wishlists()
        
        self.update_buttons()
        await interaction.response.edit_message(content=self.get_status_message(), view=self)


@wishlist_group.command(name="notifikace", description="Nastavení upozornění, když někdo nabídne druh z tvého wishlistu.")
async def wishlist_notifikace(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id not in wishlists:
        wishlists[user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}
        save_wishlists()

    view = WishlistNotifyPreferenceView(user_id)
    await interaction.response.send_message(
        content=view.get_status_message(),
        view=view,
        ephemeral=True
    )
        
        
        
# Tento soubor definuje skupinu příkazů `/patch_notes` pro Discord bota.
# Zodpovídá za zobrazování historie změn a aktualizací bota.
#
# Funkce:
# - Načítá data o patchích z JSON souboru.
# - Zobrazuje jednotlivé patche v embed zprávách s podporou stránkování.
#
# Závislosti:
# - discord.py
# - Standardní knihovny: json, datetime
# - Lokální moduly: utils.py (pro PaginatorView)

import discord
from discord import app_commands
import json
import datetime
from typing import List, Dict, Any

# Import PaginatorView z utils.py
from utils import PaginatorView

# Soubor, kde budou uloženy poznámky k patchům
PATCH_NOTES_FILE = 'patch_notes.json'

# Globální proměnná pro uložení dat patchů
# Bude to seznam slovníků, kde každý slovník reprezentuje jeden patch:
# {"version": "1.0.0", "changes": ["Změna 1", "Změna 2"], "image_url": "URL_obrazku"}
patch_notes_data: List[Dict[str, Any]] = []

def load_patch_notes():
    """Načte poznámky k patchům z JSON souboru."""
    global patch_notes_data
    try:
        with open(PATCH_NOTES_FILE, 'r', encoding='utf-8') as f:
            patch_notes_data = json.load(f)
            # Pořadí v JSON souboru nyní určuje pořadí zobrazení.
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"CHYBA: Soubor '{PATCH_NOTES_FILE}' nenalezen nebo je poškozený. Vytvářím prázdný seznam patchů.")
        patch_notes_data = []

# Načteme patche hned při importu modulu
load_patch_notes()

# Vytvoření skupiny příkazů pro patch notes
patch_notes_group = app_commands.Group(name="patch_notes", description="Zobrazuje historii změn a aktualizací bota.")

@patch_notes_group.command(name="zobrazit", description="Zobrazí historii změn bota.")
async def patch_notes_zobrazit(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False) # Odložíme odpověď

    if not patch_notes_data:
        await interaction.followup.send("Zatím nejsou k dispozici žádné poznámky k patchům.", ephemeral=True)
        return

    pages: List[discord.Embed] = []

    for patch in patch_notes_data:
        version = patch.get("version", "Neznámá verze")
        date_str = patch.get("date", "Neznámé datum") # Získáme datum string
        changes = patch.get("changes", [])
        image_url = patch.get("image_url")
        
        formatted_date = date_str # Výchozí hodnota je původní string

        # NOVINKA: Explicitní kontrola pro "N/A" nebo "Neznámé datum"
        if date_str.lower() != "n/a" and date_str != "Neznámé datum":
            try:
                # Převedeme datum do čitelného formátu, pokud to není "N/A"
                date_obj = datetime.datetime.fromisoformat(date_str)
                formatted_date = date_obj.strftime("%d.%m.%Y")
            except ValueError:
                # Pokud se parsování nezdaří (např. špatný formát, ale ne "N/A"),
                # ponecháme formatted_date jako původní string
                pass 
        
        embed = discord.Embed(
            title=f"Patch Notes: Verze {version}",
            description=f"Datum: {formatted_date}\n\n**Změny:**", # Zobrazení data (bude "N/A" nebo formátované datum)
            color=discord.Color.blue()
        )

        if changes:
            changes_text = "\n".join([f"• {change}" for change in changes])
            embed.add_field(name="\u200b", value=changes_text, inline=False)
        else:
            embed.add_field(name="\u200b", value="Žádné konkrétní změny k zobrazení.", inline=False)

        if image_url:
            embed.set_image(url=image_url)
        
        embed.set_footer(text="FormiBot Patch Notes")
        pages.append(embed)

    if not pages:
        await interaction.followup.send("Něco se pokazilo při generování patch notes.", ephemeral=True)
        return

    view = PaginatorView(pages, interaction)
    message = await interaction.followup.send(embed=pages[0], view=view)
    view.message = message


# --- Instrukce pro integraci do hlavního souboru (main.py) ---
# 1. Ulož tento soubor jako `patch_notes_commands.py` do stejné složky jako `main.py`.
# 2. V `main.py` přidej na začátek souboru import:
#    `from patch_notes_commands import patch_notes_group, load_patch_notes`
# 3. V `main.py` uvnitř funkce `on_ready()` (za `await load_dictionary_data()`) přidej registraci skupiny příkazů:
#    `tree.add_command(patch_notes_group)`
# 4. Také v `on_ready()` zavolej `load_patch_notes()` pro načtení dat při startu bota.
# 5. Vytvoř soubor `patch_notes.json` ve stejné složce jako `main.py` a vlož do něj níže uvedený obsah.



# Tento soubor definuje skupinu příkazů `/fauna` pro Discord bota.
# Umožňuje uživatelům vyhledávat inzeráty na Faunaportal.cz a iFauna.cz
# a zobrazuje až 4 nejrelevantnější výsledky s odkazy a krátkými popisy.
#
# Funkce:
# - `search_faunaportal`: Prohledává Faunaportal.cz pro daný dotaz a extrahuje inzeráty.
# - `search_ifauna`: Prohledává iFauna.cz pro daný dotaz a extrahuje inzeráty.
# - Příkaz `/fauna hledat`: Spustí vyhledávání na obou portálech a zobrazí výsledky.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, beautifulsoup4.
# - Standardní knihovny: urllib.parse.

import discord
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import urllib.parse
import asyncio
import json # Přidáno pro zpracování JSON-LD dat

# Vytvoření skupiny příkazů pro faunu
fauna_group = app_commands.Group(name="fauna", description="Vyhledávání inzerátů na prodej mravenců a hmyzu.")

# Změněno z 'async def' na 'def', protože tato funkce bude spuštěna v samostatném vlákně pomocí asyncio.to_thread
def search_faunaportal(query: str) -> list[dict]:
    """
    Prohledá Faunaportal.cz pro daný dotaz a vrátí seznam inzerátů.
    Každý inzerát obsahuje 'title', 'url' a 'description'.
    """
    base_url = "https://www.faunaportal.cz/inzeraty"
    search_url = f"{base_url}?name={urllib.parse.quote_plus(query)}"
    results = []

    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Faunaportal.cz používá divy s class 'chakra-stack css-1l48e7e' pro jednotlivé inzeráty
        ad_listings = soup.find_all('div', class_='chakra-stack css-1l48e7e')

        for ad in ad_listings:
            link_tag = ad.find('a', class_='chakra-linkbox__overlay css-1v8v44t')
            title_tag = ad.find('h3', class_='chakra-heading css-15q0f1v')
            # Hledáme popis, který by mohl být v divu s textem nebo p tagu
            description_tag = ad.find('p', class_='chakra-text css-1g9t404') # Nová třída pro popis

            if link_tag and title_tag:
                title = title_tag.get_text(strip=True)
                relative_url = link_tag.get('href')
                full_url = urllib.parse.urljoin("https://www.faunaportal.cz/", relative_url)
                description = description_tag.get_text(strip=True)[:200] + "..." if description_tag else "Popis není k dispozici."
                results.append({"title": title, "url": full_url, "description": description})
                if len(results) >= 4: # Omezíme na 4 výsledky
                    break
    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování z Faunaportal.cz pro dotaz '{query}': {e}")
    except Exception as e:
        print(f"Neočekávaná chyba při parsování Faunaportal.cz: {e}")
    
    return results

# Změněno z 'async def' na 'def', protože tato funkce bude spuštěna v samostatném vlákně pomocí asyncio.to_thread
def search_ifauna(query: str) -> list[dict]:
    """
    Prohledá iFauna.cz pro daný dotaz a vrátí seznam inzerátů.
    Každý inzerát obsahuje 'title', 'url' a 'description'.
    """
    base_url = "https://www.ifauna.cz/inzerce/"
    search_url = f"{base_url}?hledat={urllib.parse.quote_plus(query)}"
    results = []

    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # iFauna.cz používá JSON-LD data ve script tagu pro strukturovaná data
        # To je mnohem spolehlivější než HTML scraping pro inzeráty.
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'CollectionPage' and data.get('mainEntity', {}).get('@type') == 'ItemList':
                    for item_list_element in data['mainEntity'].get('itemListElement', []):
                        item = item_list_element.get('item', {})
                        if item.get('@type') == 'Product' and item.get('name') and item.get('url'):
                            title = item['name']
                            url = item['url']
                            description = item.get('description', 'Popis není k dispozici.')[:200] + "..."
                            results.append({"title": title, "url": url, "description": description})
                            if len(results) >= 4: # Omezíme na 4 výsledky
                                break
                    if len(results) >= 4:
                        break
            except json.JSONDecodeError:
                continue # Přeskočíme, pokud JSON není platný
        
        # Pokud se nic nenašlo z JSON-LD, zkusíme klasický scraping jako fallback
        if not results:
            # Hledáme divy s class 'if-advertising-item'
            ad_listings = soup.find_all('div', class_='if-advertising-item')
            for ad in ad_listings:
                link_tag = ad.find('a', class_='if-advertising-item__link')
                title_tag = ad.find('h3', class_='if-advertising-item__title')
                description_tag = ad.find('div', class_='if-advertising-item__text') # Hledáme popis

                if link_tag and title_tag:
                    title = title_tag.get_text(strip=True)
                    full_url = link_tag.get('href')
                    description = description_tag.get_text(strip=True)[:200] + "..." if description_tag else "Popis není k dispozici."
                    results.append({"title": title, "url": full_url, "description": description})
                    if len(results) >= 4: # Omezíme na 4 výsledky
                        break

    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování z iFauna.cz pro dotaz '{query}': {e}")
    except Exception as e:
        print(f"Neočekávaná chyba při parsování iFauna.cz: {e}")
    
    return results


@fauna_group.command(name="hledat", description="Vyhledá inzeráty na Faunaportal.cz a iFauna.cz.")
@app_commands.describe(dotaz="Co chceš vyhledat? (např. 'Camponotus ligniperda', 'mravenci')")
async def fauna_hledat(interaction: discord.Interaction, dotaz: str):
    """
    Vyhledá inzeráty na Faunaportal.cz a iFauna.cz a zobrazí až 4 výsledky z každého webu.
    """
    await interaction.response.defer() # Odložíme odpověď, protože vyhledávání může chvíli trvat

    # Voláme synchronní funkce search_faunaportal a search_ifauna v samostatném vlákně
    faunaportal_results = await asyncio.to_thread(search_faunaportal, dotaz)
    ifauna_results = await asyncio.to_thread(search_ifauna, dotaz)

    embed = discord.Embed(
        title=f"Výsledky vyhledávání inzerátů pro: \"{dotaz}\"",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Hledáno na Faunaportal.cz a iFauna.cz")

    # Faunaportal.cz výsledky
    if faunaportal_results:
        faunaportal_text = ""
        for i, ad in enumerate(faunaportal_results):
            faunaportal_text += f"**{i+1}. [{ad['title']}]({ad['url']})**\n{ad['description']}\n"
        embed.add_field(name="Faunaportal.cz", value=faunaportal_text, inline=False)
    else:
        embed.add_field(name="Faunaportal.cz", value="Žádné výsledky nalezeny.", inline=False)

    # iFauna.cz výsledky
    if ifauna_results:
        ifauna_text = ""
        for i, ad in enumerate(ifauna_results):
            ifauna_text += f"**{i+1}. [{ad['title']}]({ad['url']})**\n{ad['description']}\n"
        embed.add_field(name="iFauna.cz", value=ifauna_text, inline=False)
    else:
        embed.add_field(name="iFauna.cz", value="Žádné výsledky nalezeny.", inline=False)

    await interaction.followup.send(embed=embed)


# Tento soubor definuje příkaz `/map` pro Discord bota.
# Zobrazuje mapy rozšíření mravenců z AntMaps a poskytuje užitečné odkazy
# na myrmekologické databáze (AntWeb, AntWiki, AntCat, iNaturalist).
#
# Funkce:
# - Příkaz `/map`:
#   - Pokud je parametrem "help", zobrazí nápovědu.
#   - Pokud je zadán pouze rod, zobrazí mapu diverzity rodu.
#   - Pokud je zadán rod i druh, zobrazí mapu rozšíření konkrétního druhu.
#
# Závislosti:
# - discord.py
# - urllib.parse (pro bezpečné formátování URL)

import discord
from discord import app_commands
import urllib.parse

@app_commands.command(name="map", description="Zobrazí mapu rozšíření a odkazy pro daný rod nebo druh mravence.")
@app_commands.describe(rod="Rod mravence (nebo napiš 'help' pro nápovědu)", druh="Druh mravence (nepovinné)")
async def map_command(interaction: discord.Interaction, rod: str, druh: str = None):
    # DŮLEŽITÉ: Odložíme odpověď, aby interakce nevypršela po 3 sekundách (řeší chybu 10062)
    # Protože používáme defer(), musíme dále používat interaction.followup.send místo response.send_message
    await interaction.response.defer()

    # Ošetření vstupu - odstranění mezer
    rod = rod.strip()
    if druh:
        druh = druh.strip()

    # 1. Varianta: Nápověda (rod == "help")
    if rod.lower() == "help":
        embed = discord.Embed(
            description="*Je nutné napsat Rod a druh ve správném formátu a bez chyb.*",
            color=discord.Color.blue()
        )
        # Použijeme obrázek z tvého zadání
        embed.set_image(url="https://cdn.discordapp.com/attachments/661985293834125342/808308254081417227/acz_map_command.png")
        
        # Používáme followup, protože jsme již zavolali defer()
        await interaction.followup.send(embed=embed)
        return

    # Formátování názvů pro URL (Rod s velkým, druh s malým)
    rod_fmt = rod.capitalize()
    druh_fmt = druh.lower() if druh else None
    
    # Příprava URL (safe encoding)
    rod_safe = urllib.parse.quote(rod_fmt)
    
    # 2. Varianta: Zobrazení pouze rodu (druh není zadán)
    if not druh_fmt:
        # URL odkazy pro rod
        antmaps_url = f"https://antmaps.org/?mode=diversity&genus={rod_safe}"
        antweb_url = f"https://www.antweb.org/description.do?rank=genus&genus={rod_safe}&project=worldants"
        antwiki_url = f"https://antwiki.org/wiki/{rod_safe}"
        # AntCat URL vyžaduje specifické kódování, použijeme formát ze zadání
        antcat_url = f"http://www.antcat.org/catalog/search?utf8=%E2%9C%93&st=m&qq={rod_safe}&commit=Go"
        inaturalist_url = f"https://www.inaturalist.org/taxa/{rod_safe}"
        
        # API pro obrázek mapy (ze zadání)
        image_url = f"https://api.antapi.org/antmaps/{rod_safe}.png"

        description = (
            f":microscope: [AntWeb](<{antweb_url}>) "
            f":books: [AntWiki](<{antwiki_url}>) "
            f":white_check_mark: [AntCat](<{antcat_url}>) "
            f":bird: [iNaturalist](<{inaturalist_url}>)"
        )

        embed = discord.Embed(
            title=rod_fmt,
            url=antmaps_url,
            description=description,
            color=discord.Color.green()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Data: AntMaps.org, Image: AntApi.org")

        # Používáme followup
        await interaction.followup.send(embed=embed)

    # 3. Varianta: Zobrazení rodu a druhu
    else:
        druh_safe = urllib.parse.quote(druh_fmt)
        full_name_safe = urllib.parse.quote(f"{rod_fmt} {druh_fmt}")
        
        # URL odkazy pro druh
        antmaps_url = f"https://antmaps.org/?mode=species&species={rod_safe}.{druh_safe}"
        antweb_url = f"https://www.antweb.org/description.do?rank=species&genus={rod_safe}&species={druh_safe}&project=worldants"
        antwiki_url = f"https://antwiki.org/wiki/{rod_safe}_{druh_safe}"
        antcat_url = f"http://www.antcat.org/catalog/search?utf8=%E2%9C%93&st=m&qq={full_name_safe}&commit=Go"
        inaturalist_url = f"https://www.inaturalist.org/taxa/{full_name_safe}"
        
        # API pro obrázek mapy (ze zadání)
        image_url = f"https://api.antapi.org/antmaps/{rod_safe}/{druh_safe}.png"

        description = (
            f":microscope: [AntWeb](<{antweb_url}>) "
            f":books: [AntWiki](<{antwiki_url}>) "
            f":white_check_mark: [AntCat](<{antcat_url}>) "
            f":bird: [iNaturalist](<{inaturalist_url}>)"
        )

        embed = discord.Embed(
            title=f"{rod_fmt} {druh_fmt}",
            url=antmaps_url,
            description=description,
            color=discord.Color.green()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Data: AntMaps.org, Image: AntApi.org")

        # Používáme followup
        await interaction.followup.send(embed=embed)
        
        
        
# Tento soubor spravuje příkazy pro seznam chovaných druhů mravenců (/seznam).
#
# Funkce:
# - Spravuje databázi `user_ants` (načítání/ukládání JSON).
# - Načítá databázi platných druhů `bolton_species.json` (slovník s detaily) pro validaci a našeptávání.
# - Definuje skupinu příkazů `/seznam` (pridat, smazat, zobrazit, hledat...).
# - Implementuje našeptávání (autocomplete) pro názvy druhů.
# - Implementuje validaci pro otevřenou nomenklaturu (sp., cf., nr.) a opravu překlepů.
# - Podporuje obchodní názvy v uvozovkách (např. 'Odontomachus sp. "candy"').
# - Ponechává AntCat API jako záložní validaci.
# - Podpora pro stav "0 kolonií" (historie/minulost).
# - Vylepšené řazení v /seznam zobrazit (aktivní nahoře).
# - /seznam odebrat_pocet nyní při dosažení 0 nemaže záznam, ale přesouvá do historie.
# - Odesílá upozornění do mod-chatu, pokud uživatel přidá druh, který ještě nikdo na serveru nemá.
#
# Závislosti:
# - discord.py, requests, json, utils (PaginatorView), difflib, re

import discord
from discord import app_commands
import json
import requests
from utils import PaginatorView
import difflib # Pro vyhledávání podobných řetězců (fuzzy matching)
import re # Pro regulární výrazy (zpracování obchodních názvů)

# --- Globální proměnné pro data ---
user_ants = {}
species_database = {} # Slovník: {"Rod druh": {"author": "...", ...}}
species_names = []    # Pouze seznam klíčů (názvů) pro rychlé našeptávání
unique_genera = set() # Množina unikátních rodů pro rychlou validaci a opravy

# --- Pomocné funkce pro správu dat ---
def save_user_ants():
    """Uloží aktuální stav chovaných mravenců do souboru user_ants.json."""
    try:
        with open('user_ants.json', 'w', encoding='utf-8') as f:
            json.dump(user_ants, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání mravenčích druhů: {e}")

def load_user_ants():
    """Načte chované mravence ze souboru user_ants.json."""
    global user_ants
    try:
        with open('user_ants.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            user_ants.clear()
            user_ants.update(data)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Soubor user_ants.json nenalezen nebo je poškozený. Vytvářím novou databázi mravenců.")
        user_ants.clear()

def load_species_database():
    """Načte databázi druhů a připraví seznam jmen a rodů."""
    global species_database, species_names, unique_genera
    try:
        with open('Soubory/bolton_species.json', 'r', encoding='utf-8') as f:
            species_database = json.load(f)
            # Vytvoříme si seznam klíčů pro difflib a autocomplete
            species_names = list(species_database.keys())
            # Vytvoříme množinu unikátních rodů (první slovo z názvu druhu)
            unique_genera = {name.split()[0] for name in species_names if name}
        print(f"Načteno {len(species_names)} druhů a {len(unique_genera)} unikátních rodů do databáze.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("POZOR: Soubor bolton_species.json nenalezen. Našeptávání a lokální validace nebude fungovat optimálně.")
        species_database = {}
        species_names = []
        unique_genera = set()

# Načteme data hned při importu modulu
load_species_database()

# --- Pomocné funkce pro mravence a validaci ---

async def species_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """
    Funkce pro našeptávání druhů v Discordu.
    Filtruje seznam `species_names` podle toho, co uživatel píše.
    """
    if not current:
        # Pokud uživatel nic nenapsal, vrátíme prvních 10
        return [app_commands.Choice(name=sp, value=sp) for sp in species_names[:10]]
    
    current_lower = current.lower()
    # Filtrování: Hledáme v předpřipraveném seznamu jmen
    filtered = [sp for sp in species_names if current_lower in sp.lower()]
    
    # Discord limituje našeptávání na 25 položek
    return [app_commands.Choice(name=sp, value=sp) for sp in filtered[:10]]

async def validate_species_input(input_species: str) -> tuple[bool, str]:
    """
    Validuje zadaný název druhu. Podporuje i obchodní názvy v uvozovkách.
    Vrací: (is_valid, formatted_name_or_error_message)
    """
    # --- 0. Separace obchodního názvu (v uvozovkách) ---
    trade_name_suffix = ""
    clean_species_input = input_species.strip()
    
    # Regex hledá text v uvozovkách na konci řetězce
    match = re.search(r'\s*(["“].+?["”])\s*$', clean_species_input)
    if match:
        trade_name_suffix = " " + match.group(1) # Uložíme si "nazev" s mezerou na začátku
        clean_species_input = clean_species_input[:match.start()].strip() # Zbytek je vědecký název

    parts = clean_species_input.split()
    
    if len(parts) < 2:
        return False, "Název musí obsahovat alespoň Rod a Druh (např. Lasius niger) nebo Rod sp."

    genus = parts[0].capitalize()
    species_part = parts[1].lower()
    
    final_scientific_name = ""
    is_valid = False
    error_msg = ""

    # --- 1. Kontrola otevřené nomenklatury (sp., cf., nr.) ---
    if species_part in ["sp.", "sp"]:
        if genus in unique_genera:
            is_valid = True
            final_scientific_name = f"{genus} sp."
        else:
            close_genera = difflib.get_close_matches(genus, unique_genera, n=1, cutoff=0.80)
            if close_genera:
                corrected_genus = close_genera[0]
                is_valid = True
                final_scientific_name = f"{corrected_genus} sp."
            elif await check_antcat_validity(genus, "sp."):
                 is_valid = True
                 final_scientific_name = f"{genus} sp."
            else:
                 error_msg = f"Rod '{genus}' nebyl nalezen v databázi ani na AntCat (ani podobný)."

    elif species_part in ["cf.", "nr.", "cf", "nr"]:
        qualifier = species_part.rstrip('.') + '.'
        if len(parts) < 3:
             return False, f"Za zkratkou {qualifier} musí následovat název druhu (např. {genus} {qualifier} niger)."
        
        corrected_genus = genus
        if genus not in unique_genera:
             close_genera = difflib.get_close_matches(genus, unique_genera, n=1, cutoff=0.80)
             if close_genera:
                 corrected_genus = close_genera[0]
        
        base_species_epithet = " ".join(parts[2:]).lower()
        base_species_fullname = f"{corrected_genus} {base_species_epithet}"
        
        if base_species_fullname in species_database:
             is_valid = True
             final_scientific_name = f"{corrected_genus} {qualifier} {base_species_epithet}"
        else:
             close_matches = difflib.get_close_matches(base_species_fullname, species_names, n=1, cutoff=0.80)
             if close_matches:
                 found_fullname = close_matches[0]
                 found_parts = found_fullname.split(' ', 1)
                 if len(found_parts) > 1:
                     found_epithet = found_parts[1]
                     is_valid = True
                     final_scientific_name = f"{corrected_genus} {qualifier} {found_epithet}"
             
             if not is_valid:
                 if await check_antcat_validity(corrected_genus, base_species_epithet):
                     is_valid = True
                     final_scientific_name = f"{corrected_genus} {qualifier} {base_species_epithet}"
                 else:
                     error_msg = f"Základní druh '{base_species_fullname}' (uvedený za {qualifier}) nebyl nalezen v databázi (ani podobný)."

    # --- 2. Standardní druh (Rod druh) ---
    else:
        reconstructed_input = f"{genus} {' '.join(p.lower() for p in parts[1:])}"
        
        if reconstructed_input in species_database:
            is_valid = True
            final_scientific_name = reconstructed_input
        else:
            close_matches = difflib.get_close_matches(reconstructed_input, species_names, n=1, cutoff=0.85)
            if close_matches:
                is_valid = True
                final_scientific_name = close_matches[0]
            else:
                is_valid_antcat = await check_antcat_validity(genus, ' '.join(parts[1:]))
                if is_valid_antcat:
                    is_valid = True
                    final_scientific_name = reconstructed_input
                else:
                    error_msg = f"Druh '{reconstructed_input}' nebyl nalezen v seznamu ani na AntCat. Zkontroluj pravopis."

    if is_valid:
        return True, final_scientific_name + trade_name_suffix
    else:
        return False, error_msg

async def check_antcat_validity(rod: str, druh: str) -> bool:
    """Záložní kontrola přes AntCat API."""
    if druh.lower() in ["sp.", "sp"]:
        query_name = rod
    else:
        query_name = f"{rod.capitalize()} {druh.lower()}"
        
    api_url = f"https://www.antcat.org/v1/taxa/search/{query_name}"

    try:
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return len(data) > 0
    except Exception as e:
        print(f"Chyba při komunikaci s AntCat API: {e}")
    return False

# --- Definice skupiny příkazů ---
seznam_group = app_commands.Group(name="seznam", description="Správa chovaných druhů mravenců.")

@seznam_group.command(name="pridat", description="Přidá druh do seznamu. Zadej 0 pro přidání do historie (vlastnil jsem).")
@app_commands.describe(species="Název druhu (např. Lasius niger)", number="Počet kolonií (0 = v minulosti, 1+ = aktuální)")
@app_commands.autocomplete(species=species_autocomplete)
async def seznam_pridat(interaction: discord.Interaction, species: str, number: int = 1):
    user_id = str(interaction.user.id)
    MAX_COLONIES_PER_SPECIES = 25
    
    if number < 0:
        await interaction.response.send_message("Počet kolonií nesmí být záporný.", ephemeral=True)
        return
    
    await interaction.response.defer()

    is_valid, result = await validate_species_input(species)
    
    if not is_valid:
        await interaction.followup.send(f'⛔ **Chyba v názvu:** {result}', ephemeral=True)
        return

    formatted_ant = result

    # Zjistíme, zda je druh na serveru zcela nový (ještě jej nikdo nemá/neměl)
    is_new_to_server = True
    for uid, ants_data in user_ants.items():
        if formatted_ant in ants_data:
            is_new_to_server = False
            break

    if user_id not in user_ants:
        user_ants[user_id] = {}
    
    current_count = user_ants[user_id].get(formatted_ant, 0)
    
    new_total = current_count + number

    if new_total > MAX_COLONIES_PER_SPECIES:
        await interaction.followup.send(
            f'⛔ **Limit překročen!**\n'
            f'Maximální povolený počet kolonií jednoho druhu je **{MAX_COLONIES_PER_SPECIES}**.\n'
            f'Aktuálně máš: {current_count}. Pokoušíš se přidat: {number}.\n'
            f'Zbývá místa: {max(0, MAX_COLONIES_PER_SPECIES - current_count)}.',
            ephemeral=True
        )
        return
    
    user_ants[user_id][formatted_ant] = new_total
    
    msg = ""
    clean_input = species.strip().lower()
    clean_result = formatted_ant.strip().lower()
    
    if clean_input != clean_result:
        msg = f"ℹ️ Název upraven na: **{formatted_ant}**\n"
        
    if new_total > 0:
         # Pokud jsme něco přidali k nule, nebo to bylo >0
         action_msg = f"Přidáno {number} kolonií." if number > 0 else "Seznam aktualizován."
         await interaction.followup.send(f'{msg}{action_msg} **{formatted_ant}**. Celkem: {user_ants[user_id][formatted_ant]}.')
    else:
        # new_total je 0 (přidáno 0 k 0)
        await interaction.followup.send(f'{msg}Druh **{formatted_ant}** přidán do historie (stav: 0 kolonií).')
    
    save_user_ants()

    # Odeslání upozornění do mod-chatu, pokud se jedná o neznámý (nový) druh
    if is_new_to_server:
        mod_channel = interaction.client.get_channel(707574708551548973)
        if mod_channel:
            embed = discord.Embed(
                title="⚠️ Upozornění: Nový druh na serveru!",
                description=f"Uživatel {interaction.user.mention} si právě přidal do seznamu druh **{formatted_ant}**, který do teď nikdo jiný na serveru neměl.\n\nProsím o kontrolu, zda se nejedná o překlep nebo nesmyslný záznam.",
                color=discord.Color.yellow()
            )
            await mod_channel.send(embed=embed)


@seznam_group.command(name="smazat", description="Úplně vymaže druh ze seznamu i z historie.")
@app_commands.describe(species="Druh mravence k úplnému smazání")
@app_commands.autocomplete(species=species_autocomplete) 
async def seznam_smazat(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    found_key = None
    if user_id in user_ants:
        if species in user_ants[user_id]:
            found_key = species
        else:
            for stored_ant in user_ants[user_id]:
                if stored_ant.lower() == species.lower():
                    found_key = stored_ant
                    break
    
    if not found_key:
        is_valid, formatted = await validate_species_input(species)
        if is_valid and user_id in user_ants and formatted in user_ants[user_id]:
             found_key = formatted

    if not found_key:
        await interaction.response.send_message(f'Nemáš druh **{species}** v seznamu.', ephemeral=True)
        return
    
    del user_ants[user_id][found_key]
    if not user_ants[user_id]:
        del user_ants[user_id]
    save_user_ants()
    await interaction.response.send_message(f'Druh **{found_key}** byl kompletně odstraněn ze záznamů.')

@seznam_group.command(name="odebrat_pocet", description="Odebere počet kolonií. Při dosažení 0 přesune do historie.")
@app_commands.describe(species="Druh mravence", number="Počet kolonií k odebrání")
@app_commands.autocomplete(species=species_autocomplete)
async def seznam_odebrat_pocet(interaction: discord.Interaction, species: str, number: int = 1):
    user_id = str(interaction.user.id)

    found_key = None
    if user_id in user_ants:
        if species in user_ants[user_id]:
            found_key = species
        else:
            for stored_ant in user_ants[user_id]:
                if stored_ant.lower() == species.lower():
                    found_key = stored_ant
                    break
    
    if not found_key:
        is_valid, formatted = await validate_species_input(species)
        if is_valid and user_id in user_ants and formatted in user_ants[user_id]:
             found_key = formatted

    if not found_key:
        await interaction.response.send_message(f'Nemáš druh **{species}** v seznamu.', ephemeral=True)
        return

    current_count = user_ants[user_id][found_key]
    if number >= current_count:
        # Místo mazání nastavíme na 0 (historie)
        user_ants[user_id][found_key] = 0
        await interaction.response.send_message(f'Všechny kolonie druhu **{found_key}** byly odebrány. Druh přesunut do historie (0 kolonií).')
    else:
        user_ants[user_id][found_key] -= number
        await interaction.response.send_message(f'Odebráno {number} kolonií {found_key}. Zbývá: {user_ants[user_id][found_key]}.')
    
    save_user_ants()

@seznam_group.command(name="zobrazit", description="Zobrazí seznam. Aktivní kolonie jsou nahoře.")
@app_commands.describe(uzivatel="Uživatel, jehož seznam chceš zobrazit (volitelné).")
async def seznam_zobrazit(interaction: discord.Interaction, uzivatel: discord.Member = None):
    target_user = uzivatel or interaction.user
    target_user_id = str(target_user.id)

    if target_user_id not in user_ants or not user_ants[target_user_id]:
        message = f'Uživatel {target_user.mention} nemá žádné mravence v seznamu.' if uzivatel else 'Tvůj seznam je prázdný.'
        await interaction.response.send_message(message)
        return

    ant_list = user_ants[target_user_id]
    
    # Rozdělení na aktivní a historii
    active_ants = {k: v for k, v in ant_list.items() if v > 0}
    history_ants = {k: v for k, v in ant_list.items() if v == 0}
    
    # Seřazení abecedně v rámci skupin
    sorted_active = sorted(active_ants.items(), key=lambda item: item[0].lower())
    sorted_history = sorted(history_ants.items(), key=lambda item: item[0].lower())
    
    # Spojení seznamů (aktivní první)
    combined_items = sorted_active + sorted_history
    
    pages = []
    current_page_fields = []
    
    total_active_colonies = sum(active_ants.values())
    total_active_types = len(active_ants)
    total_history_types = len(history_ants)
    
    MAX_FIELDS_PER_PAGE = 24 

    for i, (cmd_name, count) in enumerate(combined_items):
        # Indikátor stavu
        # Active: "Lasius niger" -> "5 kol."
        # History: "Lasius niger" -> "V minulosti 📜"
        
        field_name = cmd_name
        
        if count > 0:
            value_text = f"{count} kol."
        else:
            value_text = "V minulosti 📜"
        
        current_page_fields.append((field_name, value_text))
        
        if len(current_page_fields) == MAX_FIELDS_PER_PAGE or i == len(combined_items) - 1:
            embed = discord.Embed(title=f"Seznam chovaných mravenců: {target_user.display_name}", color=discord.Color.blue())
            if target_user.avatar:
                embed.set_thumbnail(url=target_user.avatar.url)
            
            for ant_field_name, ant_field_val in current_page_fields:
                embed.add_field(name=ant_field_name, value=ant_field_val, inline=True)
            
            # Zarovnání gridu
            if len(current_page_fields) % 3 != 0:
                 remaining = 3 - (len(current_page_fields) % 3)
                 for _ in range(remaining):
                     embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            embed.set_footer(text=f"Aktivní: {total_active_types} druhů ({total_active_colonies} kolonií) | Historie: {total_history_types} druhů")
            pages.append(embed)
            current_page_fields = []

    view = PaginatorView(pages, interaction)
    await interaction.response.send_message(embed=pages[0], view=view)
    view.message = await interaction.original_response()

@seznam_group.command(name="hledat", description="Vyhledá uživatele nebo druh (včetně historie).")
@app_commands.describe(query="Jméno uživatele nebo druh mravence.")
async def seznam_hledat(interaction: discord.Interaction, query: str):
    final_embed = None
    final_view = None
    
    client = interaction.client
    
    member = interaction.guild.get_member_named(query)
    if not member:
        try:
            member = await client.fetch_user(int(query))
        except (ValueError, discord.NotFound):
            pass

    if member and str(member.id) in user_ants and user_ants[str(member.id)]:
        await seznam_zobrazit(interaction, uzivatel=member)
        return
    else:
        search_term_lower = query.lower()
        found_ants = {} 
        for user_id, ants_data in user_ants.items():
            user = client.get_user(int(user_id))
            if not user: continue
            
            for ant_name, count in ants_data.items():
                if search_term_lower in ant_name.lower(): 
                    if ant_name not in found_ants:
                        found_ants[ant_name] = []
                    
                    status_str = f"({count} kolonií)" if count > 0 else "(V minulosti 📜)"
                    found_ants[ant_name].append(f"{user.display_name} {status_str}")
        
        if found_ants:
            pages = []
            current_page_description = ""
            MAX_CHARS_PER_PAGE = 1500 
            
            sorted_found_ants = sorted(found_ants.items(), key=lambda item: item[0].lower())

            for ant, users in sorted_found_ants:
                entry_text = f"**{ant}**\n"
                for user_info in users:
                    entry_text += f"• {user_info}\n"
                entry_text += "\n"
                
                if len(current_page_description) + len(entry_text) > MAX_CHARS_PER_PAGE:
                    embed = discord.Embed(title=f"Výsledky hledání pro: '{query}'", description=current_page_description, color=discord.Color.orange())
                    pages.append(embed)
                    current_page_description = entry_text 
                else:
                    current_page_description += entry_text
            
            if current_page_description:
                embed = discord.Embed(title=f"Výsledky hledání pro: '{query}'", description=current_page_description, color=discord.Color.orange())
                pages.append(embed)

            if pages:
                final_embed = pages[0]
                final_view = PaginatorView(pages, interaction)
            else: 
                final_embed = discord.Embed(title=f"Výsledky hledání pro: '{query}'", description="Nenalezeny žádné druhy ani uživatel.", color=discord.Color.red())
            
    if final_embed:
        await interaction.response.send_message(embed=final_embed, view=final_view)
        if final_view:
            final_view.message = await interaction.original_response()
    else:
        await interaction.response.send_message("Došlo k chybě. Nenalezeny žádné výsledky.", ephemeral=True)
        
        
# Tento soubor spravuje systém událostí a notifikací pro Discord bota.
#
# Funkce:
# - Ukládání a načítání událostí do JSON souboru (events.json).
# - Příkaz /udalosti zobrazit: Výpis akcí s paginátorem a detaily (Web, Kontakt, Pozvánka).
# - Příkaz /udalosti pridat: Ruční přidání akce přes formulář (Modal).
# - Příkaz /udalosti pridat_entosphinx: Pokročilý scraping burz z Entosphinx.cz.
# - Automatické notifikace: Upozornění 1 měsíc, 1 týden a 1 den před akcí.
#
# Závislosti:
# - discord.py, requests, beautifulsoup4, datetime, json, re, asyncio

import discord
from discord import app_commands, ui
import json
import os
import datetime
import asyncio
import requests
from bs4 import BeautifulSoup
import re
import uuid
from typing import List, Optional

# --- Import PaginatorView z utils ---
# Předpokládáme, že utils.py je ve stejné složce
from utils import PaginatorView

# --- Konstanty ---
EVENTS_FILE = 'Soubory/events.json'
NOTIFICATION_CHANNEL_ID = 661958543548612660
ENTOSPHINX_URL = "https://www.entosphinx.cz/cs/content/8-entomologicke-burzy"

ALLOWED_ROLE_IDS = [
    661971700556234753, # Samec - mod na zkoušku
    661971822006239242, # Královna - moderátor
    661971417746898971, # Antkeeper - ADMIN
    913531312797798420  # Informátor událostí
]

# --- Globální proměnná pro události ---
# Struktura: { "uuid": { "title", "start", "end", "location", "description", "image", "source", "invitation_link", "contact", "website" } }
events_data = {}

# --- Správa dat ---
def load_events():
    """Načte události ze souboru."""
    global events_data
    try:
        with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
            events_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {EVENTS_FILE} nenalezen, vytvářím nový.")
        # Ujistíme se, že složka existuje
        os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
        events_data = {}

def save_events():
    """Uloží události do souboru."""
    try:
        # Ujistíme se, že složka existuje
        os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
        with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání událostí: {e}")

# Načteme data při importu
load_events()

# --- Pomocné funkce ---
def has_permission(interaction: discord.Interaction) -> bool:
    """Zkontroluje, zda má uživatel jednu z povolených rolí."""
    if not isinstance(interaction.user, discord.Member):
        return False
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(allowed_id in user_role_ids for allowed_id in ALLOWED_ROLE_IDS)

def parse_date_str(date_str: str) -> Optional[datetime.date]:
    """Převede string typu '10. 1. 2026' na objekt date."""
    try:
        # Odstranění mezer a běžný formát d.m.Y
        clean_str = date_str.replace(" ", "")
        return datetime.datetime.strptime(clean_str, "%d.%m.%Y").date()
    except ValueError:
        return None

def format_time_remaining(event_date: datetime.date) -> str:
    """Vrátí lidsky čitelný čas zbývající do události."""
    today = datetime.date.today()
    delta = event_date - today
    days = delta.days

    if days < 0:
        return "(Proběhlo)"
    elif days == 0:
        return "(**Dnes!**)"
    elif days == 1:
        return "(**Zítra!**)"
    elif days < 7:
        return f"(za {days} dní)"
    elif days < 30:
        weeks = round(days / 7)
        if weeks <= 1:
            return "(za 1 týden)"
        elif weeks <= 4:
            return f"(za {weeks} týdny)"
        else:
            return f"(za {weeks} týdnů)"
    else:
        months = round(days / 30)
        if months <= 1:
            return "(za 1 měsíc)"
        elif months <= 4:
            return f"(za {months} měsíce)"
        else:
            return f"(za {months} měsíců)"

# --- UI Komponenty ---

class EventModal(ui.Modal, title="Přidat novou událost"):
    name = ui.TextInput(label="Název akce", placeholder="např. Entomologická burza Praha", required=True)
    date_range = ui.TextInput(label="Datum (DD.MM.RRRR nebo rozsah)", placeholder="10.1.2026 nebo 1.1.2026 - 2.1.2026", required=True)
    location = ui.TextInput(label="Místo konání", placeholder="např. Kulturní dům Barikádníků, Praha", required=True)
    description = ui.TextInput(label="Popis akce (vč. kontaktů a webu)", style=discord.TextStyle.paragraph, placeholder="Detaily o akci...", required=False)
    image_url = ui.TextInput(label="Odkaz na obrázek (URL)", placeholder="https://...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        # Zpracování data
        raw_date = self.date_range.value.strip()
        start_date = None
        end_date = None

        date_pattern = r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"
        dates = re.findall(date_pattern, raw_date)

        if not dates:
            await interaction.response.send_message("❌ Nepodařilo se rozpoznat datum. Použijte formát `DD.MM.RRRR`.", ephemeral=True)
            return

        try:
            start_date = parse_date_str(dates[0])
            if len(dates) > 1:
                end_date = parse_date_str(dates[1])
            else:
                end_date = start_date
        except Exception:
             await interaction.response.send_message("❌ Chyba při zpracování data.", ephemeral=True)
             return

        if not start_date:
             await interaction.response.send_message("❌ Neplatné datum.", ephemeral=True)
             return

        event_id = str(uuid.uuid4())
        events_data[event_id] = {
            "title": self.name.value,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "location": self.location.value,
            "description": self.description.value or "Bez popisu.",
            "image": self.image_url.value or None,
            "source": f"Přidal: {interaction.user.display_name}",
            "invitation_link": self.image_url.value or None,
            "contact": None, # Manualně vložené akce nemají separátní pole, vše je v popisu
            "website": None
        }
        save_events()

        embed = discord.Embed(title="✅ Událost přidána", color=discord.Color.green())
        embed.add_field(name=self.name.value, value=f"{start_date.strftime('%d.%m.%Y')} v {self.location.value}")
        await interaction.response.send_message(embed=embed)


# --- Skupina příkazů ---
udalosti_group = app_commands.Group(name="udalosti", description="Správa entomologických událostí a burz.")

@udalosti_group.command(name="zobrazit", description="Zobrazí seznam nadcházejících událostí.")
async def udalosti_zobrazit(interaction: discord.Interaction):
    if not events_data:
        await interaction.response.send_message("Zatím nejsou v plánu žádné události.", ephemeral=True)
        return

    # Seřazení událostí podle data
    sorted_events = []
    today = datetime.date.today()
    
    for eid, data in events_data.items():
        try:
            s_date = datetime.date.fromisoformat(data['start'])
            # Filtrovat staré akce (starší než 7 dní od dneška se nezobrazují)
            if s_date >= (today - datetime.timedelta(days=7)):
                sorted_events.append((eid, data, s_date))
        except ValueError:
            continue

    sorted_events.sort(key=lambda x: x[2])

    if not sorted_events:
        await interaction.response.send_message("Žádné nadcházející události.", ephemeral=True)
        return

    pages = []
    for eid, data, s_date in sorted_events:
        date_str = s_date.strftime("%d. %m. %Y")
        if data['start'] != data['end']:
            try:
                e_date = datetime.date.fromisoformat(data['end'])
                date_str += f" - {e_date.strftime('%d. %m. %Y')}"
            except: pass
        
        time_remaining = format_time_remaining(s_date)
        date_display = f"{date_str} {time_remaining}"

        embed = discord.Embed(
            title=data['title'],
            description=data['description'][:4000],
            color=discord.Color.orange()
        )
        embed.add_field(name="📅 Kdy", value=date_display, inline=True)
        embed.add_field(name="📍 Kde", value=data['location'], inline=True)
        
        # Nové pole pro odkazy
        links_text = ""
        
        # Pozvánka
        invitation = data.get('invitation_link')
        if invitation:
            links_text += f"**[📄 Pozvánka]({invitation})**\n"
        
        # Web
        website = data.get('website')
        if website:
            links_text += f"**[🌐 Web akce]({website})**\n"
            
        # Kontakt
        contact = data.get('contact')
        if contact:
            if "@" in contact and not contact.startswith("mailto:"):
                 links_text += f"📧 {contact}\n"
            elif contact.startswith("mailto:"):
                 # Z mailto:email@neco.cz vytahneme email@neco.cz
                 clean_email = contact.replace("mailto:", "")
                 links_text += f"📧 {clean_email}\n"
            else:
                 links_text += f"📞 {contact}\n"

        if links_text:
             embed.add_field(name="🔗 Odkazy a Kontakt", value=links_text, inline=False)

        # Obrázek (pokud existuje a je to obrázek, ne PDF)
        img_url = data.get('image')
        if img_url:
            embed.set_image(url=img_url)
        
        embed.set_footer(text=f"Zdroj: {data.get('source', 'Neznámý')} | ID: {eid}")
        pages.append(embed)

    view = PaginatorView(pages, interaction)
    message = await interaction.response.send_message(embed=pages[0], view=view)
    view.message = await interaction.original_response()

@udalosti_group.command(name="pridat", description="Ručně přidá novou událost (jen pro oprávněné).")
async def udalosti_pridat(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("Nemáš oprávnění přidávat události.", ephemeral=True)
        return
    
    await interaction.response.send_modal(EventModal())

@udalosti_group.command(name="pridat_entosphinx", description="Načte aktuální burzy z Entosphinx.cz (jen pro oprávněné).")
async def udalosti_pridat_entosphinx(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("Nemáš oprávnění spouštět scraping.", ephemeral=True)
        return

    await interaction.response.defer()
    
    try:
        # 1. Získání HTML
        local_file = 'entosphinx burzy.html'
        html_content = ""
        
        try:
            response = requests.get(ENTOSPHINX_URL, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            html_content = response.text
        except Exception as e:
            if os.path.exists(local_file):
                with open(local_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                raise e

        soup = BeautifulSoup(html_content, 'html.parser')
        
        content_div = soup.find('div', class_='rte')
        if not content_div:
            await interaction.followup.send("❌ Nepodařilo se najít kontejner s událostmi na stránce.")
            return

        added_count = 0
        header_pattern = re.compile(r'([A-Za-ž]+)\s*-\s*(\d{1,2}\.?\s*-?\s*\d*\.?\s*\d+\.\s*\d{4})', re.IGNORECASE)
        
        # Získáme všechny paragrafy a divy
        paragraphs = content_div.find_all(['p', 'div'])
        
        i = 0
        while i < len(paragraphs):
            p = paragraphs[i]
            text = p.get_text(strip=True)
            match = header_pattern.search(text)
            
            if match:
                city = match.group(1).strip()
                date_str = match.group(2).strip()
                
                # Zpracování data
                start_date = None
                end_date = None
                try:
                    nums = re.findall(r'\d+', date_str)
                    if not nums: 
                        i += 1
                        continue
                    
                    year = int(nums[-1])
                    month = int(nums[-2])
                    day_start = int(nums[0])
                    
                    if len(nums) > 3:
                         day_end = int(nums[1])
                    else:
                         day_end = day_start
                    
                    start_date = datetime.date(year, month, day_start)
                    end_date = datetime.date(year, month, day_end)
                except Exception as e:
                    print(f"Date parse error: {date_str} - {e}")
                    i += 1
                    continue

                # Duplicita
                is_duplicate = False
                for existing in events_data.values():
                    if existing['start'] == start_date.isoformat() and existing['location'] == city:
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    i += 1
                    continue

                # --- Extrakce detailů (Web, Kontakt, Pozvánka) ---
                # Prohledáme aktuální 'p' a také následující 'p', pokud neobsahuje nové datum
                
                description_text = text
                invitation_link = None
                image_url = None
                contact = None
                website = None
                
                elements_to_scan = [p]
                
                # Podíváme se na další element, jestli nepatří k této akci
                # (Entosphinx má často nadpis v jednom P a detaily v dalším P)
                if i + 1 < len(paragraphs):
                    next_p = paragraphs[i+1]
                    next_text = next_p.get_text(strip=True)
                    # Pokud další element NENÍ nová událost (nemá pattern data)
                    if not header_pattern.search(next_text):
                        elements_to_scan.append(next_p)
                        description_text += "\n" + next_text
                        # Posuneme index, abychom tento paragraf nezpracovali znovu (i když by neprošel checkem data, je to čistší)
                        # Ale pozor, while loop se inkrementuje na konci, takže tady opatrně.
                        # Pro jednoduchost, jen naskenujeme data, ale index inkrementovat nebudeme, 
                        # hlavní smyčka ho přeskočí, protože v něm nenajde datum.

                # Skenování odkazů
                for elem in elements_to_scan:
                    links = elem.find_all('a', href=True)
                    for link in links:
                        href = link['href']
                        
                        # Fix relativních cest
                        if not href.startswith(('http', 'mailto')):
                            if href.startswith('/'):
                                href = "https://www.entosphinx.cz" + href
                            else:
                                href = "https://www.entosphinx.cz/" + href

                        lower_href = href.lower()

                        # 1. Email
                        if href.startswith('mailto:'):
                            contact = href # Uložíme celé mailto:
                        elif '@' in href and not 'entosphinx' in href: # Jednoduchá detekce
                             contact = href

                        # 2. Pozvánka (Obrázek nebo PDF)
                        elif lower_href.endswith(('.jpg', '.png', '.jpeg', '.pdf','.jfif')):
                            invitation_link = href
                            # Pokud je to obrázek, dáme ho i do image_url pro náhled
                            if not lower_href.endswith('.pdf'):
                                image_url = href
                        
                        # 3. Web (pokud to není pozvánka ani email a není to odkaz na entosphinx mapu stránek apod.)
                        elif 'google' not in lower_href and 'entosphinx' not in lower_href:
                            website = href

                # Přidání
                event_id = str(uuid.uuid4())
                events_data[event_id] = {
                    "title": f"Entomologická burza {city}",
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "location": city,
                    "description": description_text,
                    "image": image_url,
                    "invitation_link": invitation_link,
                    "contact": contact,
                    "website": website,
                    "source": "Entosphinx.cz (Auto)"
                }
                added_count += 1
            
            i += 1

        save_events()
        await interaction.followup.send(f"✅ Zpracováno. Přidáno **{added_count}** nových událostí z Entosphinx.")

    except Exception as e:
        await interaction.followup.send(f"❌ Chyba při scrapování: {e}")
        print(f"Scraping error: {e}")

@udalosti_group.command(name="smazat", description="Smaže událost podle ID (jen pro oprávněné).")
@app_commands.describe(event_id="ID události (najdeš v /udalosti zobrazit)")
async def udalosti_smazat(interaction: discord.Interaction, event_id: str):
    if not has_permission(interaction):
        await interaction.response.send_message("Nemáš oprávnění mazat události.", ephemeral=True)
        return
    
    if event_id in events_data:
        del events_data[event_id]
        save_events()
        await interaction.response.send_message(f"🗑️ Událost `{event_id}` byla smazána.")
    else:
        await interaction.response.send_message(f"❌ Událost s ID `{event_id}` nebyla nalezena.", ephemeral=True)

# --- Background Task: Notifikace ---

async def check_upcoming_events(client: discord.Client):
    """Smyčka, která kontroluje události a posílá notifikace."""
    await client.wait_until_ready()
    
    while not client.is_closed():
        today = datetime.date.today()
        channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
        
        if not channel:
            print(f"VAROVÁNÍ: Notifikační kanál {NOTIFICATION_CHANNEL_ID} nenalezen.")
            await asyncio.sleep(3600) # Zkusíme za hodinu
            continue

        for eid, data in events_data.items():
            try:
                start_date = datetime.date.fromisoformat(data['start'])
                delta = (start_date - today).days
                
                msg_prefix = None
                
                # Kontrola: 1 měsíc (cca 30 dní), 1 týden (7 dní), 1 den (1 den)
                if delta == 30:
                    msg_prefix = "🗓️ **Za měsíc**"
                elif delta == 7:
                    msg_prefix = "⏰ **Za týden**"
                elif delta == 1:
                    msg_prefix = "⚠️ **Zítra**"

                if msg_prefix:
                    embed = discord.Embed(
                        title=f"{msg_prefix}: {data['title']}",
                        description=data['description'][:200] + "...",
                        color=discord.Color.red()
                    )
                    date_str = start_date.strftime("%d. %m. %Y")
                    embed.add_field(name="Kdy", value=date_str)
                    embed.add_field(name="Kde", value=data['location'])
                    
                    # Přidání odkazů do notifikace
                    links = []
                    if data.get('invitation_link'): links.append(f"[Pozvánka]({data['invitation_link']})")
                    if data.get('website'): links.append(f"[Web]({data['website']})")
                    
                    if links:
                        embed.add_field(name="Odkazy", value=" | ".join(links), inline=False)

                    if data.get('image'):
                        embed.set_thumbnail(url=data['image'])
                    
                    await channel.send(content=f"🔔 Připomínka události!", embed=embed)
                    
            except Exception as e:
                print(f"Chyba při kontrole eventu {eid}: {e}")

        # Počkáme 24 hodin před další kontrolou
        await asyncio.sleep(86400)

def setup_udalosti(client: discord.Client):
    """Funkce pro inicializaci background tasku z main.py"""
    client.loop.create_task(check_upcoming_events(client))
    
# Tento soubor spravuje příkazy pro inzerci (/inzerce).
#
# Funkce:
# - Umožňuje uživatelům s rolí "inzeráty a inzerenti" vytvářet inzeráty.
# - Rozlišuje kategorie: Kolonie, Formikária, Příslušenství, Ostatní.
# - Odesílá embed do inzertního kanálu s trvalým tlačítkem "Odpovědět".
# - Ukládá inzeráty do `inzerce.json`.
# - Automaticky maže inzeráty po 30 dnech a notifikuje uživatele.
# - NOVINKA: Přejmenováno /inzerce pridat na /inzerce prodam.
# - NOVINKA: Přidán příkaz /inzerce hledam pro poptávky.
# - NOVINKA: Interaktivní tlačítko "Odpovědět" u všech inzerátů (posílá DM).
# - UPDATE: Patička inzerátu obsahuje datum expirace, ID inzerátu a ID autora.
# - NOVINKA (Scan): Funkce process_chat_message pro skenování volného textu.
# - NOVINKA (Match): Automatické párování nabídek a poptávek s notifikacemi.
#
# Závislosti:
# - discord.py, json, datetime, asyncio, re
# - seznam_commands (pro validaci druhů)

import discord
from discord import app_commands, ui
import json
import os
import datetime
import asyncio
import re
from typing import Optional, List

try:
    from Příkazy.seznam_commands import validate_species_input, species_autocomplete, species_names
except ImportError:
    from seznam_commands import validate_species_input, species_autocomplete, species_names

# --- Konstanty ---
INZERCE_FILE = 'Soubory/inzerce.json'
WISHLIST_FILE = 'Soubory/wishlists.json' 
AD_CHANNEL_ID = 721732364664963103  
NOTIFICATION_CHANNEL_ID = 662424508266840080  
AD_ROLE_ID = 803657064600567838  

MOD_ROLE_IDS = [
    661971700556234753, 
    661971822006239242, 
    661971417746898971, 
]

CATEGORY_THUMBNAILS = {
    "Kolonie": "https://i.imgur.com/jgygbXm.png", 
    "Formikária": "https://i.imgur.com/YqG2xqt.png", 
    "Příslušenství": "https://i.imgur.com/T7PqsLe.png", 
    "Ostatní": "https://i.imgur.com/0sMpLJD.png",
    "Poptávka": "https://i.imgur.com/MMJDqYf.png"
}

active_ads = {}

# --- Správa dat ---
def load_ads():
    global active_ads
    try:
        with open(INZERCE_FILE, 'r', encoding='utf-8') as f:
            active_ads = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        active_ads = {}

def save_ads():
    try:
        with open(INZERCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(active_ads, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání inzerce: {e}")

load_ads()

# --- Pomocné funkce ---
def has_ad_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(role.id == AD_ROLE_ID for role in interaction.user.roles)

def is_moderator(user: discord.Member) -> bool:
    return any(role.id in MOD_ROLE_IDS for role in user.roles)

def get_expiration_date():
    return (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()

async def check_wishlists_and_notify(interaction_or_message, species_name: str, price: str, ad_link: str):
    try:
        with open(WISHLIST_FILE, 'r', encoding='utf-8') as f:
            wishlists_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 

    if isinstance(interaction_or_message, discord.Interaction):
        author_id = str(interaction_or_message.user.id)
        author_mention = interaction_or_message.user.mention
        guild = interaction_or_message.guild
    else:
        author_id = str(interaction_or_message.author.id)
        author_mention = interaction_or_message.author.mention
        guild = interaction_or_message.guild

    users_to_notify = []
    species_name_lower = species_name.lower()

    for user_id, data in wishlists_data.items():
        if str(user_id) == author_id:
            continue
            
        if not data.get("notifications", True):
            continue

        items = data.get("items", [])
        for item in items:
            if item.get("name", "").lower() == species_name_lower and not item.get("completed", False):
                users_to_notify.append(user_id)
                break
    
    if users_to_notify:
        channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            mentions = " ".join([f"<@{uid}>" for uid in users_to_notify])
            
            embed = discord.Embed(
                title="🔔 Shoda s Wishlistem!",
                description=f"Uživatel {author_mention} právě nabízí druh, který máte ve wishlistu!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Druh", value=species_name, inline=True)
            if price:
                embed.add_field(name="Info", value=price, inline=True)
            embed.add_field(name="Odkaz", value=f"[Přejít na inzerát]({ad_link})", inline=False)
            
            await channel.send(content=f"{mentions}", embed=embed)

# NOVÁ FUNKCE 1: Zkontroluje aktivní poptávky, když někdo něco prodává
async def check_seek_ads_and_notify(interaction: discord.Interaction, item_name: str, ad_link: str):
    users_to_notify = []
    item_lower = item_name.lower()
    
    for ad_id, ad_data in active_ads.items():
        if ad_data.get("intent") == "hledam":
            sought_item = ad_data.get("item_name", "").lower()
            # Pokud se název shoduje (alespoň částečně)
            if sought_item in item_lower or item_lower in sought_item:
                # Neupozorňujeme autora inzerátu
                if ad_data["user_id"] != interaction.user.id:
                    users_to_notify.append(ad_data["user_id"])
                    
    if users_to_notify:
        # Odstranění duplicit, kdyby měl uživatel více stejných poptávek
        users_to_notify = list(set(users_to_notify))
        channel = interaction.guild.get_channel(NOTIFICATION_CHANNEL_ID)
        
        if channel:
            mentions = " ".join([f"<@{uid}>" for uid in users_to_notify])
            embed = discord.Embed(
                title="🔔 Někdo prodává to, co hledáš!",
                description=f"Uživatel {interaction.user.mention} právě přidal nabídku, která odpovídá tvé poptávce z `/inzerce hledam`.",
                color=discord.Color.green()
            )
            embed.add_field(name="Předmět / Druh", value=item_name, inline=True)
            embed.add_field(name="Odkaz na inzerát", value=f"[Přejít na nabídku]({ad_link})", inline=False)
            await channel.send(content=f"{mentions}", embed=embed)

# NOVÁ FUNKCE 2: Najde stávající nabídky, když někdo zadá poptávku
async def find_matching_sell_ads(interaction: discord.Interaction, sought_item: str):
    matching_ads = []
    sought_lower = sought_item.lower()

    for ad_id, ad_data in active_ads.items():
        if ad_data.get("intent") == "prodam":
            # Zjistíme jméno předmětu nebo druhu
            sold_item = ad_data.get("species", "") or ad_data.get("item_name", "")
            sold_lower = sold_item.lower()

            # Částečná shoda textu
            if sought_lower in sold_lower or sold_lower in sought_lower:
                if ad_data["user_id"] != interaction.user.id:
                    guild_id = interaction.guild_id
                    channel_id = ad_data["channel_id"]
                    # Vytvoření přímého odkazu na zprávu
                    link = f"https://discord.com/channels/{guild_id}/{channel_id}/{ad_id}"
                    matching_ads.append((sold_item, link))

    if matching_ads:
        description = "Našli jsme aktivní nabídky, které by tě mohly zajímat:\n\n"
        # Omezíme na max 5 výsledků, aby embed nebyl obří
        for item, link in matching_ads[:5]:
            description += f"• **{item}**: [Zobrazit inzerát]({link})\n"

        if len(matching_ads) > 5:
            description += "\n*... a další (prohledej kanál inzerce).*"

        embed = discord.Embed(
            title="💡 Nalezeny odpovídající nabídky!",
            description=description,
            color=discord.Color.blue()
        )
        # Pošleme jako ephemeral followup (aby to viděl jen autor poptávky)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def process_chat_message(message: discord.Message):
    if message.channel.id != AD_CHANNEL_ID:
        return
    if message.author.bot:
        return

    content_lower = message.content.lower()
    buy_keywords = ["koupím", "koupim", "sháním", "shanim", "hledám", "hledam", "poptávám", "poptavam"]
    if any(word in content_lower for word in buy_keywords):
        return 

    sell_keywords = ["prodám", "prodam", "prodávám", "prodej", "nabízím", "nabizim", "daruji", "darujem", "vyměním", "predám", "ponúkam"]
    if not any(word in content_lower for word in sell_keywords):
        return 

    if not species_names: 
        return

    found_species = []
    for species in species_names:
        if species.lower() in content_lower:
            is_substring = False
            for existing in found_species:
                if species.lower() in existing.lower() and len(species) < len(existing):
                    is_substring = True
                    break
            if not is_substring:
                found_species.append(species)

    if found_species:
        for sp in found_species:
            await check_wishlists_and_notify(message, sp, "Detekováno v chatu", message.jump_url)

async def delete_ad_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    user_is_mod = is_moderator(interaction.user)
    user_id_str = str(interaction.user.id)
    choices = []
    
    for ad_id, ad_data in active_ads.items():
        if user_is_mod or str(ad_data['user_id']) == user_id_str:
            item_name = ad_data.get('species') or ad_data.get('item_name') or "Předmět"
            category = ad_data.get('category', 'Inzerát')
            label = f"{category}: {item_name} (ID: {ad_id[-4:]})" 
            
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=ad_id))
    
    return choices[:15]


# --- Tlačítka a interakce pro odpovídání na inzeráty ---

class ContactAdAuthorModal(ui.Modal, title="Odpověď na inzerát"):
    message_text = ui.TextInput(
        label="Tvoje zpráva pro inzerenta", 
        style=discord.TextStyle.paragraph, 
        placeholder="Ahoj, měl bych zájem o tvůj inzerát. Je to ještě aktuální?",
        max_length=1500,
        required=True
    )

    def __init__(self, author_id: int, ad_url: str, ad_title: str):
        super().__init__()
        self.author_id = author_id
        self.ad_url = ad_url
        self.ad_title = ad_title

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.client.get_user(self.author_id)
        if not user:
            try:
                user = await interaction.client.fetch_user(self.author_id)
            except discord.NotFound:
                await interaction.response.send_message("❌ Nepodařilo se najít autora inzerátu. Možná opustil server.", ephemeral=True)
                return

        embed = discord.Embed(
            title="📩 Nová odpověď na tvůj inzerát",
            description=f"Uživatel {interaction.user.mention} reaguje na tvůj inzerát **{self.ad_title}**.\n\n**Zpráva:**\n{self.message_text.value}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Odkaz na inzerát", value=f"[Zobrazit inzerát zde]({self.ad_url})", inline=False)
        embed.set_footer(text=f"Odpověz uživateli {interaction.user.display_name} do jeho soukromých zpráv.")

        try:
            await user.send(embed=embed)
            await interaction.response.send_message(f"✅ Tvoje zpráva byla úspěšně odeslána uživateli **{user.display_name}** do soukromých zpráv.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ **{user.display_name}** má zablokované přijímání soukromých zpráv od členů serveru. Zkus ho označit (pingnout) přímo v inzertním kanálu.", ephemeral=True)


class AdInteractionView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Timeout None = trvalé tlačítko

    @ui.button(label="Odpovědět na inzerát", style=discord.ButtonStyle.primary, emoji="✉️", custom_id="reply_to_ad_btn")
    async def reply_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.message.embeds:
            await interaction.response.send_message("Chyba: Inzerát neobsahuje potřebná data.", ephemeral=True)
            return
            
        embed = interaction.message.embeds[0]
        footer_text = embed.footer.text if embed.footer else ""
        
        match = re.search(r'UserID:\s*(\d+)', footer_text)
        if not match:
            await interaction.response.send_message("❌ Tento inzerát je ze staré verze a nepodporuje rychlou odpověď. Napiš autorovi ručně.", ephemeral=True)
            return
            
        author_id = int(match.group(1))

        if interaction.user.id == author_id:
            await interaction.response.send_message("Nemůžeš odpovídat na svůj vlastní inzerát. 🙂", ephemeral=True)
            return

        ad_title = embed.title or "Neznámý inzerát"
        await interaction.response.send_modal(ContactAdAuthorModal(author_id, interaction.message.jump_url, ad_title))


# --- Modals (Formuláře pro tvorbu) ---

class BaseAdModal(ui.Modal):
    def __init__(self, category: str, intent: str = "prodej"):
        title_prefix = "Poptávka" if intent == "hledam" else "Inzerát"
        super().__init__(title=f"{title_prefix}: {category}")
        self.category = category
        self.intent = intent
        self.images = ui.TextInput(
            label="Odkazy na obrázky (Imgur apod.)", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            placeholder="Jeden odkaz na řádek. První odkaz bude použit jako velký náhled.",
            max_length=1000
        )

    def get_declined_category(self):
        mapping = {
            "Kolonie": "KOLONIÍ",
            "Formikária": "FORMIKÁRIÍ",
            "Příslušenství": "PŘÍSLUŠENSTVÍ",
            "Ostatní": "OSTATNÍHO"
        }
        return mapping.get(self.category, self.category.upper())

    async def create_ad_embed(self, interaction: discord.Interaction, fields: list, notes: str):
        if self.intent == "prodej":
            title = f"PRODEJ {self.get_declined_category()}"
            color = discord.Color.green()
            thumb_url = CATEGORY_THUMBNAILS.get(self.category)
        else:
            title = f"POPTÁVKA (HLEDÁM)"
            color = discord.Color.orange()
            thumb_url = CATEGORY_THUMBNAILS.get("Poptávka")

        embed = discord.Embed(
            title=title,
            description=notes if notes else "Bez poznámky.",
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=True)
            
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)

        image_urls = [url.strip() for url in self.images.value.split('\n') if url.strip()]
        if image_urls:
            embed.set_image(url=image_urls[0])
            if len(image_urls) > 1:
                links_text = "\n".join(image_urls[1:5]) 
                embed.add_field(name="Další obrázky", value=links_text, inline=False)
        
        expire_dt = datetime.datetime.now() + datetime.timedelta(days=30)
        date_str = expire_dt.strftime("%d. %m. %Y")
        
        embed.set_footer(text=f"Vyprší: {date_str} | UserID: {interaction.user.id}")
        return embed, image_urls

    async def post_ad(self, interaction: discord.Interaction, embed: discord.Embed, ad_data_extra: dict):
        channel = interaction.guild.get_channel(AD_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Chyba: Cílový kanál pro inzeráty nenalezen.", ephemeral=True)
            return None

        view = AdInteractionView()
        message = await channel.send(embed=embed, view=view)
        
        ad_id = str(message.id)
        short_id = ad_id[-4:] 
        current_footer = embed.footer.text
        
        embed.set_footer(text=f"{current_footer} | ID: {short_id}")
        await message.edit(embed=embed)
        
        active_ads[ad_id] = {
            "user_id": interaction.user.id,
            "channel_id": AD_CHANNEL_ID,
            "category": self.category,
            "intent": self.intent,
            "created_at": datetime.datetime.now().isoformat(),
            "expires_at": get_expiration_date(),
            **ad_data_extra
        }
        save_ads()
        
        await interaction.response.send_message(f"✅ Tvůj inzerát byl úspěšně zveřejněn v {channel.mention}!", ephemeral=True)
        return message


class ColonyAdModal(BaseAdModal):
    def __init__(self, species_name: str):
        super().__init__(category="Kolonie", intent="prodej")
        self.species_name = species_name
        
        self.count = ui.TextInput(label="Počet nabízených kolonií", placeholder="např. 1", default="1", max_length=5)
        self.size = ui.TextInput(label="Velikost (Královny / Dělnice)", placeholder="např. 1Q + 10-20w", max_length=100)
        self.price = ui.TextInput(label="Cena (CZK/EUR)", placeholder="např. 500 CZK", max_length=50)
        self.notes = ui.TextInput(
            label="Poznámky", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            max_length=1000,
            placeholder="rok odchycení královny, původ, doručení, další detaily..."
        )

        self.add_item(self.count)
        self.add_item(self.size)
        self.add_item(self.price)
        self.add_item(self.notes)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        fields = [
            ("Druh", self.species_name),
            ("Počet", self.count.value),
            ("Velikost", self.size.value),
            ("Cena", self.price.value)
        ]
        embed, image_urls = await self.create_ad_embed(interaction, fields, self.notes.value)
        ad_data = {"type": "colony", "species": self.species_name, "price": self.price.value, "description": self.notes.value, "images": image_urls}
        
        message = await self.post_ad(interaction, embed, ad_data)
        if message:
            # Notifikace wishlistů
            await check_wishlists_and_notify(interaction, self.species_name, self.price.value, message.jump_url)
            # NOVINKA: Kontrola existujících poptávek
            await check_seek_ads_and_notify(interaction, self.species_name, message.jump_url)


class ItemAdModal(BaseAdModal):
    def __init__(self, category: str):
        super().__init__(category=category, intent="prodej")
        self.item_name = ui.TextInput(label="Název předmětu/zvířete", placeholder="např. Ytong hnízdo velikost M", max_length=100)
        self.amount = ui.TextInput(label="Množství", placeholder="např. 1 ks", max_length=50)
        self.price = ui.TextInput(label="Cena (CZK/EUR)", placeholder="např. 200 CZK", max_length=50)
        self.notes = ui.TextInput(label="Popis a poznámky", style=discord.TextStyle.paragraph, required=False, max_length=1000)

        self.add_item(self.item_name)
        self.add_item(self.amount)
        self.add_item(self.price)
        self.add_item(self.notes)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        fields = [("Předmět", self.item_name.value), ("Množství", self.amount.value), ("Cena", self.price.value)]
        embed, image_urls = await self.create_ad_embed(interaction, fields, self.notes.value)
        ad_data = {"type": "item", "item_name": self.item_name.value, "price": self.price.value, "description": self.notes.value, "images": image_urls}
        
        message = await self.post_ad(interaction, embed, ad_data)
        if message:
            # NOVINKA: Kontrola existujících poptávek (funguje i na předměty)
            await check_seek_ads_and_notify(interaction, self.item_name.value, message.jump_url)


class SeekAdModal(BaseAdModal):
    def __init__(self, species_name: Optional[str] = None):
        super().__init__(category="Hledám", intent="hledam")
        
        default_item = species_name if species_name else ""
        
        self.item_name = ui.TextInput(
            label="Co poptáváš? (Druh mravence / Předmět)", 
            placeholder="např. Kolonii Lasius niger / Ytong hnízdo", 
            default=default_item,
            max_length=100,
            required=True
        )
        self.price = ui.TextInput(
            label="Nabízená cena / Rozpočet", 
            placeholder="např. do 500 Kč, Nabídněte, Vyměním za...", 
            max_length=50,
            required=True
        )
        self.notes = ui.TextInput(
            label="Další detaily a specifikace", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            max_length=1000,
            placeholder="např. chci jen velkou kolonii, osobní předání v Praze, atd..."
        )

        self.add_item(self.item_name)
        self.add_item(self.price)
        self.add_item(self.notes)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        fields = [
            ("Poptávám", self.item_name.value),
            ("Nabízená cena", self.price.value)
        ]
        embed, image_urls = await self.create_ad_embed(interaction, fields, self.notes.value)
        ad_data = {
            "type": "seek", 
            "item_name": self.item_name.value, 
            "price": self.price.value, 
            "description": self.notes.value, 
            "images": image_urls
        }
        
        message = await self.post_ad(interaction, embed, ad_data)
        if message:
            # NOVINKA: Pokud už někdo prodává to, co se právě začalo poptávat, pošleme odkazy (ephemeral)
            await find_matching_sell_ads(interaction, self.item_name.value)


# --- Views (Výběrová menu) ---

class CategorySelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Kolonie mravenců", emoji="🐜", description="Prodej královen a kolonií", value="colony"),
            discord.SelectOption(label="Formikária", emoji="🏠", description="Hnízda, arény, zkumavky", value="formicaria"),
            discord.SelectOption(label="Příslušenství", emoji="🔧", description="Pinzety, krmítka, bariéry", value="accessories"),
            discord.SelectOption(label="Ostatní živočichové/rostliny", emoji="🌿", description="Krmný hmyz, isopodi, rostliny", value="other")
        ]
        super().__init__(placeholder="Vyber kategorii prodeje...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "colony":
            await interaction.response.send_modal(ManualColonyNameModal())
        elif choice == "formicaria":
            await interaction.response.send_modal(ItemAdModal("Formikária"))
        elif choice == "accessories":
            await interaction.response.send_modal(ItemAdModal("Příslušenství"))
        elif choice == "other":
            await interaction.response.send_modal(ItemAdModal("Ostatní"))

class ManualColonyNameModal(ui.Modal, title="Zadej název druhu"):
    species_input = ui.TextInput(label="Název druhu", placeholder="např. Lasius niger", min_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        is_valid, result = await validate_species_input(self.species_input.value)
        if not is_valid:
            await interaction.response.send_message(f"⛔ **Chyba v názvu:** {result}\nZkus to prosím znovu.", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"Druh ověřen: {result}", description="Klikni na tlačítko níže pro vyplnění detailů inzerátu.", color=discord.Color.green())
        view = ContinueToAdView(result)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ContinueToAdView(ui.View):
    def __init__(self, species_name):
        super().__init__()
        self.species_name = species_name

    @ui.button(label="Vyplnit inzerát", style=discord.ButtonStyle.primary, emoji="📝")
    async def continue_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ColonyAdModal(self.species_name))


class InzerceProdamView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(CategorySelect())


# --- Hlavní příkazy ---

inzerce_group = app_commands.Group(name="inzerce", description="Systém pro inzerci na serveru.")

@inzerce_group.command(name="prodam", description="Vytvořit nový inzerát (nabídku). Pro mravence použij 'druh' pro našeptávání!")
@app_commands.describe(druh="Použij POUZE pokud prodáváš mravence, aktivuje našeptávání.")
@app_commands.autocomplete(druh=species_autocomplete)
async def inzerce_prodam(interaction: discord.Interaction, druh: Optional[str] = None):
    if not has_ad_role(interaction):
        await interaction.response.send_message("⛔ Nemáš roli <@&803657064600567838> pro přidávání inzerátů.", ephemeral=True)
        return

    if druh:
        is_valid, result = await validate_species_input(druh)
        if not is_valid:
            await interaction.response.send_message(f"⛔ **Chyba v názvu:** {result}", ephemeral=True)
            return
        await interaction.response.send_modal(ColonyAdModal(result))
    else:
        embed = discord.Embed(title="Vytvoření prodejního inzerátu", description="Vyber kategorii inzerátu z nabídky níže.\n\n*💡 Tip: Pokud prodáváš mravence, použij `/inzerce prodam druh:Nazev` pro využití našeptávače.*", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=InzerceProdamView(), ephemeral=True)


@inzerce_group.command(name="hledam", description="Vytvořit poptávku (koupím / hledám).")
@app_commands.describe(druh="Použij, pokud poptáváš konkrétní druh mravence (aktivuje našeptávač).")
@app_commands.autocomplete(druh=species_autocomplete)
async def inzerce_hledam(interaction: discord.Interaction, druh: Optional[str] = None):
    if not has_ad_role(interaction):
        await interaction.response.send_message("⛔ Nemáš roli <@&803657064600567838> pro přidávání inzerátů.", ephemeral=True)
        return

    species_valid_name = None
    if druh:
        is_valid, result = await validate_species_input(druh)
        if not is_valid:
            await interaction.response.send_message(f"⛔ **Chyba v názvu:** {result}", ephemeral=True)
            return
        species_valid_name = result

    await interaction.response.send_modal(SeekAdModal(species_name=species_valid_name))


@inzerce_group.command(name="smazat", description="Smazat inzerát (pro autory a moderátory).")
@app_commands.describe(inzerat="Vyber inzerát, který chceš smazat.")
@app_commands.autocomplete(inzerat=delete_ad_autocomplete)
async def inzerce_smazat(interaction: discord.Interaction, inzerat: str):
    ad_id = inzerat
    
    if ad_id not in active_ads:
        await interaction.response.send_message("❌ Tento inzerát nebyl nalezen v databázi (možná už expiroval nebo byl smazán).", ephemeral=True)
        return
        
    ad_data = active_ads[ad_id]
    user_is_mod = is_moderator(interaction.user)
    user_is_owner = str(ad_data['user_id']) == str(interaction.user.id)
    
    if not (user_is_mod or user_is_owner):
        await interaction.response.send_message("⛔ Nemáš oprávnění smazat tento inzerát (nejsi autor ani moderátor).", ephemeral=True)
        return

    channel_id = ad_data['channel_id']
    channel = interaction.guild.get_channel(channel_id)
    
    msg_deleted_from_discord = False
    
    if channel:
        try:
            msg = await channel.fetch_message(int(ad_id))
            await msg.delete()
            msg_deleted_from_discord = True
        except discord.NotFound:
            pass
        except discord.Forbidden:
            await interaction.response.send_message("❌ Nemám práva smazat zprávu v inzertním kanálu.", ephemeral=True)
            return
    
    del active_ads[ad_id]
    save_ads()
    
    item_name = ad_data.get('species') or ad_data.get('item_name') or "Předmět"
    
    if msg_deleted_from_discord:
        await interaction.response.send_message(f"✅ Inzerát **{item_name}** byl úspěšně smazán.", ephemeral=True)
    else:
        await interaction.response.send_message(f"✅ Inzerát **{item_name}** byl odstraněn z databáze (zpráva na Discordu už neexistovala).", ephemeral=True)


# --- Background Task: Mazání starých inzerátů ---

async def check_expired_ads(client: discord.Client):
    await client.wait_until_ready()
    
    while not client.is_closed():
        now = datetime.datetime.now()
        ids_to_remove = []
        
        for msg_id, data in active_ads.items():
            try:
                expires_at = datetime.datetime.fromisoformat(data['expires_at'])
                if now >= expires_at:
                    ids_to_remove.append(msg_id)
                    
                    channel = client.get_channel(data['channel_id'])
                    if channel:
                        try:
                            msg = await channel.fetch_message(int(msg_id))
                            await msg.delete()
                        except discord.NotFound:
                            pass 
                    
                    notify_channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
                    user_id = data['user_id']
                    
                    if notify_channel:
                        cat = data.get('category', 'Neznámá')
                        item = data.get('species') or data.get('item_name') or 'Předmět'
                        await notify_channel.send(
                            f"🔔 <@{user_id}>, tvoje inzerce ({cat}: {item}) vypršela a byla smazána. "
                            f"Pokud je nabídka stále aktuální, zadej inzerát znovu."
                        )

            except Exception as e:
                print(f"Chyba při kontrole expirace inzerátu {msg_id}: {e}")

        if ids_to_remove:
            for msg_id in ids_to_remove:
                del active_ads[msg_id]
            save_ads()
        
        await asyncio.sleep(6600)

def setup_inzerce(client: discord.Client):
    client.loop.create_task(check_expired_ads(client))
    
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

# POPIS:
# Tento modul definuje a implementuje slash příkaz `/chov`. Tento příkaz slouží
# k vyhledání a zobrazení ucelených chovatelských informací o konkrétním druhu mravence.
#
# FUNKCIONALITA A ZDROJE DATA:
# 1. NAŠEPTÁVÁNÍ (Autocomplete): Využívá `species_autocomplete` ze seznamu mravenců.
# 2. TAXONOMIE & HISTORIE: Načítá autorství a rok popisu z lokální Bolton databáze
#    (bolton_species.json).
# 3. CHRÁNĚNOST V ČR: Ověřuje přítomnost druhu v českém checklistu (czech_checklist.json).
# 4. CHOVATELSKÁ DATA (Scraping z AntKeeping.info):
#    - Velikosti dělnic a královen (převod rozsahu).
#    - Doporučená teplota a vlhkost v hnízdě.
#    - Typ zakládání kolonie (Claustral/Semifile apod.) a struktura (Mono/Polygynní).
#    - Dělnický polymorfismus a požadavky na zimování (diapauzu).
#    - Čas rojení (nuptial flights) - přepočítává se a formátuje z grafů aktivity
#      do přehledných římských číslic se symbolem intenzity (+/++/+++).
# 5. OBRÁZKY (Fuzzy Check):
#    - Prioritně ověřuje přímý odkaz na kvalitní fotografii z AntCheck.info přes HEAD request.
#    - Jako zálohu používá OG Image tag přímo z AntKeeping.info.
# 6. EXTERNÍ API (GBIF): Vyhledává taxon přes veřejné GBIF API a získává přímý odkaz.
# 7. SITEMAP INTEGRACE: Paršuje sitemapu Formikaristika.cz pro vytvoření odkazu na profil druhu.
# 8. UŽITEČNÉ ODKAZY: Generuje dvousloupcový přehled odkazů na myrmekologické portály:
#    - AntMaps, AntWiki, AntWeb, AntCat, AntScout, AntCheck, iNaturalist, Nature.cz atd.
#
# ASYNCHRONNÍ PROVOZ:
# Scrapování a volání externích API probíhá paralelně v samostatných vláknech
# (run_in_executor), což zabraňuje blokování hlavního event loopu bota.


import discord
from discord import app_commands
import json
import os
import requests
from bs4 import BeautifulSoup
import re
import asyncio
import xml.etree.ElementTree as ET

# Importujeme našeptávač ze seznam_commands
# Používáme try-except blok pro kompatibilitu s různými strukturami složek
try:
    from Příkazy.seznam_commands import species_autocomplete
except ImportError:
    from seznam_commands import species_autocomplete

# --- Globální proměnné pro data ---
bolton_data = {}
checklist_data = []
formikaristika_map = {} # Změněno ze setu na dict pro mapování slug -> url

def load_chov_data():
    """
    Načte data z JSON souborů a sitemapu do globálních proměnných.
    Tuto funkci je potřeba zavolat v main.py v on_ready().
    """
    global bolton_data, checklist_data, formikaristika_map
    
    # 1. Načtení Bolton data
    try:
        with open('Soubory/bolton_species.json', 'r', encoding='utf-8') as f:
            bolton_data = json.load(f)
        print("Bolton data načtena (Chov).")
    except FileNotFoundError:
        print("Soubor bolton_species.json nenalezen.")
        bolton_data = {}

    # 2. Načtení Checklistu
    try:
        with open('Soubory/czech_checklist.json', 'r', encoding='utf-8') as f:
            checklist_data = json.load(f) # Předpokládám, že je to list stringů nebo dict klíčů
        print("Czech checklist načten (Chov).")
    except FileNotFoundError:
        print("Soubor czech_checklist.json nenalezen.")
        checklist_data = []

    # 3. Načtení sitemapy Formikaristika.cz pro ověřování odkazů
    try:
        response = requests.get("https://formikaristika.wordpress.com/sitemap.xml", timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            # Namespace sitemap (obvykle http://www.sitemaps.org/schemas/sitemap/0.9)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            formikaristika_map = {} # Reset mapy
            for url_elem in root.findall('sm:url', ns):
                loc = url_elem.find('sm:loc', ns).text
                if loc:
                    # Získání slugu (poslední část URL)
                    # Např. .../camponotus-ligniperda/ -> camponotus-ligniperda
                    # Ošetříme případné lomítko na konci
                    parts = loc.rstrip('/').split('/')
                    slug = parts[-1]
                    formikaristika_map[slug] = loc
            
            print(f"Sitemap načtena (Chov): {len(formikaristika_map)} URL.")
        else:
             print(f"Chyba při stahování sitemap (Chov): {response.status_code}")
    except Exception as e:
        print(f"Chyba při zpracování sitemap (Chov): {e}")

def get_gbif_link_sync(genus, species):
    """
    Získá odkaz na GBIF databázi pomocí jejich API (Synchronní funkce pro thread).
    """
    url = f"https://api.gbif.org/v1/species/match?name={genus}%20{species}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            usage_key = data.get("usageKey")
            if usage_key:
                return f"https://www.gbif.org/species/{usage_key}"
    except Exception as e:
        print(f"Chyba při získávání GBIF odkazu: {e}")
    return None

def get_antkeeping_data(genus, species):
    """
    Získá data z antkeeping.info (Synchronní funkce, běží v threadu).
    Vrací slovník s nalezenými informacemi.
    Prioritně zkouší získat obrázek z AntCheck.
    """
    url = f"https://antkeeping.info/ants/{genus.lower()}-{species.lower()}/"
    data = {
        "subfamily": "NA",
        "worker_size": "NA",
        "queen_size": "NA",
        "temp": "NA",
        "humidity": "NA",
        "founding": "NA",
        "structure": "NA",
        "polymorphism": "NA",
        "hibernation": "NA", # Nové pole pro diapauzu
        "nuptial_flight": "NA",
        "image_url": None,
        "url": url,
        "found": False
    }

    # --- 0. Pokus o získání obrázku z AntCheck ---
    # Formát: https://antcheck.info/include/frontend/img/compressed/large/ants/Rod_druh.jpeg
    antcheck_url = f"https://antcheck.info/include/frontend/img/compressed/large/ants/{genus}_{species}.jpeg"
    antcheck_found = False
    
    try:
        # Použijeme HEAD request pro rychlé ověření existence bez stahování celého obrázku
        headers = {'User-Agent': 'Mozilla/5.0'}
        head_resp = requests.head(antcheck_url, headers=headers, timeout=2)
        if head_resp.status_code == 200:
            data["image_url"] = antcheck_url
            antcheck_found = True
    except Exception:
        pass # Pokud AntCheck selže, pokračujeme dál

    # --- Scraping AntKeeping.info ---
    try:
        # Simulujeme prohlížeč
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            return data

        data["found"] = True
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- 1. Získání obrázku (OG tag) ---
        # Použijeme pouze pokud jsme nenašli obrázek na AntCheck
        if not antcheck_found:
            og_image = soup.find("meta", property="og:image")
            if og_image:
                img_link = og_image["content"]
                if img_link.startswith("/"):
                    img_link = "https://antkeeping.info" + img_link
                data["image_url"] = img_link

        # --- 2. Získání textových dat (Vylepšeno) ---
        
        # Hledání velikostí pomocí specifických tříd (mnohem spolehlivější)
        size_containers = soup.find_all("div", class_="ant-size-container")
        for container in size_containers:
            title_tag = container.find("h5")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            
            # Hledáme všechny hodnoty v patičce (obvykle Min a Max)
            size_footers = container.find_all("div", class_="size-footer")
            if size_footers:
                # Vezmeme první (min) a poslední (max) hodnotu
                min_val = size_footers[0].get_text(strip=True)
                max_val = size_footers[-1].get_text(strip=True)
                
                # Pokud jsou stejné, zobrazíme jen jednu, jinak rozsah
                if min_val == max_val:
                    size_str = min_val
                else:
                    size_str = f"{min_val} - {max_val}"

                if "Worker" in title:
                    data["worker_size"] = size_str
                elif "Queen" in title:
                    data["queen_size"] = size_str

        # Hledání ostatních informací v tabulkách
        for row in soup.find_all(['tr']):
            header = row.find('th')
            cell = row.find('td')
            
            if header and cell:
                header_text = header.get_text(strip=True)
                cell_text = cell.get_text(strip=True)
                
                if "Subfamily:" in header_text:
                    # Očištění od "Tribe" pokud tam je
                    data["subfamily"] = cell_text.split("Tribe")[0].strip()
                
                if "Nest temperature:" in header_text:
                    data["temp"] = cell_text.split('\n')[0]

                if "Nest humidity:" in header_text:
                    data["humidity"] = cell_text.split('\n')[0]
                    
                if "Colony founding:" in header_text:
                    data["founding"] = cell_text.split('\n')[0]
                    
                if "Colony structure:" in header_text:
                    data["structure"] = cell_text.split('\n')[0]

                if "Worker polymorphism:" in header_text:
                    poly_val = cell_text.split('\n')[0].strip()
                    if poly_val.lower().startswith("yes"):
                        data["polymorphism"] = re.sub(r'^yes', 'Ano', poly_val, flags=re.IGNORECASE)
                    elif poly_val.lower().startswith("no"):
                        data["polymorphism"] = re.sub(r'^no', 'Ne', poly_val, flags=re.IGNORECASE)
                    elif not poly_val or poly_val.lower() in ["na", "n/a", "unknown"]:
                        data["polymorphism"] = "NA"
                    else:
                        data["polymorphism"] = poly_val # Fallback pro jiný text

                if "Hibernation required:" in header_text:
                    hib_val = cell_text.split('\n')[0].strip()
                    if hib_val.lower().startswith("yes"):
                        # Nahradíme "yes" nebo "Yes" na začátku za "Ano", zbytek textu necháme (např. "end of...")
                        data["hibernation"] = re.sub(r'^yes', 'Ano', hib_val, flags=re.IGNORECASE)
                    elif hib_val.lower() == "no":
                        data["hibernation"] = "Ne"
                    elif hib_val.lower() == "no information":
                        data["hibernation"] = "Žádné informace"
                    else:
                        data["hibernation"] = hib_val

        # --- 3. Zpracování grafu rojení ---
        script_content = str(soup)
        match = re.search(r'var chartData\s*=\s*\[(.*?)\];', script_content)
        
        if match:
            chart_str = match.group(1)
            try:
                chart_data = [int(x.strip()) for x in chart_str.split(',')]
                
                # Římské číslice pro měsíce
                months_roman = ["I", "II", "III", "IV", "V", "VI", 
                                "VII", "VIII", "IX", "X", "XI", "XII"]
                
                # Získáme indexy měsíců, kde je nějaká aktivita (> 0)
                active_indices = [i for i, x in enumerate(chart_data) if x > 0]
                
                active_months_strs = []
                max_val = max(chart_data) if chart_data else 0
                
                if active_indices:
                    # Logika podle počtu aktivních měsíců
                    if len(active_indices) <= 2:
                        # Pokud jsou jen 2 nebo méně: tam, kde se rojí nejvíc (max), dáme +, jinak nic
                        for i in active_indices:
                            val = chart_data[i]
                            month_str = months_roman[i]
                            if val == max_val:
                                month_str += "+"
                            active_months_strs.append(month_str)
                    else:
                        # Pokud je měsíců více: škálujeme +, ++, +++
                        # +++ pro peak, ++ pro střední, + pro nízké, jinak nic
                        for i in active_indices:
                            val = chart_data[i]
                            month_str = months_roman[i]
                            
                            ratio = val / max_val
                            if ratio >= 0.8:
                                month_str += "+++"
                            elif ratio >= 0.5:
                                month_str += "++"
                            elif ratio >= 0.25:
                                month_str += "+"
                            else:
                                month_str += ""
                            active_months_strs.append(month_str)
                    
                    data["nuptial_flight"] = ", ".join(active_months_strs)
                else:
                    data["nuptial_flight"] = "Žádná data o rojení"

            except Exception as e:
                print(f"Chyba při parsování grafu: {e}")
                data["nuptial_flight"] = "Chyba dat"

    except Exception as e:
        print(f"Chyba při scrapování antkeeping.info: {e}")
    
    return data

@app_commands.command(name="chov", description="Zobrazí podrobné informace o konkrétním druhu.")
@app_commands.describe(species="Vědecký název druhu (např. Camponotus ligniperda)")
@app_commands.autocomplete(species=species_autocomplete)
async def chov_command(interaction: discord.Interaction, species: str):
    await interaction.response.defer()

    # Rozdělení na Rod a druh
    parts = species.split(' ')
    if len(parts) < 2:
        await interaction.followup.send("Prosím zadej celé jméno druhu (Rod druh).", ephemeral=True)
        return

    genus = parts[0].capitalize()
    species_name = parts[1].lower() 
    full_name = f"{genus} {species_name}"

    # 1. Získání dat z Boltona
    bolton_info = bolton_data.get(full_name, {})
    author_year = bolton_info.get("author_year_full", "Autor neznámý")

    # 2. Získání dat z Checklistu ČR
    in_czech = False
    if isinstance(checklist_data, list):
        in_czech = full_name in checklist_data
    elif isinstance(checklist_data, dict):
            in_czech = full_name in checklist_data

    # 3. Scrapování a GBIF API (běží paralelně v threadech)
    loop = asyncio.get_running_loop()
    ak_task = loop.run_in_executor(None, get_antkeeping_data, genus, species_name)
    gbif_task = loop.run_in_executor(None, get_gbif_link_sync, genus, species_name)
    
    ak_data, gbif_url = await asyncio.gather(ak_task, gbif_task)

    # 4. Sestavení Embedu
    embed = discord.Embed(
        title=f"Informace o chovu {genus} {species_name}",
        description=f"*{genus} {species_name}* {author_year}",
        color=discord.Color.dark_green()
    )

    if ak_data["subfamily"] != "Neznámá":
        embed.set_author(name=f"Podčeleď: {ak_data['subfamily']}")

    # Sloučení informací o velikosti a polymorfismu pod jeden název, aby to vypadalo lépe
    size_info = f"**Dělnice:** {ak_data['worker_size']}\n**Královna:** {ak_data['queen_size']}"
    embed.add_field(name="📏 Velikost", value=size_info, inline=True)
    
    embed.add_field(name="🌡️ Hnízdo", value=f"**Teplota:** {ak_data['temp']}\n**Vlhkost:** {ak_data['humidity']}", inline=False)
    
    # Prázdné pole pro zarovnání (volitelné, pokud chceš 2 sloupce nahoře)
    # embed.add_field(name="\u200b", value="\u200b", inline=True)
    
    
    # Přidání polymorfismu pod kolonii
    colony_info = f"**Zakládání:** {ak_data['founding']}\n**Struktura:** {ak_data['structure']}\n**Polymorfní:** {ak_data['polymorphism']}"
    embed.add_field(name="🏛️ Kolonie", value=colony_info, inline=True)
    
    # Přidání diapauzy
    embed.add_field(name="💤 Diapauza", value=ak_data['hibernation'], inline=False)
 
    embed.add_field(name="✈️ Rojení", value=ak_data['nuptial_flight'], inline=False)

    if ak_data["image_url"]:
        embed.set_image(url=ak_data["image_url"])
    
    # 5. Sestavení Odkazů (dva sloupce)
    url_genus = genus
    url_species = species_name
    
    links_col1 = []
    links_col2 = []
    
    # První sloupec: Mapy a Taxonomie
    links_col1.append(f"🗺️ [AntMaps](https://antmaps.org/?mode=species&species={url_genus}.{url_species})")
    links_col1.append(f"📚 [AntWiki](https://antwiki.org/wiki/{url_genus}_{url_species})")
    links_col1.append(f"🔬 [AntWeb](https://www.antweb.org/description.do?rank=species&genus={url_genus}&species={url_species}&project=worldants)")
    links_col1.append(f"✅ [AntCat](http://www.antcat.org/catalog/search?utf8=%E2%9C%93&st=m&qq={url_genus}%20{url_species}&commit=Go)")
    links_col1.append(f"✨ [AntScout](https://antscout.com/species/{url_genus.lower()}-{url_species})")

    # Druhý sloupec: Info a Chov
    links_col2.append(f"🛒 [AntCheck](https://antcheck.info/species/{url_genus}_{url_species})")
    
    if ak_data["found"]:
        links_col2.append(f"ℹ️ [AntKeeping.info]({ak_data['url']})")
        
    # Přidán GBIF podle požadavku pod AntKeeping.info
    if gbif_url:
        links_col2.append(f"🌍 [GBIF]({gbif_url})")
    
    # Přidán iNaturalist
    links_col2.append(f"🐦 [iNaturalist](https://www.inaturalist.org/taxa/{url_genus}%20{url_species})")
    
    # Vylepšené hledání odkazu na Formikaristika.cz
    # 1. Zkusíme přesnou shodu: rod-druh
    target_slug = f"{genus.lower()}-{species_name.lower()}"
    # 2. Fallback: rod-sp (např. pro myrmica-sp)
    fallback_slug = f"{genus.lower()}-sp"
    
    formikaristika_url = formikaristika_map.get(target_slug)
    if not formikaristika_url:
        formikaristika_url = formikaristika_map.get(fallback_slug)

    if formikaristika_url:
        links_col2.append(f"📖 [Profil druhu]({formikaristika_url})")
    
    if in_czech:
        links_col2.append(f"🇨🇿 [Rozšíření v ČR](https://portal23.nature.cz/publik_syst/nd_nalez-public.php?akce=view&rfTaxon={url_genus}%20{url_species})")

    # Přidání polí do embedu vedle sebe
    embed.add_field(name="Odkazy", value="\n".join(links_col1), inline=True)
    embed.add_field(name="ㅤ", value="\n".join(links_col2), inline=True)
    embed.set_footer(text="Data z antkeeping.info | Uvedené informace mohou být chybné")

    await interaction.followup.send(embed=embed)