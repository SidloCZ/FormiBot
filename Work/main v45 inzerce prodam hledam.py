# Tento soubor je hlavním spouštěcím bodem pro Discord bota "FormiBot".
#
# Funkce:
# - Inicializuje klienta Discordu a strom příkazů.
# - Načítá a spravuje konfiguraci (token).
# - Načítá a ukládá data z JSON souborů (skóre, historická data, kvízové otázky).
# - Definuje a registruje hlavní slash příkazy (/ping, /restart, atd.).
# - Spravuje hlavní události bota, jako je on_ready.
# - NOVINKA: Zaregistrováno trvalé tlačítko (AdInteractionView) pro inzerci.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, matplotlib, tabulate.
# - Lokální moduly (mohou být umístěny v Příkazy.):
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