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