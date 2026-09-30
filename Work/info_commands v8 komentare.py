# Tento soubor definuje skupinu příkazů `/info` pro Discord bota.
# Jeho hlavním úkolem je umožnit vyhledávání informací o mravencích
# na různých externích myrmekologických fórech.
#
# Funkce:
# - Definuje seznam fór (`ANT_FORUMS`) s jejich URL a parametry pro vyhledávání.
# - `search_forum_sync`: Synchronní funkce pro provedení web scrapingu na daném
#   fóru. Stáhne stránku s výsledky vyhledávání a parsuje ji pomocí
#   BeautifulSoup, aby získala relevantní odkazy, názvy a úryvky.
# - Příkaz `/info vyhledat`: Asynchronní příkaz, který přijímá dotaz od
#   uživatele. Spouští `search_forum_sync` v odděleném vlákně, aby
#   neblokoval bota, a postupně zobrazuje výsledky v Discord embed zprávě.
#
# Závislosti:
# - Externí knihovny: discord.py, requests, beautifulsoup4
# - Standardní knihovny: urllib.parse, typing, datetime, asyncio

import discord
from discord import app_commands
import urllib.parse
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
import datetime
import asyncio # Nový import pro asynchronní čekání

# Seznam fór k prohledávání
# Každé fórum má nyní 'search_path' pro specifickou vyhledávací URL a 'searchable' flag.
ANT_FORUMS: List[dict] = [
    {"name": "Myrmecofourmis (FR)", "url": "www.myrmecofourmis.org/", "search_path": "forum/search.php?keywords=", "link_prefix": "https://www.myrmecofourmis.org/", "searchable": True},
    {"name": "Ameiseninfos (DE)", "url": "ameiseninfos.de/Forum/app.php/portal", "searchable": False, "reason": "Vyhledávání není povoleno."}, # Toto fórum nelze prohledávat
    {"name": "Ameisenhaltung (DE)", "url": "www.ameisenhaltung.de/cafe/", "search_path": "search.php?keywords=", "link_prefix": "https://www.ameisenhaltung.de/cafe/", "searchable": True},
    {"name": "Ameisenforum (DE)", "url": "ameisenforum.de/", "search_path": "search.php?keywords=", "link_prefix": "https://ameisenforum.de/", "searchable": True}, # Opravená search_path
    {"name": "Antstore (DE/EN)", "url": "www.antstore.net/forum/", "search_path": "search.php?keywords=", "link_prefix": "https://www.antstore.net/forum/", "searchable": True},
    {"name": "Eusozial (DE)", "url": "eusozial.de/", "search_path": "search.php?keywords=", "link_prefix": "https://eusozial.de/", "searchable": True},
    {"name": "AntForum (NL)", "url": "www.antforum.nl/", "search_path": "search.php?keywords=", "link_prefix": "https://www.antforum.nl/", "searchable": True},
    {"name": "Paco Alarcon Hormigas (ES)", "url": "pacoalarcon-hormigas.blogspot.com/", "search_path": "search?q=", "link_prefix": "https://pacoalarcon-hormigas.blogspot.com/", "searchable": True},
    {"name": "Termites and Ants (EN)", "url": "termitesandants.blogspot.com/", "search_path": "search?q=", "link_prefix": "https://termitesandants.blogspot.com/", "searchable": True},
    # Formiculture nyní používá Google vyhledávání pro spolehlivější výsledky
    {"name": "Formiculture (EN)", "url": "www.google.com/", "search_path": "search?q=site%3Aformiculture.com+", "link_prefix": "", "searchable": True, "is_google_search": True},
]

# Vytvoření nové skupiny příkazů
info_group = app_commands.Group(name="info", description="Příkazy pro získávání informací o mravencích a hmyzu.")

# Funkce pro prohledávání fóra
# Zůstává synchronní, protože používá knihovnu requests
def search_forum_sync(forum_data: dict, query: str) -> List[dict]:
    """
    Prohledá dané fórum pro zadaný dotaz.
    Vrací seznam slovníků s 'title', 'link' a 'snippet'.
    """
    search_results = []
    found_links = set() # Použijeme sadu pro sledování již nalezených URL adres

    # Zkontrolujeme, zda je fórum prohledávatelné
    if not forum_data.get("searchable", True):
        return [] # Pokud není prohledávatelné, vrátíme prázdný seznam

    forum_url_base = forum_data["url"]
    search_path = forum_data.get("search_path")
    link_prefix = forum_data.get("link_prefix")
    is_google_search = forum_data.get("is_google_search", False)

    if not search_path:
        print(f"Chyba: Pro fórum {forum_data['name']} není definována 'search_path'.")
        return []

    # Pro Formiculture (Google vyhledávání)
    if is_google_search:
        # Dotaz pro Google bude "site:formiculture.com <uživatelský dotaz>"
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://{forum_url_base}{search_path}{encoded_query}"
    else:
        # Pro ostatní fóra zůstává původní logika
        encoded_query = urllib.parse.quote(query.replace(" ", "+"))
        search_url = f"https://{forum_url_base}{search_path}{encoded_query}"
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status() # Vyvolá HTTPError pro špatné odpovědi (4xx nebo 5xx)
        soup = BeautifulSoup(response.text, 'html.parser')

        print(f"DEBUG: Google Search URL: {search_url}")
        print(f"DEBUG: Google Response Status: {response.status_code}")
        if response.status_code != 200:
            print(f"DEBUG: Google Response Text (partial): {response.text[:500]}")

        if is_google_search:
            # Nové parsování pro Google výsledky na základě poskytnutého HTML
            # Hledáme hlavní kontejnery výsledků, což je často div s class='MjjYud'
            result_containers = soup.find_all('div', class_='MjjYud')

            print(f"DEBUG: Found {len(result_containers)} Google result containers.")

            for result_block in result_containers:
                title = ""
                href = ""
                snippet = ""

                # Hledáme odkaz a titulek. Odkaz je často v <a> tagu, titulek pak v <h3> uvnitř <a>.
                # Zkoušíme různé cesty k nalezení odkazu a titulku.
                # První pokus: a tag s h3 uvnitř (nejběžnější)
                title_link_tag = result_block.find('a')
                if title_link_tag:
                    title_h3 = title_link_tag.find('h3')
                    if title_h3:
                        title = title_h3.get_text(strip=True)
                        href = title_link_tag['href']
                    else:
                        # Druhý pokus: titulek je přímo v a tagu
                        title = title_link_tag.get_text(strip=True)
                        href = title_link_tag['href']

                    # Google někdy obaluje skutečnou URL do /url?q=...&sa=U...
                    if "/url?q=" in href:
                        try:
                            href = urllib.parse.unquote(href.split("/url?q=")[1].split("&sa=")[0])
                        except IndexError:
                            pass # Použijeme původní href, pokud je formát nečekaný

                # Hledáme snippet (popisek)
                # Snippet je často v divu s třídou 'VwiC3b' nebo v jiných textových elementech v rámci bloku.
                snippet_tag = result_block.find('div', class_='VwiC3b')
                if not snippet_tag:
                    # Alternativní třídy pro snippet, pokud 'VwiC3b' není nalezeno
                    snippet_tag = result_block.find('span', class_='aCOpNe') or \
                                  result_block.find('div', class_='lEBKkf') or \
                                  result_block.find('span', class_='st')
                
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                print(f"DEBUG: Found result - Title: {title}, Link: {href}, Snippet: {snippet[:50]}")

                # Zajištění, že odkaz je z Formiculture.com a není prázdný
                if title and href and "formiculture.com" in href:
                    if href in found_links:
                        continue

                    search_results.append({
                        "title": title,
                        "link": href,
                        "snippet": snippet
                    })
                    found_links.add(href)
                    if len(search_results) >= 3: # Omezíme na 3 výsledky
                        break
        else:
            # Původní parsování pro ostatní fóra
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                href = link['href']

                if not href.startswith(('http://', 'https://')):
                    if link_prefix:
                        href = urllib.parse.urljoin(link_prefix, href)
                    else:
                        continue

                if query.lower() in title.lower() or query.lower() in href.lower():
                    if href in found_links:
                        continue

                    snippet = ""
                    parent = link.find_parent()
                    if parent:
                        for sibling in parent.find_next_siblings():
                            if sibling.name == 'p' and sibling.get_text(strip=True):
                                snippet = sibling.get_text(strip=True)
                                break
                        if not snippet:
                            full_text = parent.get_text(strip=True)
                            snippet = (full_text[:100] + '...') if len(full_text) > 100 else full_text

                    if title and href:
                        search_results.append({
                            "title": title,
                            "link": href,
                            "snippet": snippet
                        })
                        found_links.add(href)
                        if len(search_results) >= 3:
                            break
    except requests.exceptions.RequestException as e:
        print(f"Chyba při prohledávání {forum_data['name']} ({forum_url_base}): {e}")
    return search_results


@info_group.command(name="vyhledat", description="Vyhledá informace o mravencích na vybraných fórech.")
@app_commands.describe(dotaz="Co chceš vyhledat?", forum_name="Volitelně vyber konkrétní fórum k prohledání.")
@app_commands.choices(forum_name=[
    app_commands.Choice(name=f["name"], value=f["name"]) for f in ANT_FORUMS
])
async def info_vyhledat(interaction: discord.Interaction, dotaz: str, forum_name: Optional[app_commands.Choice[str]] = None):
    await interaction.response.defer()

    embed = discord.Embed(
        title=f"Vyhledávání: \"{dotaz}\"",
        description="Probíhá vyhledávání na fórech...",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    embed.set_thumbnail(url="https://placehold.co/128x128/ADD8E6/000000?text=Mravenec") 

    all_results_found = False
    
    forums_to_search = []
    if forum_name:
        selected_forum_name_str = forum_name.value
        found_forum = next((f for f in ANT_FORUMS if f["name"] == selected_forum_name_str), None)
        if found_forum:
            forums_to_search.append(found_forum)
        else:
            await interaction.edit_original_response(embed=discord.Embed(
                title="Chyba",
                description=f"Fórum '{selected_forum_name_str}' nebylo nalezeno v seznamu.",
                color=discord.Color.red()
            ))
            return
    else:
        forums_to_search = ANT_FORUMS

    for i, forum_data in enumerate(forums_to_search):
        forum_name_display = forum_data["name"]
        
        if not forum_data.get("searchable", True):
            reason = forum_data.get("reason", "Není dostupné pro vyhledávání.")
            embed.add_field(name=f"Výsledky z: {forum_name_display}", value=f"⚠️ Fórum nelze prohledat: {reason}", inline=False)
            await interaction.edit_original_response(embed=embed)
            if not forum_name and i < len(forums_to_search) - 1:
                await asyncio.sleep(1)
            continue

        embed.description = f"Probíhá vyhledávání na fóru: **{forum_name_display}**..."
        await interaction.edit_original_response(embed=embed)

        results = await asyncio.to_thread(search_forum_sync, forum_data, dotaz)
        
        if results:
            all_results_found = True
            forum_results_text = ""
            for res in results:
                snippet = (res['snippet'][:100] + '...') if len(res['snippet']) > 100 else res['snippet']
                forum_results_text += f"**[{res['title']}]({res['link']})**\n> {snippet}\n"
            
            if len(forum_results_text) > 900:
                forum_results_text = forum_results_text[:900] + "... (pokračování zkráceno)"

            embed.add_field(name=f"Výsledky z: {forum_name_display}", value=forum_results_text, inline=False)
        else:
            embed.add_field(name=f"Výsledky z: {forum_name_display}", value="Žádné výsledky.", inline=False)

        if not forum_name and i < len(forums_to_search) - 1:
            await asyncio.sleep(1)

    if all_results_found:
        embed.description = "Zde jsou nejlepší výsledky nalezené na jednotlivých fórech:"
        embed.color = discord.Color.green()
    else:
        embed.description = "Bohužel se nepodařilo najít žádné relevantní výsledky. Zkuste prosím jiný dotaz."
        embed.color = discord.Color.red()

    embed.set_footer(text=f"Vyhledávání provedl: {interaction.user.display_name}")
    
    await interaction.edit_original_response(embed=embed)

# --- Instrukce pro integraci do hlavního souboru --
# 1. Ulož tento soubor jako `info_commands.py` ve stejné složce jako tvůj hlavní bot soubor.
# 2. Ujisti se, že máš nainstalované potřebné knihovny: pip install requests beautifulsoup4 discord.py
# 3. V hlavním souboru bota (např. main.py) importuj skupinu příkazů:
#    from info_commands import info_group
# 4. A zaregistruj ji do tree (stromu příkazů):
#    tree.add_command(info_group)
