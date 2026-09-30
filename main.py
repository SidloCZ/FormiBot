import discord
from discord import app_commands
import os
import json
import time
import asyncio
import random
import datetime
import sys
from typing import Optional

from config import (
    DISCORD_TOKEN,
    RESTART_ROLE_ID,
    STARTUP_CHANNEL_ID,
    BRAINROT_CHANNEL_ID,
    SCORES_FILE,
    HISTORICAL_ANTS_FILE,
    QUIZ_QUESTIONS_FILE,
    MOD_ROLE_IDS
)
from utils import PaginatorView

# Příkazové moduly
from commands.wishlist_commands import wishlist_group, load_wishlists, save_wishlists
from commands.formikaristika_commands import FormikaristikaCommands
from commands.statistiky_commands import statistiky_group
from commands.quiz_commands import QuizCommands
from commands.isop_commands import isop_group
from commands.slovnik_commands import slovnik_group, load_dictionary_data
from commands.patch_notes_commands import patch_notes_group, load_patch_notes
from commands.fauna_commands import fauna_group
from commands.map_commands import map_command
from commands.seznam_commands import seznam_group, load_user_ants, user_ants, save_user_ants, load_species_database
from commands.udalosti_commands import udalosti_group, setup_udalosti
from commands.inzerce_commands import inzerce_group, setup_inzerce, process_chat_message, AdInteractionView
from commands.chov_commands import chov_command, load_chov_data
from commands.checklist_commands import checklist_group, load_checklist_species, load_user_checklists, save_user_checklists
from commands import brainrot_startup

def load_quiz_questions() -> dict:
    """Načte otázky pro kvíz z JSON souboru."""
    try:
        with open(QUIZ_QUESTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {QUIZ_QUESTIONS_FILE} nenalezen nebo poškozen, inicializuji prázdný slovník.")
        return {}

quiz_questions = load_quiz_questions()

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

scores = {
    "total_scores": {},
    "weekly_scores": {}
}

def save_scores():
    """Uloží aktuální stav skóre do souboru."""
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání skóre: {e}")

def load_scores():
    """Načte skóre ze souboru při startu bota."""
    global scores
    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            loaded_scores = json.load(f)
            
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
        print(f"Soubor {SCORES_FILE} nenalezen nebo poškozen. Inicializuji novou databázi skóre.")
        scores = {"total_scores": {}, "weekly_scores": {}}

historical_ants_data = {}

def save_historical_ants_data():
    """Uloží aktuální historická data do souboru."""
    try:
        with open(HISTORICAL_ANTS_FILE, "w", encoding="utf-8") as f:
            json.dump(historical_ants_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání historických dat mravenců: {e}")

def load_historical_ants_data():
    """Načte historická data mravenců ze souboru."""
    global historical_ants_data
    try:
        with open(HISTORICAL_ANTS_FILE, "r", encoding="utf-8") as f:
            historical_ants_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {HISTORICAL_ANTS_FILE} nenalezen, inicializuji novou databázi.")
        historical_ants_data = {}

async def periodic_save_historical_data():
    await client.wait_until_ready()
    while not client.is_closed():
        current_date = datetime.date.today().isoformat()
        last_saved_date = max(historical_ants_data.keys()) if historical_ants_data else None

        should_save = True
        if last_saved_date:
            try:
                last_date_obj = datetime.date.fromisoformat(last_saved_date)
                if (datetime.date.today() - last_date_obj).days < 60:
                    should_save = False
            except ValueError:
                pass

        if should_save:
            print(f"Ukládám historická data pro datum: {current_date}")
            historical_ants_data[current_date] = user_ants.copy()
            save_historical_ants_data()
        
        await asyncio.sleep(60 * 60 * 24 * 60)

def has_role_by_id(member: discord.Member, role_id: int) -> bool:
    """Zkontroluje, zda má člen serveru danou roli podle ID."""
    return any(role.id == role_id for role in member.roles)

@client.event
async def on_ready():
    """Inicializace bota po úspěšném připojení k Discordu."""
    print("Načítám data modulů...", flush=True)
    load_scores()
    load_species_database()
    load_user_ants() 
    load_wishlists()
    load_historical_ants_data()
    load_chov_data()
    load_checklist_species()
    load_user_checklists()
    await load_dictionary_data() 
    load_patch_notes() 
    
    client.user_ants = user_ants 
    client.historical_ants_data = historical_ants_data

    print("Inicializuji příkazové skupiny...", flush=True)
    formikaristika_group = FormikaristikaCommands(client)
    await formikaristika_group.on_ready() 
    
    tree.add_command(wishlist_group)
    tree.add_command(formikaristika_group) 
    tree.add_command(statistiky_group)
    tree.add_command(isop_group)
    tree.add_command(slovnik_group)
    tree.add_command(patch_notes_group) 
    tree.add_command(fauna_group) 
    tree.add_command(map_command)
    tree.add_command(seznam_group) 
    tree.add_command(udalosti_group)
    tree.add_command(inzerce_group)
    tree.add_command(chov_command)
    tree.add_command(checklist_group)

    setup_inzerce(client) 
    client.add_view(AdInteractionView())
    setup_udalosti(client)
    
    client.quiz_commands = QuizCommands(client, tree, scores, save_scores, quiz_questions)

    await tree.sync()
    client.loop.create_task(periodic_save_historical_data())

    print(f"Přihlášen jako {client.user} (ID: {client.user.id})", flush=True)
    print("Bot je plně připraven a příkazy jsou synchronizovány.", flush=True)

    target_channel = client.get_channel(STARTUP_CHANNEL_ID)
    if target_channel and isinstance(target_channel, discord.TextChannel):
        await target_channel.send("FormiBot byl úspěšně spuštěn.")
    
    brainrot_startup.start_brainrot_timer(client, BRAINROT_CHANNEL_ID)

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Listener pro reakce delegující zpracování na QuizCommands."""
    if hasattr(client, 'quiz_commands'):
        await client.quiz_commands.on_raw_reaction_add(payload)

@client.event
async def on_message(message: discord.Message):
    """Zpracování zpráv pro inzerci."""
    await process_chat_message(message)

@tree.command(name="restart", description="Restartuje bota (pouze pro oprávněné role).")
async def restart_command(interaction: discord.Interaction):
    if not isinstance(interaction.user, discord.Member) or not has_role_by_id(interaction.user, RESTART_ROLE_ID):
        await interaction.response.send_message("Nemáš oprávnění k použití tohoto příkazu.", ephemeral=True)
        return

    await interaction.channel.send("Bot se aktuálně ukládá a nebude chvilku fungovat. Prosím, vyčkejte.")

    save_scores()
    save_user_ants()
    save_wishlists()
    save_historical_ants_data()
    save_user_checklists()
    if hasattr(client, 'quiz_commands'):
        client.quiz_commands.save_suggestions()
        client.quiz_commands.save_quiz_questions()
    
    print("Všechna data uložena. Vypínám bota pro restart.")
    await interaction.channel.send("Všechna data byla uložena. Vypínám bota pro restart.")
    await client.close()
    sys.exit(0)

@tree.command(name="ping", description="Zobrazí latenci bota.")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    if latency <= 50:
        color = 0x44ff44
    elif latency <= 100:
        color = 0xffd000
    elif latency <= 200:
        color = 0xff6600
    else:
        color = 0x990000

    embed = discord.Embed(
        title="Odezva bota",
        description=f"Aktuální odezva je **{latency}**\u00A0ms.",
        color=color
    )
    await interaction.response.send_message(embed=embed)

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
            embed = discord.Embed(
                title="Dostupné příkazy bota",
                description="Seznam všech dostupných příkazů:",
                color=discord.Color.gold()
            )
            for name, value in current_page_fields:
                embed.add_field(name=name, value=value, inline=False)
            pages.append(embed)
            current_page_fields = []

    view = PaginatorView(pages, interaction)
    await interaction.response.send_message(embed=pages[0], view=view)
    view.message = await interaction.original_response()

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("CHYBA: Discord token nebyl nalezen. Zkontrolujte soubor .env nebo token.txt.")
        sys.exit(1)
    
    print("Spouštím FormiBotV2...")
    client.run(DISCORD_TOKEN)
