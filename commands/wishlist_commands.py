import discord
from discord import app_commands, ui
import json
from typing import Optional

from utils import PaginatorView
from config import get_data_path
from commands.seznam_commands import validate_species_input, species_autocomplete

wishlists = {}
WISHLISTS_FILE = get_data_path("wishlists.json")

def save_wishlists():
    """Uloží aktuální stav wishlistů do souboru wishlists.json."""
    global wishlists
    try:
        with open(WISHLISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(wishlists, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání wishlistů: {e}")

def load_wishlists():
    """Načte wishlisty ze souboru wishlists.json při startu bota."""
    global wishlists
    try:
        with open(WISHLISTS_FILE, "r", encoding="utf-8") as f:
            wishlists = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {WISHLISTS_FILE} nenalezen nebo je poškozený. Vytvářím novou databázi wishlistů.")
        wishlists = {}

load_wishlists()

class WishlistNotificationView(ui.View):
    """Interaktivní komponenta pro nastavení notifikací wishlistu."""
    def __init__(self, user_id: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.update_buttons()

    def update_buttons(self):
        user_data = wishlists.get(self.user_id, {})
        notif_enabled = user_data.get("notifications", True)
        notify_pref = user_data.get("notify_pref", "public")

        if notif_enabled:
            self.toggle_btn.label = "Notifikace: Zapnuto"
            self.toggle_btn.style = discord.ButtonStyle.success
            self.pref_btn.disabled = False
        else:
            self.toggle_btn.label = "Notifikace: Vypnuto"
            self.toggle_btn.style = discord.ButtonStyle.danger
            self.pref_btn.disabled = True

        if notify_pref == "dm":
            self.pref_btn.label = "Doručení: Soukromá zpráva (DM)"
            self.pref_btn.style = discord.ButtonStyle.primary
        else:
            self.pref_btn.label = "Doručení: Veřejně v kanálu"
            self.pref_btn.style = discord.ButtonStyle.secondary

    @ui.button(label="Notifikace", style=discord.ButtonStyle.secondary, custom_id="toggle_notif")
    async def toggle_btn(self, interaction: discord.Interaction, button: ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Toto menu může ovládat pouze vlastník wishlistu.", ephemeral=True)
            return

        current_state = wishlists[self.user_id].get("notifications", True)
        wishlists[self.user_id]["notifications"] = not current_state
        save_wishlists()

        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @ui.button(label="Způsob doručení", style=discord.ButtonStyle.secondary, custom_id="toggle_pref")
    async def pref_btn(self, interaction: discord.Interaction, button: ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("Toto menu může ovládat pouze vlastník wishlistu.", ephemeral=True)
            return

        current_pref = wishlists[self.user_id].get("notify_pref", "public")
        new_pref = "dm" if current_pref == "public" else "public"
        wishlists[self.user_id]["notify_pref"] = new_pref
        save_wishlists()

        self.update_buttons()
        await interaction.response.edit_message(view=self)

wishlist_group = app_commands.Group(name="wishlist", description="Správa tvého seznamu přání (wishlistu).")

@wishlist_group.command(name="zobrazit", description="Zobrazí tvůj wishlist nebo wishlist jiného uživatele.")
@app_commands.describe(uzivatel="Uživatel, jehož wishlist chceš zobrazit (volitelné).")
async def wishlist_zobrazit(interaction: discord.Interaction, uzivatel: Optional[discord.Member] = None):
    target_user = uzivatel or interaction.user
    user_id = str(target_user.id)

    user_wishlist = wishlists.get(user_id)
    is_locked = user_wishlist.get("locked", False) if user_wishlist else False

    if is_locked and target_user != interaction.user:
        await interaction.response.send_message(f"Wishlist uživatele {target_user.mention} je zamčený.", ephemeral=True)
        return

    if not user_wishlist or not user_wishlist.get("items"):
        message = f"Wishlist uživatele {target_user.mention} je prázdný." if uzivatel else "Tvůj wishlist je prázdný. Přidej si něco pomocí /wishlist pridat."
        await interaction.response.send_message(message, ephemeral=is_locked)
        return

    items = user_wishlist.get("items", [])
    notifications_enabled = user_wishlist.get("notifications", True)
    notify_pref = user_wishlist.get("notify_pref", "public")

    sorted_items = sorted(items, key=lambda x: (x.get("completed", False), x["name"].lower()))

    pages = []
    page_content = ""
    items_on_page = 0
    MAX_ITEMS_PER_PAGE = 15

    for i, item in enumerate(sorted_items):
        name = item.get("name", "Neznámý druh")
        if item.get("completed", False):
            page_content += f"[Splněno] ~~{name}~~\n"
        else:
            page_content += f"• {name}\n"
        
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
                footer_text += "Zamčeno "
            
            if target_user == interaction.user:
                if notifications_enabled:
                    notif_status = "Zapnuto (DM)" if notify_pref == "dm" else "Zapnuto (Veřejně)"
                else:
                    notif_status = "Vypnuto"
                
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
    await interaction.response.send_message(embed=pages[0], view=view, ephemeral=is_locked)
    view.message = await interaction.original_response()

@wishlist_group.command(name="pridat", description="Přidá druh do tvého wishlistu. Použij našeptávač!")
@app_commands.describe(species="Název druhu (např. Lasius niger, Camponotus sp.)")
@app_commands.autocomplete(species=species_autocomplete)
async def wishlist_pridat(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    is_valid, result = await validate_species_input(species)
    if not is_valid:
        await interaction.response.send_message(f"**Chyba v názvu:** {result}", ephemeral=True)
        return
        
    ant_name = result

    if user_id not in wishlists:
        wishlists[user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}

    if any(item["name"] == ant_name for item in wishlists[user_id]["items"]):
        await interaction.response.send_message(f"Druh **{ant_name}** už na tvém wishlistu je.", ephemeral=True)
        return

    wishlists[user_id]["items"].append({"name": ant_name, "completed": False})
    save_wishlists()
    
    msg_prefix = ""
    if species.strip().lower() != ant_name.strip().lower():
        msg_prefix = f"Název upraven na: **{ant_name}**\n"
        
    await interaction.response.send_message(f"{msg_prefix}Přidáno **{ant_name}** do tvého wishlistu.")

@wishlist_group.command(name="splneno", description="Označí druh na tvém wishlistu jako splněný.")
@app_commands.describe(species="Název druhu")
@app_commands.autocomplete(species=species_autocomplete)
async def wishlist_splneno(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    target_name = species
    is_valid, validated_name = await validate_species_input(species)
    if is_valid:
        target_name = validated_name

    if user_id not in wishlists or not wishlists[user_id].get("items"):
        await interaction.response.send_message("Tvůj wishlist je prázdný.", ephemeral=True)
        return

    item_found = False
    for item in wishlists[user_id]["items"]:
        if item["name"].lower() == target_name.lower() or item["name"].lower() == species.lower():
            if item.get("completed", False):
                await interaction.response.send_message(f"Druh **{item['name']}** je již označen jako splněný.", ephemeral=True)
                return
            item["completed"] = True
            target_name = item["name"]
            item_found = True
            break

    if item_found:
        save_wishlists()
        await interaction.response.send_message(f"Druh **{target_name}** byl označen jako splněný na tvém wishlistu.")
    else:
        await interaction.response.send_message(f"Druh **{species}** nebyl nalezen na tvém wishlistu.", ephemeral=True)

@wishlist_group.command(name="zamek", description="Přepne viditelnost tvého wishlistu (zamkne/odemkne).")
async def wishlist_zamek(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id not in wishlists:
        wishlists[user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}

    current_state = wishlists[user_id].get("locked", False)
    new_state = not current_state
    wishlists[user_id]["locked"] = new_state
    save_wishlists()

    if new_state:
        await interaction.response.send_message("Tvůj wishlist byl úspěšně zamčen. Ostatní ho nyní neuvidí.", ephemeral=True)
    else:
        await interaction.response.send_message("Tvůj wishlist byl úspěšně odemčen. Ostatní ho nyní mohou vidět.", ephemeral=True)

@wishlist_group.command(name="odebrat", description="Odebere druh z tvého wishlistu.")
@app_commands.describe(species="Název druhu")
@app_commands.autocomplete(species=species_autocomplete)
async def wishlist_odebrat(interaction: discord.Interaction, species: str):
    user_id = str(interaction.user.id)
    
    target_name = species
    is_valid, validated_name = await validate_species_input(species)
    if is_valid:
        target_name = validated_name

    if user_id not in wishlists or not wishlists[user_id].get("items"):
        await interaction.response.send_message("Tvůj wishlist je prázdný.", ephemeral=True)
        return

    items = wishlists[user_id]["items"]
    initial_len = len(items)
    
    wishlists[user_id]["items"] = [
        item for item in items 
        if item["name"].lower() != target_name.lower() and item["name"].lower() != species.lower()
    ]

    if len(wishlists[user_id]["items"]) < initial_len:
        save_wishlists()
        await interaction.response.send_message(f"Odebráno **{target_name}** z tvého wishlistu.")
    else:
        await interaction.response.send_message(f"Druh **{species}** nebyl na tvém wishlistu nalezen.", ephemeral=True)

@wishlist_group.command(name="notifikace", description="Nastavení notifikací pro inzeráty.")
async def wishlist_notifikace(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if user_id not in wishlists:
        wishlists[user_id] = {"locked": False, "items": [], "notifications": True, "notify_pref": "public"}
        save_wishlists()

    view = WishlistNotificationView(user_id)
    await interaction.response.send_message(
        "Zde si můžeš upravit nastavení upozornění na nové nabídky druhů z tvého wishlistu:",
        view=view,
        ephemeral=True
    )
