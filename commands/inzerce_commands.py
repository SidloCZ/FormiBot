import discord
from discord import app_commands, ui
import json
import datetime
import asyncio
import re
from typing import Optional, List

from config import (
    get_data_path,
    AD_CHANNEL_ID,
    AD_NOTIFICATION_CHANNEL_ID as NOTIFICATION_CHANNEL_ID,
    AD_ROLE_ID,
    MOD_ROLE_IDS
)
from commands.seznam_commands import validate_species_input, species_autocomplete, species_names

INZERCE_FILE = get_data_path("inzerce.json")
WISHLIST_FILE = get_data_path("wishlists.json")

CATEGORY_THUMBNAILS = {
    "Kolonie": "https://i.imgur.com/jgygbXm.png", 
    "Formikária": "https://i.imgur.com/YqG2xqt.png", 
    "Příslušenství": "https://i.imgur.com/T7PqsLe.png", 
    "Ostatní": "https://i.imgur.com/0sMpLJD.png",
    "Poptávka": "https://i.imgur.com/MMJDqYf.png"
}

active_ads = {}

def load_ads():
    global active_ads
    try:
        with open(INZERCE_FILE, "r", encoding="utf-8") as f:
            active_ads = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        active_ads = {}

def save_ads():
    try:
        with open(INZERCE_FILE, "w", encoding="utf-8") as f:
            json.dump(active_ads, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání inzerce: {e}")

load_ads()

def has_ad_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(role.id == AD_ROLE_ID for role in interaction.user.roles)

def is_moderator(user: discord.Member) -> bool:
    return any(role.id in MOD_ROLE_IDS for role in user.roles)

def get_expiration_date():
    return (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()

async def check_wishlists_and_notify(interaction_or_message, species_name: str, price: str, ad_link: str):
    try:
        with open(WISHLIST_FILE, "r", encoding="utf-8") as f:
            wishlists_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 

    if isinstance(interaction_or_message, discord.Interaction):
        author_id = str(interaction_or_message.user.id)
        author_mention = interaction_or_message.user.mention
        guild = interaction_or_message.guild
    else:
        author_id = str(interaction_or_message.author.id)
        author_mention = interaction_or_message.author.mention
        guild = interaction_or_message.guild

    users_to_notify_dm = []
    users_to_notify_public = []
    species_name_lower = species_name.lower()

    for user_id, data in wishlists_data.items():
        if str(user_id) == author_id:
            continue
            
        if not data.get("notifications", True):
            continue

        items = data.get("items", [])
        for item in items:
            if item.get("name", "").lower() == species_name_lower and not item.get("completed", False):
                pref = data.get("notify_pref", "public")
                if pref == "dm":
                    users_to_notify_dm.append(int(user_id))
                else:
                    users_to_notify_public.append(int(user_id))
                break
    
    users_to_notify_dm = list(set(users_to_notify_dm))
    users_to_notify_public = list(set(users_to_notify_public))

    if not users_to_notify_dm and not users_to_notify_public:
        return

    embed = discord.Embed(
        title="Shoda s Wishlistem!",
        description=f"Uživatel {author_mention} právě nabízí druh, který máte ve wishlistu.",
        color=discord.Color.gold()
    )
    embed.add_field(name="Druh", value=species_name, inline=True)
    if price:
        embed.add_field(name="Cena / Info", value=price, inline=True)
    embed.add_field(name="Odkaz na inzerát", value=f"[Přejít na inzerát]({ad_link})", inline=False)
    
    if users_to_notify_public:
        channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            mentions = " ".join([f"<@{uid}>" for uid in users_to_notify_public])
            await channel.send(content=mentions, embed=embed)

    for uid in users_to_notify_dm:
        member = guild.get_member(uid)
        if member:
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
                if channel:
                    await channel.send(content=f"<@{uid}> *(Máš zablokované zprávy od botů, proto posílám upozornění veřejně)*:", embed=embed)

async def check_seek_ads_and_notify(interaction_or_message, item_name: str, price: str, ad_link: str):
    if isinstance(interaction_or_message, discord.Interaction):
        author_id = interaction_or_message.user.id
        author_mention = interaction_or_message.user.mention
        guild = interaction_or_message.guild
    else:
        author_id = interaction_or_message.author.id
        author_mention = interaction_or_message.author.mention
        guild = interaction_or_message.guild

    item_lower = item_name.lower()
    users_to_notify_dm = []
    users_to_notify_public = []
    
    for ad_id, ad_data in active_ads.items():
        if ad_data.get("intent") == "hledam":
            sought_item = ad_data.get("item_name", "").lower()
            if sought_item and item_lower and (sought_item in item_lower or item_lower in sought_item):
                if ad_data["user_id"] != author_id:
                    pref = ad_data.get("notify_pref", "public")
                    if pref == "dm":
                        users_to_notify_dm.append(ad_data["user_id"])
                    else:
                        users_to_notify_public.append(ad_data["user_id"])
                        
    users_to_notify_dm = list(set(users_to_notify_dm))
    users_to_notify_public = list(set(users_to_notify_public))

    if not users_to_notify_dm and not users_to_notify_public:
        return

    embed = discord.Embed(
        title="Někdo nabízí to, co hledáš!",
        description=f"Uživatel {author_mention} právě přidal nabídku, která odpovídá tvé poptávce.",
        color=discord.Color.green()
    )
    embed.add_field(name="Předmět / Druh", value=item_name, inline=True)
    if price:
        embed.add_field(name="Cena / Info", value=price, inline=True)
    embed.add_field(name="Odkaz na nabídku", value=f"[Přejít na nabídku]({ad_link})", inline=False)

    if users_to_notify_public:
        channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            mentions = " ".join([f"<@{uid}>" for uid in users_to_notify_public])
            await channel.send(content=mentions, embed=embed)

    for uid in users_to_notify_dm:
        member = guild.get_member(uid)
        if member:
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
                if channel:
                    await channel.send(content=f"<@{uid}> *(Máš zablokované zprávy od botů, proto posílám upozornění veřejně)*:", embed=embed)

async def find_matching_sell_ads(interaction: discord.Interaction, sought_item: str):
    matching_ads = []
    sought_lower = sought_item.lower()

    for ad_id, ad_data in active_ads.items():
        intent = ad_data.get("intent", "prodej")
        if intent in ["prodej", "prodam"]:
            sold_item = ad_data.get("species", "") or ad_data.get("item_name", "")
            sold_lower = sold_item.lower()

            if sold_lower and sought_lower and (sought_lower in sold_lower or sold_lower in sought_lower):
                if ad_data["user_id"] != interaction.user.id:
                    guild_id = interaction.guild_id
                    channel_id = ad_data["channel_id"]
                    link = f"https://discord.com/channels/{guild_id}/{channel_id}/{ad_id}"
                    matching_ads.append((sold_item, link))

    if matching_ads:
        description = "Našli jsme aktivní nabídky, které by tě mohly zajímat:\n\n"
        for item, link in matching_ads[:5]:
            description += f"• **{item}**: [Zobrazit inzerát]({link})\n"

        if len(matching_ads) > 5:
            description += "\n*... a další (prohledej kanál inzerce).*"

        embed = discord.Embed(
            title="Nalezeny odpovídající nabídky!",
            description=description,
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

async def process_chat_message(message: discord.Message):
    if message.channel.id != AD_CHANNEL_ID:
        return
    if message.author.bot:
        return

    content_lower = message.content.lower()
    buy_keywords = ["koupím", "koupim", "sháním", "shanim", "hledám", "hledam", "poptávám", "poptavam", "koupě", "koupe"]
    if any(word in content_lower for word in buy_keywords):
        return 

    sell_keywords = ["prodám", "prodam", "prodávám", "prodej", "nabízím", "nabizim", "daruji", "darujem", "vyměním", "predám", "ponúkam", "nabídka", "nabidka"]
    if not any(word in content_lower for word in sell_keywords):
        return 

    if not species_names: 
        return

    found_species = []
    for species in species_names:
        if species.lower() in content_lower:
            is_substring = False
            for existing in found_species:
                if species.lower() in existing.lower() and len(species) < len(existing):
                    is_substring = True
                    break
            if not is_substring:
                found_species.append(species)

    if found_species:
        for sp in found_species:
            await check_wishlists_and_notify(message, sp, "Cena ve zprávě", message.jump_url)
            await check_seek_ads_and_notify(message, sp, "Cena ve zprávě", message.jump_url)

async def delete_ad_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    user_is_mod = is_moderator(interaction.user)
    user_id_str = str(interaction.user.id)
    choices = []
    
    for ad_id, ad_data in active_ads.items():
        if user_is_mod or str(ad_data["user_id"]) == user_id_str:
            item_name = ad_data.get("species") or ad_data.get("item_name") or "Předmět"
            category = ad_data.get("category", "Inzerát")
            label = f"{category}: {item_name} (ID: {ad_id[-4:]})" 
            
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=ad_id))
    
    return choices[:15]

class ContactAdAuthorModal(ui.Modal, title="Odpověď na inzerát"):
    message_text = ui.TextInput(
        label="Tvoje zpráva pro inzerenta", 
        style=discord.TextStyle.paragraph, 
        placeholder="Ahoj, měl bych zájem o tvůj inzerát. Je to ještě aktuální?",
        max_length=1500,
        required=True
    )

    def __init__(self, author_id: int, ad_url: str, ad_title: str):
        super().__init__()
        self.author_id = author_id
        self.ad_url = ad_url
        self.ad_title = ad_title

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.client.get_user(self.author_id)
        if not user:
            try:
                user = await interaction.client.fetch_user(self.author_id)
            except discord.NotFound:
                await interaction.response.send_message("Nepodařilo se najít autora inzerátu. Možná opustil server.", ephemeral=True)
                return

        embed = discord.Embed(
            title="Nová odpověď na tvůj inzerát",
            description=f"Uživatel {interaction.user.mention} reaguje na tvůj inzerát **{self.ad_title}**.\n\n**Zpráva:**\n{self.message_text.value}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Odkaz na inzerát", value=f"[Zobrazit inzerát zde]({self.ad_url})", inline=False)
        embed.set_footer(text=f"Odpověz uživateli {interaction.user.display_name} do jeho soukromých zpráv.")

        try:
            await user.send(embed=embed)
            await interaction.response.send_message(f"Tvoje zpráva byla úspěšně odeslána uživateli **{user.display_name}** do soukromých zpráv.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"**{user.display_name}** má zablokované přijímání soukromých zpráv od členů serveru. Zkus ho označit přímo v inzertním kanálu.", ephemeral=True)

class AdInteractionView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Odpovědět na inzerát", style=discord.ButtonStyle.primary, custom_id="reply_to_ad_btn")
    async def reply_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.message.embeds:
            await interaction.response.send_message("Chyba: Inzerát neobsahuje potřebná data.", ephemeral=True)
            return

        ad_id = str(interaction.message.id)
        author_id = None
        
        if ad_id in active_ads:
            author_id = active_ads[ad_id]["user_id"]
        else:
            embed = interaction.message.embeds[0]
            footer_text = embed.footer.text if embed.footer else ""
            match = re.search(r"UserID:\s*(\d+)", footer_text)
            if match:
                author_id = int(match.group(1))
                
        if not author_id:
            await interaction.response.send_message("Záznam o tomto inzerátu již neexistuje v databázi.", ephemeral=True)
            return

        if interaction.user.id == author_id:
            await interaction.response.send_message("Nemůžeš odpovídat na svůj vlastní inzerát.", ephemeral=True)
            return

        ad_title = interaction.message.embeds[0].title or "Neznámý inzerát"
        await interaction.response.send_modal(ContactAdAuthorModal(author_id, interaction.message.jump_url, ad_title))

class SeekNotifyPreferenceView(ui.View):
    def __init__(self, ad_id: str):
        super().__init__(timeout=300)
        self.ad_id = ad_id

    @ui.button(label="Upozornění do DM", style=discord.ButtonStyle.primary)
    async def dm_pref(self, interaction: discord.Interaction, button: ui.Button):
        if self.ad_id in active_ads:
            active_ads[self.ad_id]["notify_pref"] = "dm"
            save_ads()
            await interaction.response.edit_message(content="Nastaveno upozornění do **Soukromých zpráv (DM)**.", view=None)
        else:
            await interaction.response.edit_message(content="Inzerát nebyl nalezen v databázi.", view=None)

    @ui.button(label="Veřejně do kanálu", style=discord.ButtonStyle.secondary)
    async def pub_pref(self, interaction: discord.Interaction, button: ui.Button):
        if self.ad_id in active_ads:
            active_ads[self.ad_id]["notify_pref"] = "public"
            save_ads()
            await interaction.response.edit_message(content="Nastaveno **Veřejné upozornění** do oznamovacího kanálu.", view=None)
        else:
            await interaction.response.edit_message(content="Inzerát nebyl nalezen v databázi.", view=None)

class BaseAdModal(ui.Modal):
    def __init__(self, category: str, intent: str = "prodej"):
        title_prefix = "Poptávka" if intent == "hledam" else "Inzerát"
        super().__init__(title=f"{title_prefix}: {category}")
        self.category = category
        self.intent = intent
        self.images = ui.TextInput(
            label="Odkazy na obrázky (Imgur apod.)", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            placeholder="Jeden odkaz na řádek. První odkaz bude použit jako náhled.",
            max_length=1000
        )

    def get_declined_category(self):
        mapping = {
            "Kolonie": "KOLONIÍ",
            "Formikária": "FORMIKÁRIÍ",
            "Příslušenství": "PŘÍSLUŠENSTVÍ",
            "Ostatní": "OSTATNÍHO"
        }
        return mapping.get(self.category, self.category.upper())

    async def create_ad_embed(self, interaction: discord.Interaction, fields: list, notes: str):
        if self.intent == "prodej":
            title = f"PRODEJ {self.get_declined_category()}"
            color = discord.Color.green()
            thumb_url = CATEGORY_THUMBNAILS.get(self.category)
        else:
            title = "POPTÁVKA (HLEDÁM)"
            color = discord.Color.orange()
            thumb_url = CATEGORY_THUMBNAILS.get("Poptávka")

        embed = discord.Embed(
            title=title,
            description=notes if notes else "Bez poznámky.",
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=True)
            
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)

        image_urls = [url.strip() for url in self.images.value.split("\n") if url.strip()]
        if image_urls:
            embed.set_image(url=image_urls[0])
            if len(image_urls) > 1:
                links_text = "\n".join(image_urls[1:5]) 
                embed.add_field(name="Další obrázky", value=links_text, inline=False)
        
        expire_dt = datetime.datetime.now() + datetime.timedelta(days=30)
        date_str = expire_dt.strftime("%d. %m. %Y")
        
        embed.set_footer(text=f"Vyprší: {date_str}")
        return embed, image_urls

    async def post_ad(self, interaction: discord.Interaction, embed: discord.Embed, ad_data_extra: dict):
        channel = interaction.guild.get_channel(AD_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("Chyba: Cílový kanál pro inzeráty nenalezen.", ephemeral=True)
            return None, None

        view = AdInteractionView()
        message = await channel.send(embed=embed, view=view)
        
        ad_id = str(message.id)
        short_id = ad_id[-4:] 
        current_footer = embed.footer.text
        
        embed.set_footer(text=f"{current_footer} | ID: {short_id}")
        await message.edit(embed=embed)
        
        active_ads[ad_id] = {
            "user_id": interaction.user.id,
            "channel_id": AD_CHANNEL_ID,
            "category": self.category,
            "intent": self.intent,
            "created_at": datetime.datetime.now().isoformat(),
            "expires_at": get_expiration_date(),
            **ad_data_extra
        }
        save_ads()
        return message, ad_id

class ColonyAdModal(BaseAdModal):
    def __init__(self, species_name: str):
        super().__init__(category="Kolonie", intent="prodej")
        self.species_name = species_name
        
        self.count = ui.TextInput(label="Počet nabízených kolonií", placeholder="např. 1", default="1", max_length=5)
        self.size = ui.TextInput(label="Velikost (Královny / Dělnice)", placeholder="např. 1Q + 10-20w", max_length=100)
        self.price = ui.TextInput(label="Cena (CZK/EUR)", placeholder="např. 500 CZK", max_length=50)
        self.notes = ui.TextInput(
            label="Poznámky", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            max_length=1000,
            placeholder="rok odchycení královny, původ, doručení, další detaily..."
        )

        self.add_item(self.count)
        self.add_item(self.size)
        self.add_item(self.price)
        self.add_item(self.notes)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        fields = [
            ("Druh", self.species_name),
            ("Počet", self.count.value),
            ("Velikost", self.size.value),
            ("Cena", self.price.value)
        ]
        embed, image_urls = await self.create_ad_embed(interaction, fields, self.notes.value)
        ad_data = {"type": "colony", "species": self.species_name, "price": self.price.value, "description": self.notes.value, "images": image_urls}
        
        message, ad_id = await self.post_ad(interaction, embed, ad_data)
        if message:
            await interaction.response.send_message(f"Tvůj inzerát byl úspěšně zveřejněn v <#{AD_CHANNEL_ID}>!", ephemeral=True)
            await check_wishlists_and_notify(interaction, self.species_name, self.price.value, message.jump_url)
            await check_seek_ads_and_notify(interaction, self.species_name, self.price.value, message.jump_url)

class ItemAdModal(BaseAdModal):
    def __init__(self, category: str):
        super().__init__(category=category, intent="prodej")
        self.item_name = ui.TextInput(label="Název předmětu/zvířete", placeholder="např. Ytong hnízdo velikost M", max_length=100)
        self.amount = ui.TextInput(label="Množství", placeholder="např. 1 ks", max_length=50)
        self.price = ui.TextInput(label="Cena (CZK/EUR)", placeholder="např. 200 CZK", max_length=50)
        self.notes = ui.TextInput(label="Popis a poznámky", style=discord.TextStyle.paragraph, required=False, max_length=1000)

        self.add_item(self.item_name)
        self.add_item(self.amount)
        self.add_item(self.price)
        self.add_item(self.notes)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        fields = [("Předmět", self.item_name.value), ("Množství", self.amount.value), ("Cena", self.price.value)]
        embed, image_urls = await self.create_ad_embed(interaction, fields, self.notes.value)
        ad_data = {"type": "item", "item_name": self.item_name.value, "price": self.price.value, "description": self.notes.value, "images": image_urls}
        
        message, ad_id = await self.post_ad(interaction, embed, ad_data)
        if message:
            await interaction.response.send_message(f"Tvůj inzerát byl úspěšně zveřejněn v <#{AD_CHANNEL_ID}>!", ephemeral=True)
            await check_seek_ads_and_notify(interaction, self.item_name.value, self.price.value, message.jump_url)

class SeekAdModal(BaseAdModal):
    def __init__(self, species_name: Optional[str] = None):
        super().__init__(category="Hledám", intent="hledam")
        default_item = species_name if species_name else ""
        
        self.item_name = ui.TextInput(
            label="Co poptáváš? (Druh mravence / Předmět)", 
            placeholder="např. Kolonii Lasius niger / Ytong hnízdo", 
            default=default_item,
            max_length=100,
            required=True
        )
        self.price = ui.TextInput(
            label="Nabízená cena / Rozpočet", 
            placeholder="např. do 500 Kč, Nabídněte, Vyměním za...", 
            max_length=50,
            required=True
        )
        self.notes = ui.TextInput(
            label="Další detaily a specifikace", 
            style=discord.TextStyle.paragraph, 
            required=False, 
            max_length=1000,
            placeholder="např. chci jen velkou kolonii, osobní předání v Praze..."
        )

        self.add_item(self.item_name)
        self.add_item(self.price)
        self.add_item(self.notes)
        self.add_item(self.images)

    async def on_submit(self, interaction: discord.Interaction):
        fields = [
            ("Poptávám", self.item_name.value),
            ("Nabízená cena", self.price.value)
        ]
        embed, image_urls = await self.create_ad_embed(interaction, fields, self.notes.value)
        ad_data = {
            "type": "seek", 
            "item_name": self.item_name.value, 
            "price": self.price.value, 
            "description": self.notes.value, 
            "images": image_urls,
            "notify_pref": "public"
        }
        
        message, ad_id = await self.post_ad(interaction, embed, ad_data)
        if message:
            view = SeekNotifyPreferenceView(ad_id)
            await interaction.response.send_message(
                f"Tvoje poptávka byla úspěšně zveřejněna v <#{AD_CHANNEL_ID}>.\n\n"
                f"**Jak chceš být upozorněn**, pokud se objeví nabídka na tvou poptávku?", 
                view=view, 
                ephemeral=True
            )
            await find_matching_sell_ads(interaction, self.item_name.value)

class CategorySelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Kolonie mravenců", description="Prodej královen a kolonií", value="colony"),
            discord.SelectOption(label="Formikária", description="Hnízda, arény, zkumavky", value="formicaria"),
            discord.SelectOption(label="Příslušenství", description="Pinzety, krmítka, bariéry", value="accessories"),
            discord.SelectOption(label="Ostatní živočichové/rostliny", description="Krmný hmyz, isopodi, rostliny", value="other")
        ]
        super().__init__(placeholder="Vyber kategorii prodeje...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "colony":
            await interaction.response.send_modal(ManualColonyNameModal())
        elif choice == "formicaria":
            await interaction.response.send_modal(ItemAdModal("Formikária"))
        elif choice == "accessories":
            await interaction.response.send_modal(ItemAdModal("Příslušenství"))
        elif choice == "other":
            await interaction.response.send_modal(ItemAdModal("Ostatní"))

class ManualColonyNameModal(ui.Modal, title="Zadej název druhu"):
    species_input = ui.TextInput(label="Název druhu", placeholder="např. Lasius niger", min_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        is_valid, result = await validate_species_input(self.species_input.value)
        if not is_valid:
            await interaction.response.send_message(f"**Chyba v názvu:** {result}\nZkus to prosím znovu.", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"Druh ověřen: {result}", description="Klikni na tlačítko níže pro vyplnění detailů inzerátu.", color=discord.Color.green())
        view = ContinueToAdView(result)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ContinueToAdView(ui.View):
    def __init__(self, species_name):
        super().__init__()
        self.species_name = species_name

    @ui.button(label="Vyplnit inzerát", style=discord.ButtonStyle.primary)
    async def continue_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ColonyAdModal(self.species_name))

class InzerceProdamView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(CategorySelect())

inzerce_group = app_commands.Group(name="inzerce", description="Systém pro inzerci na serveru.")

@inzerce_group.command(name="prodam", description="Vytvořit nový inzerát (nabídku). Pro mravence použij 'druh' pro našeptávání!")
@app_commands.describe(druh="Použij POUZE pokud prodáváš mravence, aktivuje našeptávání.")
@app_commands.autocomplete(druh=species_autocomplete)
async def inzerce_prodam(interaction: discord.Interaction, druh: Optional[str] = None):
    if not has_ad_role(interaction):
        await interaction.response.send_message("Nemáš roli pro přidávání inzerátů.", ephemeral=True)
        return

    if druh:
        is_valid, result = await validate_species_input(druh)
        if not is_valid:
            await interaction.response.send_message(f"**Chyba v názvu:** {result}", ephemeral=True)
            return
        await interaction.response.send_modal(ColonyAdModal(result))
    else:
        embed = discord.Embed(title="Vytvoření prodejního inzerátu", description="Vyber kategorii inzerátu z nabídky níže.\n\n*Tip: Pokud prodáváš mravence, použij `/inzerce prodam druh:Nazev` pro využití našeptávače.*", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=InzerceProdamView(), ephemeral=True)

@inzerce_group.command(name="hledam", description="Vytvořit poptávku (koupím / hledám).")
@app_commands.describe(druh="Použij, pokud poptáváš konkrétní druh mravence (aktivuje našeptávač).")
@app_commands.autocomplete(druh=species_autocomplete)
async def inzerce_hledam(interaction: discord.Interaction, druh: Optional[str] = None):
    if not has_ad_role(interaction):
        await interaction.response.send_message("Nemáš roli pro přidávání inzerátů.", ephemeral=True)
        return

    species_valid_name = None
    if druh:
        is_valid, result = await validate_species_input(druh)
        if not is_valid:
            await interaction.response.send_message(f"**Chyba v názvu:** {result}", ephemeral=True)
            return
        species_valid_name = result

    await interaction.response.send_modal(SeekAdModal(species_name=species_valid_name))

@inzerce_group.command(name="smazat", description="Smazat inzerát (pro autory a moderátory).")
@app_commands.describe(inzerat="Vyber inzerát, který chceš smazat.")
@app_commands.autocomplete(inzerat=delete_ad_autocomplete)
async def inzerce_smazat(interaction: discord.Interaction, inzerat: str):
    ad_id = inzerat
    
    if ad_id not in active_ads:
        await interaction.response.send_message("Tento inzerát nebyl nalezen v databázi (možná již vypršel nebo byl smazán).", ephemeral=True)
        return
        
    ad_data = active_ads[ad_id]
    user_is_mod = is_moderator(interaction.user)
    user_is_owner = str(ad_data["user_id"]) == str(interaction.user.id)
    
    if not (user_is_mod or user_is_owner):
        await interaction.response.send_message("Nemáš oprávnění smazat tento inzerát (nejsi autor ani moderátor).", ephemeral=True)
        return

    channel_id = ad_data["channel_id"]
    channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
    
    msg_deleted_from_discord = False
    
    if channel:
        try:
            msg = await channel.fetch_message(int(ad_id))
            await msg.delete()
            msg_deleted_from_discord = True
        except discord.NotFound:
            pass
        except discord.Forbidden:
            await interaction.response.send_message("Nemám práva smazat zprávu v inzertním kanálu.", ephemeral=True)
            return
    
    del active_ads[ad_id]
    save_ads()
    
    item_name = ad_data.get("species") or ad_data.get("item_name") or "Předmět"
    
    if msg_deleted_from_discord:
        await interaction.response.send_message(f"Inzerát **{item_name}** byl úspěšně smazán.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Inzerát **{item_name}** byl odstraněn z databáze (zpráva na Discordu již neexistovala).", ephemeral=True)

async def check_expired_ads(client: discord.Client):
    await client.wait_until_ready()
    
    while not client.is_closed():
        now = datetime.datetime.now()
        ids_to_remove = []
        
        for msg_id, data in active_ads.items():
            try:
                expires_at = datetime.datetime.fromisoformat(data["expires_at"])
                if now >= expires_at:
                    ids_to_remove.append(msg_id)
                    
                    channel = client.get_channel(data["channel_id"])
                    if channel:
                        try:
                            msg = await channel.fetch_message(int(msg_id))
                            await msg.delete()
                        except discord.NotFound:
                            pass 
                    
                    notify_channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
                    user_id = data["user_id"]
                    
                    if notify_channel:
                        cat = data.get("category", "Neznámá")
                        item = data.get("species") or data.get("item_name") or "Předmět"
                        await notify_channel.send(
                            f"<@{user_id}>, tvoje inzerce ({cat}: {item}) vypršela a byla smazána. "
                            f"Pokud je nabídka stále aktuální, zadej inzerát znovu."
                        )

            except Exception as e:
                print(f"Chyba při kontrole expirace inzerátu {msg_id}: {e}")

        if ids_to_remove:
            for msg_id in ids_to_remove:
                del active_ads[msg_id]
            save_ads()
        
        await asyncio.sleep(6600)

def setup_inzerce(client: discord.Client):
    client.loop.create_task(check_expired_ads(client))
