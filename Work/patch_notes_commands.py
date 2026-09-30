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