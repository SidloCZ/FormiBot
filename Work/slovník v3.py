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
