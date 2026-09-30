# Tento soubor spravuje systém událostí a notifikací pro Discord bota.
#
# Funkce:
# - Ukládání a načítání událostí do JSON souboru (events.json).
# - Příkaz /udalosti zobrazit: Výpis akcí s paginátorem a detaily (Web, Kontakt, Pozvánka).
# - Příkaz /udalosti pridat: Ruční přidání akce přes formulář (Modal).
# - Příkaz /udalosti pridat_entosphinx: Pokročilý scraping burz z Entosphinx.cz.
# - Automatické notifikace: Upozornění 1 měsíc, 1 týden a 1 den před akcí.
#
# Závislosti:
# - discord.py, requests, beautifulsoup4, datetime, json, re, asyncio

import discord
from discord import app_commands, ui
import json
import os
import datetime
import asyncio
import requests
from bs4 import BeautifulSoup
import re
import uuid
from typing import List, Optional

# --- Import PaginatorView z utils ---
# Předpokládáme, že utils.py je ve stejné složce
from utils import PaginatorView

# --- Konstanty ---
EVENTS_FILE = 'Soubory/events.json'
NOTIFICATION_CHANNEL_ID = 661958543548612660
ENTOSPHINX_URL = "https://www.entosphinx.cz/cs/content/8-entomologicke-burzy"

ALLOWED_ROLE_IDS = [
    661971700556234753, # Samec - mod na zkoušku
    661971822006239242, # Královna - moderátor
    661971417746898971, # Antkeeper - ADMIN
    913531312797798420  # Informátor událostí
]

# --- Globální proměnná pro události ---
# Struktura: { "uuid": { "title", "start", "end", "location", "description", "image", "source", "invitation_link", "contact", "website" } }
events_data = {}

# --- Správa dat ---
def load_events():
    """Načte události ze souboru."""
    global events_data
    try:
        with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
            events_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {EVENTS_FILE} nenalezen, vytvářím nový.")
        # Ujistíme se, že složka existuje
        os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
        events_data = {}

def save_events():
    """Uloží události do souboru."""
    try:
        # Ujistíme se, že složka existuje
        os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
        with open(EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Chyba při ukládání událostí: {e}")

# Načteme data při importu
load_events()

# --- Pomocné funkce ---
def has_permission(interaction: discord.Interaction) -> bool:
    """Zkontroluje, zda má uživatel jednu z povolených rolí."""
    if not isinstance(interaction.user, discord.Member):
        return False
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(allowed_id in user_role_ids for allowed_id in ALLOWED_ROLE_IDS)

def parse_date_str(date_str: str) -> Optional[datetime.date]:
    """Převede string typu '10. 1. 2026' na objekt date."""
    try:
        # Odstranění mezer a běžný formát d.m.Y
        clean_str = date_str.replace(" ", "")
        return datetime.datetime.strptime(clean_str, "%d.%m.%Y").date()
    except ValueError:
        return None

def format_time_remaining(event_date: datetime.date) -> str:
    """Vrátí lidsky čitelný čas zbývající do události."""
    today = datetime.date.today()
    delta = event_date - today
    days = delta.days

    if days < 0:
        return "(Proběhlo)"
    elif days == 0:
        return "(**Dnes!**)"
    elif days == 1:
        return "(**Zítra!**)"
    elif days < 7:
        return f"(za {days} dní)"
    elif days < 30:
        weeks = round(days / 7)
        if weeks <= 1:
            return "(za 1 týden)"
        elif weeks <= 4:
            return f"(za {weeks} týdny)"
        else:
            return f"(za {weeks} týdnů)"
    else:
        months = round(days / 30)
        if months <= 1:
            return "(za 1 měsíc)"
        elif months <= 4:
            return f"(za {months} měsíce)"
        else:
            return f"(za {months} měsíců)"

# --- UI Komponenty ---

class EventModal(ui.Modal, title="Přidat novou událost"):
    name = ui.TextInput(label="Název akce", placeholder="např. Entomologická burza Praha", required=True)
    date_range = ui.TextInput(label="Datum (DD.MM.RRRR nebo rozsah)", placeholder="10.1.2026 nebo 1.1.2026 - 2.1.2026", required=True)
    location = ui.TextInput(label="Místo konání", placeholder="např. Kulturní dům Barikádníků, Praha", required=True)
    description = ui.TextInput(label="Popis akce (vč. kontaktů a webu)", style=discord.TextStyle.paragraph, placeholder="Detaily o akci...", required=False)
    image_url = ui.TextInput(label="Odkaz na obrázek (URL)", placeholder="https://...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        # Zpracování data
        raw_date = self.date_range.value.strip()
        start_date = None
        end_date = None

        date_pattern = r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"
        dates = re.findall(date_pattern, raw_date)

        if not dates:
            await interaction.response.send_message("❌ Nepodařilo se rozpoznat datum. Použijte formát `DD.MM.RRRR`.", ephemeral=True)
            return

        try:
            start_date = parse_date_str(dates[0])
            if len(dates) > 1:
                end_date = parse_date_str(dates[1])
            else:
                end_date = start_date
        except Exception:
             await interaction.response.send_message("❌ Chyba při zpracování data.", ephemeral=True)
             return

        if not start_date:
             await interaction.response.send_message("❌ Neplatné datum.", ephemeral=True)
             return

        event_id = str(uuid.uuid4())
        events_data[event_id] = {
            "title": self.name.value,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "location": self.location.value,
            "description": self.description.value or "Bez popisu.",
            "image": self.image_url.value or None,
            "source": f"Přidal: {interaction.user.display_name}",
            "invitation_link": self.image_url.value or None,
            "contact": None, # Manualně vložené akce nemají separátní pole, vše je v popisu
            "website": None
        }
        save_events()

        embed = discord.Embed(title="✅ Událost přidána", color=discord.Color.green())
        embed.add_field(name=self.name.value, value=f"{start_date.strftime('%d.%m.%Y')} v {self.location.value}")
        await interaction.response.send_message(embed=embed)


# --- Skupina příkazů ---
udalosti_group = app_commands.Group(name="udalosti", description="Správa entomologických událostí a burz.")

@udalosti_group.command(name="zobrazit", description="Zobrazí seznam nadcházejících událostí.")
async def udalosti_zobrazit(interaction: discord.Interaction):
    if not events_data:
        await interaction.response.send_message("Zatím nejsou v plánu žádné události.", ephemeral=True)
        return

    # Seřazení událostí podle data
    sorted_events = []
    today = datetime.date.today()
    
    for eid, data in events_data.items():
        try:
            s_date = datetime.date.fromisoformat(data['start'])
            # Filtrovat staré akce (starší než 7 dní od dneška se nezobrazují)
            if s_date >= (today - datetime.timedelta(days=7)):
                sorted_events.append((eid, data, s_date))
        except ValueError:
            continue

    sorted_events.sort(key=lambda x: x[2])

    if not sorted_events:
        await interaction.response.send_message("Žádné nadcházející události.", ephemeral=True)
        return

    pages = []
    for eid, data, s_date in sorted_events:
        date_str = s_date.strftime("%d. %m. %Y")
        if data['start'] != data['end']:
            try:
                e_date = datetime.date.fromisoformat(data['end'])
                date_str += f" - {e_date.strftime('%d. %m. %Y')}"
            except: pass
        
        time_remaining = format_time_remaining(s_date)
        date_display = f"{date_str} {time_remaining}"

        embed = discord.Embed(
            title=data['title'],
            description=data['description'][:4000],
            color=discord.Color.orange()
        )
        embed.add_field(name="📅 Kdy", value=date_display, inline=True)
        embed.add_field(name="📍 Kde", value=data['location'], inline=True)
        
        # Nové pole pro odkazy
        links_text = ""
        
        # Pozvánka
        invitation = data.get('invitation_link')
        if invitation:
            links_text += f"**[📄 Pozvánka]({invitation})**\n"
        
        # Web
        website = data.get('website')
        if website:
            links_text += f"**[🌐 Web akce]({website})**\n"
            
        # Kontakt
        contact = data.get('contact')
        if contact:
            if "@" in contact and not contact.startswith("mailto:"):
                 links_text += f"📧 {contact}\n"
            elif contact.startswith("mailto:"):
                 # Z mailto:email@neco.cz vytahneme email@neco.cz
                 clean_email = contact.replace("mailto:", "")
                 links_text += f"📧 {clean_email}\n"
            else:
                 links_text += f"📞 {contact}\n"

        if links_text:
             embed.add_field(name="🔗 Odkazy a Kontakt", value=links_text, inline=False)

        # Obrázek (pokud existuje a je to obrázek, ne PDF)
        img_url = data.get('image')
        if img_url:
            embed.set_image(url=img_url)
        
        embed.set_footer(text=f"Zdroj: {data.get('source', 'Neznámý')} | ID: {eid}")
        pages.append(embed)

    view = PaginatorView(pages, interaction)
    message = await interaction.response.send_message(embed=pages[0], view=view)
    view.message = await interaction.original_response()

@udalosti_group.command(name="pridat", description="Ručně přidá novou událost (jen pro oprávněné).")
async def udalosti_pridat(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("Nemáš oprávnění přidávat události.", ephemeral=True)
        return
    
    await interaction.response.send_modal(EventModal())

@udalosti_group.command(name="pridat_entosphinx", description="Načte aktuální burzy z Entosphinx.cz (jen pro oprávněné).")
async def udalosti_pridat_entosphinx(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("Nemáš oprávnění spouštět scraping.", ephemeral=True)
        return

    await interaction.response.defer()
    
    try:
        # 1. Získání HTML
        local_file = 'entosphinx burzy.html'
        html_content = ""
        
        try:
            response = requests.get(ENTOSPHINX_URL, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            html_content = response.text
        except Exception as e:
            if os.path.exists(local_file):
                with open(local_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            else:
                raise e

        soup = BeautifulSoup(html_content, 'html.parser')
        
        content_div = soup.find('div', class_='rte')
        if not content_div:
            await interaction.followup.send("❌ Nepodařilo se najít kontejner s událostmi na stránce.")
            return

        added_count = 0
        header_pattern = re.compile(r'([A-Za-ž]+)\s*-\s*(\d{1,2}\.?\s*-?\s*\d*\.?\s*\d+\.\s*\d{4})', re.IGNORECASE)
        
        # Získáme všechny paragrafy a divy
        paragraphs = content_div.find_all(['p', 'div'])
        
        i = 0
        while i < len(paragraphs):
            p = paragraphs[i]
            text = p.get_text(strip=True)
            match = header_pattern.search(text)
            
            if match:
                city = match.group(1).strip()
                date_str = match.group(2).strip()
                
                # Zpracování data
                start_date = None
                end_date = None
                try:
                    nums = re.findall(r'\d+', date_str)
                    if not nums: 
                        i += 1
                        continue
                    
                    year = int(nums[-1])
                    month = int(nums[-2])
                    day_start = int(nums[0])
                    
                    if len(nums) > 3:
                         day_end = int(nums[1])
                    else:
                         day_end = day_start
                    
                    start_date = datetime.date(year, month, day_start)
                    end_date = datetime.date(year, month, day_end)
                except Exception as e:
                    print(f"Date parse error: {date_str} - {e}")
                    i += 1
                    continue

                # Duplicita
                is_duplicate = False
                for existing in events_data.values():
                    if existing['start'] == start_date.isoformat() and existing['location'] == city:
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    i += 1
                    continue

                # --- Extrakce detailů (Web, Kontakt, Pozvánka) ---
                # Prohledáme aktuální 'p' a také následující 'p', pokud neobsahuje nové datum
                
                description_text = text
                invitation_link = None
                image_url = None
                contact = None
                website = None
                
                elements_to_scan = [p]
                
                # Podíváme se na další element, jestli nepatří k této akci
                # (Entosphinx má často nadpis v jednom P a detaily v dalším P)
                if i + 1 < len(paragraphs):
                    next_p = paragraphs[i+1]
                    next_text = next_p.get_text(strip=True)
                    # Pokud další element NENÍ nová událost (nemá pattern data)
                    if not header_pattern.search(next_text):
                        elements_to_scan.append(next_p)
                        description_text += "\n" + next_text
                        # Posuneme index, abychom tento paragraf nezpracovali znovu (i když by neprošel checkem data, je to čistší)
                        # Ale pozor, while loop se inkrementuje na konci, takže tady opatrně.
                        # Pro jednoduchost, jen naskenujeme data, ale index inkrementovat nebudeme, 
                        # hlavní smyčka ho přeskočí, protože v něm nenajde datum.

                # Skenování odkazů
                for elem in elements_to_scan:
                    links = elem.find_all('a', href=True)
                    for link in links:
                        href = link['href']
                        
                        # Fix relativních cest
                        if not href.startswith(('http', 'mailto')):
                            if href.startswith('/'):
                                href = "https://www.entosphinx.cz" + href
                            else:
                                href = "https://www.entosphinx.cz/" + href

                        lower_href = href.lower()

                        # 1. Email
                        if href.startswith('mailto:'):
                            contact = href # Uložíme celé mailto:
                        elif '@' in href and not 'entosphinx' in href: # Jednoduchá detekce
                             contact = href

                        # 2. Pozvánka (Obrázek nebo PDF)
                        elif lower_href.endswith(('.jpg', '.png', '.jpeg', '.pdf','.jfif')):
                            invitation_link = href
                            # Pokud je to obrázek, dáme ho i do image_url pro náhled
                            if not lower_href.endswith('.pdf'):
                                image_url = href
                        
                        # 3. Web (pokud to není pozvánka ani email a není to odkaz na entosphinx mapu stránek apod.)
                        elif 'google' not in lower_href and 'entosphinx' not in lower_href:
                            website = href

                # Přidání
                event_id = str(uuid.uuid4())
                events_data[event_id] = {
                    "title": f"Entomologická burza {city}",
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "location": city,
                    "description": description_text,
                    "image": image_url,
                    "invitation_link": invitation_link,
                    "contact": contact,
                    "website": website,
                    "source": "Entosphinx.cz (Auto)"
                }
                added_count += 1
            
            i += 1

        save_events()
        await interaction.followup.send(f"✅ Zpracováno. Přidáno **{added_count}** nových událostí z Entosphinx.")

    except Exception as e:
        await interaction.followup.send(f"❌ Chyba při scrapování: {e}")
        print(f"Scraping error: {e}")

@udalosti_group.command(name="smazat", description="Smaže událost podle ID (jen pro oprávněné).")
@app_commands.describe(event_id="ID události (najdeš v /udalosti zobrazit)")
async def udalosti_smazat(interaction: discord.Interaction, event_id: str):
    if not has_permission(interaction):
        await interaction.response.send_message("Nemáš oprávnění mazat události.", ephemeral=True)
        return
    
    if event_id in events_data:
        del events_data[event_id]
        save_events()
        await interaction.response.send_message(f"🗑️ Událost `{event_id}` byla smazána.")
    else:
        await interaction.response.send_message(f"❌ Událost s ID `{event_id}` nebyla nalezena.", ephemeral=True)

# --- Background Task: Notifikace ---

async def check_upcoming_events(client: discord.Client):
    """Smyčka, která kontroluje události a posílá notifikace."""
    await client.wait_until_ready()
    
    while not client.is_closed():
        today = datetime.date.today()
        channel = client.get_channel(NOTIFICATION_CHANNEL_ID)
        
        if not channel:
            print(f"VAROVÁNÍ: Notifikační kanál {NOTIFICATION_CHANNEL_ID} nenalezen.")
            await asyncio.sleep(3600) # Zkusíme za hodinu
            continue

        for eid, data in events_data.items():
            try:
                start_date = datetime.date.fromisoformat(data['start'])
                delta = (start_date - today).days
                
                msg_prefix = None
                
                # Kontrola: 1 měsíc (cca 30 dní), 1 týden (7 dní), 1 den (1 den)
                if delta == 30:
                    msg_prefix = "🗓️ **Za měsíc**"
                elif delta == 7:
                    msg_prefix = "⏰ **Za týden**"
                elif delta == 1:
                    msg_prefix = "⚠️ **Zítra**"

                if msg_prefix:
                    embed = discord.Embed(
                        title=f"{msg_prefix}: {data['title']}",
                        description=data['description'][:200] + "...",
                        color=discord.Color.red()
                    )
                    date_str = start_date.strftime("%d. %m. %Y")
                    embed.add_field(name="Kdy", value=date_str)
                    embed.add_field(name="Kde", value=data['location'])
                    
                    # Přidání odkazů do notifikace
                    links = []
                    if data.get('invitation_link'): links.append(f"[Pozvánka]({data['invitation_link']})")
                    if data.get('website'): links.append(f"[Web]({data['website']})")
                    
                    if links:
                        embed.add_field(name="Odkazy", value=" | ".join(links), inline=False)

                    if data.get('image'):
                        embed.set_thumbnail(url=data['image'])
                    
                    await channel.send(content=f"🔔 Připomínka události!", embed=embed)
                    
            except Exception as e:
                print(f"Chyba při kontrole eventu {eid}: {e}")

        # Počkáme 24 hodin před další kontrolou
        await asyncio.sleep(86400)

def setup_udalosti(client: discord.Client):
    """Funkce pro inicializaci background tasku z main.py"""
    client.loop.create_task(check_upcoming_events(client))