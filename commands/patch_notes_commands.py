import discord
from discord import app_commands
import json
import datetime
from typing import List, Dict, Any

from utils import PaginatorView
from config import get_data_path

PATCH_NOTES_FILE = get_data_path("patch_notes.json")
patch_notes_data: List[Dict[str, Any]] = []

def load_patch_notes():
    """Načte poznámky k patchům z JSON souboru."""
    global patch_notes_data
    try:
        with open(PATCH_NOTES_FILE, "r", encoding="utf-8") as f:
            patch_notes_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"CHYBA: Soubor '{PATCH_NOTES_FILE}' nenalezen nebo je poškozený. Vytvářím prázdný seznam patchů.")
        patch_notes_data = []

# Načteme patche hned při importu modulu
load_patch_notes()

patch_notes_group = app_commands.Group(name="patch_notes", description="Zobrazuje historii změn a aktualizací bota.")

@patch_notes_group.command(name="zobrazit", description="Zobrazí historii změn bota.")
async def patch_notes_zobrazit(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    if not patch_notes_data:
        await interaction.followup.send("Zatím nejsou k dispozici žádné poznámky k patchům.", ephemeral=True)
        return

    pages: List[discord.Embed] = []

    for patch in patch_notes_data:
        version = patch.get("version", "Neznámá verze")
        date_str = patch.get("date", "Neznámé datum")
        changes = patch.get("changes", [])
        image_url = patch.get("image_url")
        
        formatted_date = date_str

        if date_str.lower() != "n/a" and date_str != "Neznámé datum":
            try:
                date_obj = datetime.datetime.fromisoformat(date_str)
                formatted_date = date_obj.strftime("%d.%m.%Y")
            except ValueError:
                pass 
        
        embed = discord.Embed(
            title=f"Patch Notes: Verze {version}",
            description=f"Datum: {formatted_date}\n\n**Změny:**",
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
