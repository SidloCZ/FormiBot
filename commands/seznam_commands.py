import discord
from discord import app_commands, ui
import json
import requests
import difflib
import re

from utils import PaginatorView
from config import get_data_path, MOD_ROLE_IDS, MOD_LOG_CHANNEL_ID

user_ants = {}
species_database = {}
species_names = []
unique_genera = set()

USER_ANTS_FILE = get_data_path("user_ants.json")
BOLTON_SPECIES_FILE = get_data_path("bolton_species.json")

def save_user_ants():
    """Uloží aktuální stav chovaných mravenců do souboru user_ants.json."""
    try:
        with open(USER_ANTS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_ants, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání mravenčích druhů: {e}")

def load_user_ants():
    """Načte chované mravence ze souboru user_ants.json."""
    global user_ants
    try:
        with open(USER_ANTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            user_ants.clear()
            user_ants.update(data)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {USER_ANTS_FILE} nenalezen nebo je poškozený. Vytvářím novou databázi mravenců.")
        user_ants.clear()

def load_species_database():
    """Načte databázi druhů a připraví seznam jmen a rodů."""
    global species_database, species_names, unique_genera
    try:
        with open(BOLTON_SPECIES_FILE, "r", encoding="utf-8") as f:
            species_database = json.load(f)
            species_names = list(species_database.keys())
            unique_genera = {name.split()[0] for name in species_names if name}
        print(f"Načteno {len(species_names)} druhů a {len(unique_genera)} unikátních rodů do databáze.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("POZOR: Soubor bolton_species.json nenalezen. Našeptávání a lokální validace poběží v záložním režimu.")
        species_database = {}
        species_names = []
        unique_genera = set()

load_species_database()

def is_moderator(member: discord.Member) -> bool:
    """Zkontroluje, zda má uživatel moderátorská práva."""
    if not isinstance(member, discord.Member):
        return False
    return any(role.id in MOD_ROLE_IDS for role in member.roles)

async def species_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Funkce pro našeptávání druhů z databáze (pro přidávání)."""
    if not current:
        return [app_commands.Choice(name=sp, value=sp) for sp in species_names[:10]]
    
    current_lower = current.lower()
    filtered = [sp for sp in species_names if current_lower in sp.lower()]
    return [app_commands.Choice(name=sp, value=sp) for sp in filtered[:10]]

async def user_species_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Našeptávač pro druhy, které má uživatel aktuálně ve svém osobním seznamu."""
    target_id = str(interaction.user.id)
    
    uzivatel_val = getattr(interaction.namespace, "uzivatel", None)
    if uzivatel_val:
        if hasattr(uzivatel_val, "id"):
            target_id = str(uzivatel_val.id)
        else:
            target_id = str(uzivatel_val)
            
    user_species = list(user_ants.get(target_id, {}).keys())
    
    if not current:
        return [app_commands.Choice(name=sp, value=sp) for sp in user_species[:25]]
        
    current_lower = current.lower()
    filtered = [sp for sp in user_species if current_lower in sp.lower()]
    return [app_commands.Choice(name=sp, value=sp) for sp in filtered[:25]]

async def validate_species_input(input_species: str) -> tuple[bool, str]:
    """
    Validuje zadaný název druhu. Podporuje i obchodní názvy v uvozovkách.
    Vrací: (is_valid, formatted_name_or_error_message)
    """
    trade_name_suffix = ""
    clean_species_input = input_species.strip()
    
    match = re.search(r'\s*(["“].+?["”])\s*$', clean_species_input)
    if match:
        trade_name_suffix = " " + match.group(1) 
        clean_species_input = clean_species_input[:match.start()].strip() 

    parts = clean_species_input.split()
    
    if len(parts) < 2:
        return False, "Název musí obsahovat alespoň Rod a Druh (např. Lasius niger) nebo Rod sp."

    genus = parts[0].capitalize()
    species_part = parts[1].lower()
    
    final_scientific_name = ""
    is_valid = False
    error_msg = ""

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
                error_msg = f"Rod '{genus}' nebyl nalezen v databázi ani na AntCat."

    elif species_part in ["cf.", "nr.", "cf", "nr"]:
        qualifier = species_part.rstrip(".") + "."
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
                found_parts = found_fullname.split(" ", 1)
                if len(found_parts) > 1:
                    found_epithet = found_parts[1]
                    is_valid = True
                    final_scientific_name = f"{corrected_genus} {qualifier} {found_epithet}"
            
            if not is_valid:
                if await check_antcat_validity(corrected_genus, base_species_epithet):
                    is_valid = True
                    final_scientific_name = f"{corrected_genus} {qualifier} {base_species_epithet}"
                else:
                    error_msg = f"Základní druh '{base_species_fullname}' (za {qualifier}) nebyl nalezen v databázi."

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
                is_valid_antcat = await check_antcat_validity(genus, " ".join(parts[1:]))
                if is_valid_antcat:
                    is_valid = True
                    final_scientific_name = reconstructed_input
                else:
                    error_msg = f"Druh '{reconstructed_input}' nebyl nalezen v seznamu ani na AntCat. Zkontrolujte pravopis."

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

class DeleteNewSpeciesView(ui.View):
    """Pohled obsahující tlačítko pro smazání neplatného druhu z mod-chatu."""
    def __init__(self, target_user_id: str, species_name: str):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        self.species_name = species_name

    @ui.button(label="Smazat záznam a upozornit uživatele", style=discord.ButtonStyle.danger)
    async def delete_record(self, interaction: discord.Interaction, button: ui.Button):
        if not is_moderator(interaction.user):
            await interaction.response.send_message("Nemáte oprávnění smazat tento záznam.", ephemeral=True)
            return

        record_deleted = False
        if self.target_user_id in user_ants and self.species_name in user_ants[self.target_user_id]:
            del user_ants[self.target_user_id][self.species_name]
            if not user_ants[self.target_user_id]:
                del user_ants[self.target_user_id]
            save_user_ants()
            record_deleted = True

        dm_sent = False
        try:
            target_user = await interaction.client.fetch_user(int(self.target_user_id))
            if target_user:
                await target_user.send(
                    f"**Upozornění ze serveru:**\n"
                    f"Moderátor **{interaction.user.display_name}** ti ze seznamu smazal záznam o druhu **{self.species_name}**.\n"
                    f"Tento druh na serveru zatím nikdo neměl a po kontrole bylo zjištěno, že se jedná o překlep, nesmyslný záznam, nebo druh, který nelze chovat. Pokud se jedná o omyl z naší strany, kontaktuj prosím moderátory."
                )
                dm_sent = True
        except discord.Forbidden:
            pass 
        except Exception as e:
            print(f"Chyba při odesílání DM uživateli {self.target_user_id}: {e}")

        button.disabled = True
        button.label = "Záznam smazán"
        button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        
        status_msg = f"Záznam **{self.species_name}** byl vymazán."
        if dm_sent:
            status_msg += " Uživateli byla úspěšně odeslána soukromá zpráva."
        else:
            status_msg += " Uživateli se nepodařilo odeslat zprávu (má je zřejmě zablokované)."
            
        await interaction.followup.send(status_msg)

seznam_group = app_commands.Group(name="seznam", description="Správa chovaných druhů mravenců.")

@seznam_group.command(name="pridat", description="Přidá druh do seznamu. Zadej 0 pro přidání do historie (vlastnil jsem).")
@app_commands.describe(species="Název druhu (např. Lasius niger)", number="Počet kolonií (0 = v minulosti, 1+ = aktuální)", uzivatel="Volitelné: Přidat druh jinému uživateli (jen moderátoři).")
@app_commands.autocomplete(species=species_autocomplete)
async def seznam_pridat(interaction: discord.Interaction, species: str, number: int = 1, uzivatel: discord.Member = None):
    target_user = uzivatel or interaction.user
    
    if uzivatel and target_user != interaction.user:
        if not is_moderator(interaction.user):
            await interaction.response.send_message("Nemáš oprávnění přidávat druhy do cizích seznamů.", ephemeral=True)
            return

    user_id = str(target_user.id)
    MAX_COLONIES_PER_SPECIES = 25
    
    if number < 0:
        await interaction.response.send_message("Počet kolonií nesmí být záporný.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=False if (uzivatel and target_user != interaction.user) else True)

    is_valid, result = await validate_species_input(species)
    
    if not is_valid:
        await interaction.followup.send(f"**Chyba v názvu:** {result}")
        return

    formatted_ant = result

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
            f"**Limit překročen!**\n"
            f"Maximální povolený počet kolonií jednoho druhu je **{MAX_COLONIES_PER_SPECIES}**.\n"
            f"Aktuálně je v seznamu: {current_count}. Pokus o přidání: {number}.\n"
            f"Zbývá místa: {max(0, MAX_COLONIES_PER_SPECIES - current_count)}."
        )
        return
    
    user_ants[user_id][formatted_ant] = new_total
    
    msg = ""
    clean_input = species.strip().lower()
    clean_result = formatted_ant.strip().lower()
    
    if clean_input != clean_result:
        msg = f"Název upraven na: **{formatted_ant}**\n"
        
    target_mention = "" if target_user == interaction.user else f"uživateli {target_user.mention} "
        
    if new_total > 0:
        action_msg = f"Přidáno {number} kolonií" if number > 0 else "Seznam aktualizován"
        await interaction.followup.send(f"{msg}{action_msg} {target_mention}pro **{formatted_ant}**. Celkem: {user_ants[user_id][formatted_ant]}.")
    else:
        await interaction.followup.send(f"{msg}Druh **{formatted_ant}** přidán {target_mention}do historie (stav: 0 kolonií).")
    
    save_user_ants()

    if is_new_to_server:
        mod_channel = interaction.client.get_channel(MOD_LOG_CHANNEL_ID)
        if mod_channel:
            embed = discord.Embed(
                title="Upozornění: Nový druh na serveru!",
                description=f"Uživatel {target_user.mention} má v seznamu nově druh **{formatted_ant}**, který do teď nikdo jiný na serveru neměl.\n\nProsím o kontrolu, zda se nejedná o překlep nebo nesmyslný záznam.",
                color=discord.Color.yellow()
            )
            view = DeleteNewSpeciesView(user_id, formatted_ant)
            await mod_channel.send(embed=embed, view=view)

@seznam_group.command(name="smazat", description="Úplně vymaže druh ze seznamu i z historie.")
@app_commands.describe(species="Druh mravence k úplnému smazání", uzivatel="Volitelné: Smazat druh jinému uživateli (jen moderátoři).")
@app_commands.autocomplete(species=user_species_autocomplete) 
async def seznam_smazat(interaction: discord.Interaction, species: str, uzivatel: discord.Member = None):
    target_user = uzivatel or interaction.user
    is_mod_action = bool(uzivatel and target_user != interaction.user)
    
    if is_mod_action and not is_moderator(interaction.user):
        await interaction.response.send_message("Nemáš oprávnění mazat druhy z cizích seznamů.", ephemeral=True)
        return

    user_id = str(target_user.id)
    
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
        msg = (
            f"Uživatel **{target_user.display_name}** nemá druh **{species}** ve svém seznamu."
            if is_mod_action
            else f"Druh **{species}** ve svém seznamu nemáš."
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return
    
    del user_ants[user_id][found_key]
    if not user_ants[user_id]:
        del user_ants[user_id]
    save_user_ants()
    
    if is_mod_action:
        try:
            await target_user.send(f"Moderátor **{interaction.user.display_name}** odstranil druh **{found_key}** ze tvého seznamu.")
        except discord.Forbidden:
            pass 
        await interaction.response.send_message(f"Druh **{found_key}** byl kompletně odstraněn ze záznamů uživatele {target_user.display_name}.")
    else:
        await interaction.response.send_message(f"Druh **{found_key}** byl kompletně odstraněn ze záznamů.")

@seznam_group.command(name="odebrat_pocet", description="Odebere počet kolonií. Při dosažení 0 přesune do historie.")
@app_commands.describe(species="Druh mravence", number="Počet kolonií k odebrání", uzivatel="Volitelné: Upravit jinému uživateli (jen moderátoři).")
@app_commands.autocomplete(species=user_species_autocomplete)
async def seznam_odebrat_pocet(interaction: discord.Interaction, species: str, number: int = 1, uzivatel: discord.Member = None):
    target_user = uzivatel or interaction.user
    is_mod_action = bool(uzivatel and target_user != interaction.user)
    
    if is_mod_action and not is_moderator(interaction.user):
        await interaction.response.send_message("Nemáš oprávnění upravovat cizí seznamy.", ephemeral=True)
        return

    user_id = str(target_user.id)

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
        msg = (
            f"Uživatel **{target_user.display_name}** nemá druh **{species}** ve svém seznamu."
            if is_mod_action
            else f"Druh **{species}** ve svém seznamu nemáš."
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return

    current_count = user_ants[user_id][found_key]
    action_description = ""
    
    if number >= current_count:
        user_ants[user_id][found_key] = 0
        action_description = f"Všechny kolonie druhu **{found_key}** byly odebrány. Druh přesunut do historie (0 kolonií)."
    else:
        user_ants[user_id][found_key] -= number
        action_description = f"Odebráno {number} kolonií {found_key}. Zbývá: {user_ants[user_id][found_key]}."
    
    save_user_ants()

    if is_mod_action:
        try:
            await target_user.send(f"Moderátor **{interaction.user.display_name}** upravil tvůj seznam: {action_description}")
        except discord.Forbidden:
            pass
        await interaction.response.send_message(f"Úprava seznamu uživatele {target_user.display_name}: {action_description}")
    else:
        await interaction.response.send_message(action_description)

@seznam_group.command(name="zobrazit", description="Zobrazí seznam. Aktivní kolonie jsou nahoře.")
@app_commands.describe(uzivatel="Uživatel, jehož seznam chceš zobrazit (volitelné).")
async def seznam_zobrazit(interaction: discord.Interaction, uzivatel: discord.Member = None):
    target_user = uzivatel or interaction.user
    target_user_id = str(target_user.id)

    if target_user_id not in user_ants or not user_ants[target_user_id]:
        message = f"Uživatel {target_user.mention} nemá žádné mravence v seznamu." if uzivatel else "Tvůj seznam je prázdný."
        await interaction.response.send_message(message)
        return

    ant_list = user_ants[target_user_id]
    
    active_ants = {k: v for k, v in ant_list.items() if v > 0}
    history_ants = {k: v for k, v in ant_list.items() if v == 0}
    
    sorted_active = sorted(active_ants.items(), key=lambda item: item[0].lower())
    sorted_history = sorted(history_ants.items(), key=lambda item: item[0].lower())
    
    combined_items = sorted_active + sorted_history
    
    pages = []
    current_page_fields = []
    
    total_active_colonies = sum(active_ants.values())
    total_active_types = len(active_ants)
    total_history_types = len(history_ants)
    
    MAX_FIELDS_PER_PAGE = 24 

    for i, (cmd_name, count) in enumerate(combined_items):
        field_name = cmd_name
        value_text = f"{count} kol." if count > 0 else "V minulosti"
        
        current_page_fields.append((field_name, value_text))
        
        if len(current_page_fields) == MAX_FIELDS_PER_PAGE or i == len(combined_items) - 1:
            embed = discord.Embed(title=f"Seznam chovaných mravenců: {target_user.display_name}", color=discord.Color.blue())
            if target_user.avatar:
                embed.set_thumbnail(url=target_user.avatar.url)
            
            for ant_field_name, ant_field_val in current_page_fields:
                embed.add_field(name=ant_field_name, value=ant_field_val, inline=True)
            
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
    
    member = interaction.guild.get_member_named(query) if interaction.guild else None
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
            if not user:
                continue
            
            for ant_name, count in ants_data.items():
                if search_term_lower in ant_name.lower(): 
                    if ant_name not in found_ants:
                        found_ants[ant_name] = []
                    
                    status_str = f"({count} kolonií)" if count > 0 else "(V minulosti)"
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
