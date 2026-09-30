# Tento soubor definuje skupinu příkazů `/checklist` pro Discord bota.
# Umožňuje uživatelům vést si osobní seznam ("checklist") druhů mravenců
# nalezených ve volné přírodě, založený na seznamu druhů ČR a SR.
# Nově ukládá i datum a lokalitu nálezu.
#
# Funkce:
# - Načítá master seznam druhů ČR/SR ze souboru `checklist_species_czsk.json`.
# - Načítá a ukládá uživatelské checklisty do `user_checklist_data.json`.
# - Příkaz `/checklist zapsat`: Otevře modální okno pro zadání druhu, data a lokality.
# - Příkaz `/checklist odebrat`: Odebere druh z osobního checklistu.
# - Příkaz `/checklist seznam`: Zobrazí jeden kompletní seznam nalezených (s detaily) i chybějících druhů.
#
# Závislosti:
# - discord.py, json
# - Lokální moduly: utils.py (pro PaginatorView)

import discord
from discord import app_commands, ui
import json
import re
from typing import List, Dict, Optional

# Import PaginatorView z utils.py
from utils import PaginatorView

# --- Globální proměnné ---
checklist_species: List[str] = []
# Struktura: {"user_id": {"Species Name": {"date": "...", "location": "..."}}}
user_checklists: Dict[str, Dict[str, Dict[str, str]]] = {}

# --- Názvy souborů ---
MASTER_LIST_FILE = 'Soubory/checklist_species_czsk.json'
USER_CHECKLISTS_FILE = 'Soubory/user_checklist_data.json'

# --- Pomocné funkce ---

def load_checklist_species():
    """Načte master seznam druhů ČR/SR ze souboru JSON."""
    global checklist_species
    try:
        with open(MASTER_LIST_FILE, 'r', encoding='utf-8') as f:
            checklist_species = json.load(f)
            # Seřadíme seznam hned po načtení
            checklist_species.sort()
            print(f"Úspěšně načten master checklist ČR/SR s {len(checklist_species)} druhy.")
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"CHYBA: Soubor '{MASTER_LIST_FILE}' nenalezen nebo je poškozený.")
        checklist_species = []

def load_user_checklists():
    """Načte uživatelské checklisty (s detaily) ze souboru JSON."""
    global user_checklists
    try:
        with open(USER_CHECKLISTS_FILE, 'r', encoding='utf-8') as f:
            user_checklists = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor '{USER_CHECKLISTS_FILE}' nenalezen, vytvářím novou databázi.")
        user_checklists = {}

def save_user_checklists():
    """Uloží aktuální stav uživatelských checklistů (s detaily) do souboru JSON."""
    try:
        with open(USER_CHECKLISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_checklists, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání uživatelských checklistů: {e}")

def format_ant_name(rod: str, druh: str) -> str:
    """Formátuje jméno mravence (Rod druh, Rod sp., Rod cf. druh)."""
    return f"{rod.capitalize()} {druh.lower()}"

def get_master_name_from_input(ant_name_lower: str) -> Optional[str]:
    """Najde a vrátí správně kapitalizované jméno z master seznamu."""
    for master_name in checklist_species:
        if master_name.lower() == ant_name_lower:
            return master_name
    return None

# --- Modální okno pro zadání nálezu ---

class ChecklistEntryModal(ui.Modal, title="Zapsat nález do checklistu"):
    def __init__(self, cog_instance: 'ChecklistCommands'):
        super().__init__(timeout=None)
        self.cog = cog_instance

    species_input = ui.TextInput(
        label="Nalezený druh (formát: Rod druh)",
        placeholder="Např. Camponotus ligniperda",
        required=True,
        style=discord.TextStyle.short
    )
    
    date_input = ui.TextInput(
        label="Datum nálezu (nepovinné)",
        placeholder="Např. 10. 5. 2024",
        required=False,
        style=discord.TextStyle.short
    )
    
    location_input = ui.TextInput(
        label="Lokalita nálezu (nepovinné)",
        placeholder="Např. Pálava, u cesty",
        required=False,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        species_raw = self.species_input.value.strip()
        
        # Jednoduché parsování "Rod druh"
        parts = species_raw.split(maxsplit=1)
        if len(parts) != 2:
            await interaction.response.send_message(f"Neplatný formát druhu. Zadejte ho prosím jako 'Rod druh' (např. 'Formica rufa').", ephemeral=True)
            return

        ant_name = format_ant_name(parts[0], parts[1])
        master_name = get_master_name_from_input(ant_name.lower())

        if not master_name:
            await interaction.response.send_message(f"Druh **{ant_name}** není na oficiálním seznamu volně žijících druhů ČR/SR.", ephemeral=True)
            return

        # Inicializace checklistu pro uživatele
        if user_id not in user_checklists:
            user_checklists[user_id] = {}

        # Přidání druhu, pokud tam ještě není
        if master_name in user_checklists[user_id]:
            # Možnost budoucího vylepšení: zeptat se, zda chce aktualizovat data
            await interaction.response.send_message(f"Druh **{master_name}** už máš ve svém checklistu.", ephemeral=True)
        else:
            entry_data = {
                "date": self.date_input.value or "Nezadáno",
                "location": self.location_input.value or "Nezadáno"
            }
            user_checklists[user_id][master_name] = entry_data
            save_user_checklists()
            
            progress = len(user_checklists[user_id])
            total = len(checklist_species)
            await interaction.response.send_message(f"Úspěšně zapsáno: **{master_name}**! Tvůj progress: **{progress} / {total}** druhů.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Chyba v ChecklistEntryModal: {error}")
        await interaction.response.send_message("Oups, něco se pokazilo při odesílání formuláře.", ephemeral=True)


# --- Třída pro zapouzdření příkazů (nutné pro modal) ---
class ChecklistCommands:
    def __init__(self, tree: app_commands.CommandTree):
        self.tree = tree
        self.group = checklist_group
        self.register_commands()

    def register_commands(self):
        # Příkazy jsou již definovány s dekorátorem @checklist_group.command
        # Tato metoda je zde pro přehlednost a budoucí rozšíření
        pass

# Vytvoření skupiny příkazů
checklist_group = app_commands.Group(name="checklist", description="Správa tvého checklistu nalezených druhů mravenců ČR/SR.")

@checklist_group.command(name="zapsat", description="Otevře okno pro zapsání nálezu mravence z ČR/SR.")
async def checklist_zapsat(interaction: discord.Interaction):
    if not checklist_species:
        await interaction.response.send_message("Chyba: Master seznam druhů ČR/SR není načten.", ephemeral=True)
        return
    
    # Předání instance 'self' není nutné, pokud modal nepotřebuje přistupovat k ničemu z vnější třídy
    # Ale pro budoucí použití (pokud bychom chtěli cog) je to dobrá praxe.
    # Zde prostě vytvoříme instanci modalu.
    modal = ChecklistEntryModal(cog_instance=None) # 'cog_instance' zde není potřeba
    await interaction.response.send_modal(modal)


@checklist_group.command(name="odebrat", description="Odebere druh mravence z tvého checklistu.")
@app_commands.describe(rod="Rod mravence", druh="Druh mravence")
async def checklist_odebrat(interaction: discord.Interaction, rod: str, druh: str):
    user_id = str(interaction.user.id)
    ant_name = format_ant_name(rod, druh)
    
    if user_id not in user_checklists or not user_checklists[user_id]:
        await interaction.response.send_message("Tvůj checklist je prázdný.", ephemeral=True)
        return

    master_name_to_remove = get_master_name_from_input(ant_name.lower())
            
    if master_name_to_remove and master_name_to_remove in user_checklists[user_id]:
        del user_checklists[user_id][master_name_to_remove]
        save_user_checklists()
        
        progress = len(user_checklists[user_id])
        total = len(checklist_species)
        await interaction.response.send_message(f"Druh **{master_name_to_remove}** odebrán z checklistu. Tvůj progress: **{progress} / {total}**.")
    else:
        await interaction.response.send_message(f"Druh **{ant_name}** nebyl v tvém checklistu nalezen.", ephemeral=True)

@checklist_group.command(name="seznam", description="Zobrazí kompletní checklist nalezených i chybějících druhů ČR/SR.")
@app_commands.describe(
    uzivatel="Uživatel, jehož checklist chceš zobrazit (volitelné)."
)
async def checklist_seznam(interaction: discord.Interaction, uzivatel: Optional[discord.Member] = None):
    
    target_user = uzivatel or interaction.user
    user_id = str(target_user.id)
    
    found_species_data = user_checklists.get(user_id, {})
    found_species_set = set(found_species_data.keys())
    total_species = len(checklist_species)
    progress_percent = (len(found_species_set) / total_species * 100) if total_species > 0 else 0

    # Seznam k zobrazení je vždy kompletní master list
    display_list = checklist_species # Ta je již seřazena při načtení
    
    title = f"Checklist ČR/SR pro {target_user.display_name}"
    description_prefix = f"**Progress: {len(found_species_set)} / {total_species}** ({progress_percent:.1f}%)\n\n"

    if not display_list:
         await interaction.response.send_message("Chyba: Master seznam druhů ČR/SR není načten.", ephemeral=True)
         return

    pages = []
    current_page_content = ""
    items_per_page = 20 # Můžeme zvýšit, chybějící jsou krátké

    for i, species_name in enumerate(display_list):
        
        if species_name in found_species_set:
            # Nalezený druh
            entry = found_species_data.get(species_name, {})
            date_str = f" ({entry['date']})" if entry.get('date') and entry['date'] != 'Nezadáno' else ""
            loc_str = f" - *{entry['location']}*" if entry.get('location') and entry['location'] != 'Nezadáno' else ""
            current_page_content += f"✅ **{species_name}**{date_str}{loc_str}\n"
        else:
            # Chybějící druh
            current_page_content += f"❌ {species_name}\n"

        if (i + 1) % items_per_page == 0 or i == len(display_list) - 1:
            embed = discord.Embed(
                title=title,
                description=description_prefix + current_page_content,
                color=discord.Color.blue()
            )
            if target_user.avatar:
                embed.set_thumbnail(url=target_user.avatar.url)
            embed.set_footer(text=f"Celkem druhů na seznamu: {len(display_list)} | Zdroj: Werner et al. (2018) + SR druhy")
            pages.append(embed)
            current_page_content = ""

    if not pages:
        await interaction.response.send_message("Něco se pokazilo při generování seznamu.")
        return

    view = PaginatorView(pages, interaction)
    await interaction.response.send_message(embed=pages[0], view=view)
    view.message = await interaction.original_response()