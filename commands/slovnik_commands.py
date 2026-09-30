import discord
from discord import app_commands, ui
import requests
from bs4 import BeautifulSoup
import difflib
import re
from typing import List, Dict, Any, Optional

from utils import PaginatorView

SLOVNIK_URL = "https://formikaristika.wordpress.com/mravenci/slovnik/"
dictionary_data: List[Dict[str, str]] = []

async def load_dictionary_data():
    """Načte a parsuje data ze slovníku na Formikaristika CZ."""
    global dictionary_data
    dictionary_data = []

    try:
        response = requests.get(SLOVNIK_URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        table = soup.find("table")
        if not table:
            print("CHYBA: Tabulka se slovníkem nebyla nalezena na stránce.")
            return

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                term = cols[0].get_text(strip=True)
                explanation = cols[1].get_text(strip=True)
                image_url = None

                if len(cols) >= 3:
                    img_tag = cols[2].find("img")
                    if img_tag and img_tag.get("src"):
                        image_url = img_tag["src"]
                    elif cols[2].find("a", href=True):
                        img_in_a = cols[2].find("a").find("img")
                        if img_in_a and img_in_a.get("src"):
                            image_url = img_in_a["src"]
                        else:
                            link_to_image = cols[2].find("a", href=True)
                            if link_to_image and (".jpg" in link_to_image["href"] or ".png" in link_to_image["href"]):
                                image_url = link_to_image["href"]

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
    def __init__(self, terms: List[Dict[str, str]], original_interaction: discord.Interaction, timeout=180):
        super().__init__(timeout=timeout)
        self.terms = terms
        self.original_interaction = original_interaction

        options = []
        for i, term_data in enumerate(self.terms):
            options.append(discord.SelectOption(label=term_data["term"][:100], value=str(i)))
        
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
        if interaction.user != self.original_interaction.user:
            await interaction.response.send_message("Tuto navigaci může ovládat pouze původní uživatel.", ephemeral=True)
            return False
        return True

    async def on_select_term(self, interaction: discord.Interaction):
        selected_index = int(interaction.data["values"][0])
        selected_term_data = self.terms[selected_index]
        await display_dictionary_term(interaction, selected_term_data, is_redirect=False)
        self.stop()

async def display_dictionary_term(interaction: discord.Interaction, term_data: Dict[str, str], is_redirect: bool = False, original_term: Optional[str] = None):
    embed_title = f"Slovník: {original_term}" if is_redirect and original_term else f"Slovník: {term_data['term']}"
    embed_description = term_data["explanation"]
    embed_color = discord.Color.blue()
    embed_footer_text = "Zdroj: Formikaristika CZ"

    if is_redirect and original_term:
        embed_description = f"**Vysvětlení tohoto termínu je součástí termínu: {term_data['term']}**\n\n" + embed_description
        embed_color = discord.Color.gold()

    embed = discord.Embed(
        title=embed_title,
        description=embed_description,
        color=embed_color
    )
    if term_data["image_url"]:
        embed.set_image(url=term_data["image_url"])
        embed_footer_text += f" | Obrázek: {term_data['term']}"
    
    embed.set_footer(text=embed_footer_text)

    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=None)
    else:
        await interaction.followup.send(embed=embed)

slovnik_group = app_commands.Group(name="slovnik", description="Vyhledávání termínů ze slovníku Formikaristika CZ.")

@slovnik_group.command(name="hledat", description="Vyhledá termín ve slovníku Formikaristika CZ.")
@app_commands.describe(term="Termín, který chcete vyhledat.")
async def slovnik_hledat(interaction: discord.Interaction, term: str):
    await interaction.response.defer(ephemeral=False)

    if not dictionary_data:
        await load_dictionary_data()

    if not dictionary_data:
        await interaction.followup.send("Slovník se nepodařilo načíst. Zkuste to prosím později.", ephemeral=True)
        return

    normalized_term = term.lower().strip()

    exact_match = None
    for item in dictionary_data:
        if item["term"].lower() == normalized_term:
            exact_match = item
            break

    if exact_match:
        viz_match = re.match(r"viz\s+(.+)", exact_match["explanation"].lower())
        if viz_match:
            target_term_raw = viz_match.group(1).strip()
            target_term_data = None
            for item in dictionary_data:
                if item["term"].lower() == target_term_raw:
                    target_term_data = item
                    break
            
            if target_term_data:
                await display_dictionary_term(interaction, target_term_data, is_redirect=True, original_term=exact_match["term"])
            else:
                embed = discord.Embed(
                    title=f"Slovník: {exact_match['term']}",
                    description=f"Vysvětlení tohoto termínu odkazuje na: **{target_term_raw.capitalize()}**.\nBohužel, cílový termín nebyl nalezen ve slovníku.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Zdroj: Formikaristika CZ")
                await interaction.followup.send(embed=embed)
        else:
            await display_dictionary_term(interaction, exact_match)
    else:
        all_terms_raw = [item["term"] for item in dictionary_data]
        found_terms_data = []
        found_terms_names = set()

        close_matches_difflib = difflib.get_close_matches(normalized_term, all_terms_raw, n=10, cutoff=0.5)
        for match_term_str in close_matches_difflib:
            for item in dictionary_data:
                if item["term"] == match_term_str and item["term"] not in found_terms_names:
                    found_terms_data.append(item)
                    found_terms_names.add(item["term"])
                    break
        
        for item in dictionary_data:
            if normalized_term in item["term"].lower() and item["term"] not in found_terms_names:
                found_terms_data.append(item)
                found_terms_names.add(item["term"])
        
        found_terms_data.sort(key=lambda x: (
            0 if x["term"].lower().startswith(normalized_term) else
            1 if normalized_term in x["term"].lower() else
            2,
            x["term"].lower()
        ))

        if found_terms_data:
            if len(found_terms_data) == 1:
                single_match = found_terms_data[0]
                viz_match = re.match(r"viz\s+(.+)", single_match["explanation"].lower())
                if viz_match:
                    target_term_raw = viz_match.group(1).strip()
                    target_term_data = None
                    for item in dictionary_data:
                        if item["term"].lower() == target_term_raw:
                            target_term_data = item
                            break
                    
                    if target_term_data:
                        await display_dictionary_term(interaction, target_term_data, is_redirect=True, original_term=single_match["term"])
                    else:
                        embed = discord.Embed(
                            title=f"Slovník: {single_match['term']} (Nejpodobnější shoda)",
                            description=f"Vysvětlení tohoto termínu odkazuje na: **{target_term_raw.capitalize()}**.\nBohužel, cílový termín nebyl nalezen ve slovníku.",
                            color=discord.Color.red()
                        )
                        embed.set_footer(text="Zdroj: Formikaristika CZ")
                        await interaction.followup.send(embed=embed)
                else:
                    await display_dictionary_term(interaction, single_match)
            else:
                view = DictionaryResultView(found_terms_data[:5], interaction)
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

    sorted_terms = sorted(dictionary_data, key=lambda x: x["term"].lower())

    pages: List[discord.Embed] = []
    current_page_description = ""
    terms_per_page = 20

    for i, item in enumerate(sorted_terms):
        current_page_description += f"• **{item['term']}**\n"
        if (i + 1) % terms_per_page == 0 or i == len(sorted_terms) - 1:
            embed = discord.Embed(
                title="Slovník pojmů Formikaristika CZ",
                description=current_page_description,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Zdroj: Formikaristika CZ | Použijte /slovnik hledat <termín> pro detailní informace.")
            pages.append(embed)
            current_page_description = ""

    if not pages:
        await interaction.followup.send("Slovník je prázdný.", ephemeral=True)
        return

    view = PaginatorView(pages, interaction)
    message = await interaction.followup.send(embed=pages[0], view=view)
    view.message = message
