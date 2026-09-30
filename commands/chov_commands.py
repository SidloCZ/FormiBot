import discord
from discord import app_commands
import json
import requests
from bs4 import BeautifulSoup
import re
import asyncio
import xml.etree.ElementTree as ET

from config import get_data_path
from commands.seznam_commands import species_autocomplete

bolton_data = {}
checklist_data = []
formikaristika_map = {}

BOLTON_FILE = get_data_path("bolton_species.json")
CHECKLIST_FILE = get_data_path("czech_checklist.json")

def load_chov_data():
    """Načte data z JSON souborů a sitemapu do globálních proměnných."""
    global bolton_data, checklist_data, formikaristika_map
    
    # 1. Načtení Bolton data
    try:
        with open(BOLTON_FILE, "r", encoding="utf-8") as f:
            bolton_data = json.load(f)
        print("Bolton data načtena (Chov).")
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {BOLTON_FILE} nenalezen.")
        bolton_data = {}

    # 2. Načtení Checklistu
    try:
        with open(CHECKLIST_FILE, "r", encoding="utf-8") as f:
            checklist_data = json.load(f)
        print("Czech checklist načten (Chov).")
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Soubor {CHECKLIST_FILE} nenalezen.")
        checklist_data = []

    # 3. Načtení sitemapy Formikaristika.cz pro ověřování odkazů
    try:
        response = requests.get("https://formikaristika.wordpress.com/sitemap.xml", timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            formikaristika_map = {}
            for url_elem in root.findall("sm:url", ns):
                loc = url_elem.find("sm:loc", ns).text
                if loc:
                    parts = loc.rstrip("/").split("/")
                    slug = parts[-1]
                    formikaristika_map[slug] = loc
            print(f"Sitemap načtena (Chov): {len(formikaristika_map)} URL.")
        else:
            print(f"Chyba při stahování sitemap (Chov): {response.status_code}")
    except Exception as e:
        print(f"Chyba při zpracování sitemap (Chov): {e}")

def get_gbif_link_sync(genus, species):
    """Získá odkaz na GBIF databázi pomocí veřejného API."""
    url = f"https://api.gbif.org/v1/species/match?name={genus}%20{species}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            usage_key = data.get("usageKey")
            if usage_key:
                return f"https://www.gbif.org/species/{usage_key}"
    except Exception as e:
        print(f"Chyba při získávání GBIF odkazu: {e}")
    return None

def get_antkeeping_data(genus, species):
    """Získá chovatelská data z antkeeping.info a náhled z AntCheck."""
    url = f"https://antkeeping.info/ants/{genus.lower()}-{species.lower()}/"
    data = {
        "subfamily": "NA",
        "worker_size": "NA",
        "queen_size": "NA",
        "temp": "NA",
        "humidity": "NA",
        "founding": "NA",
        "structure": "NA",
        "polymorphism": "NA",
        "hibernation": "NA",
        "nuptial_flight": "NA",
        "image_url": None,
        "url": url,
        "found": False
    }

    antcheck_url = f"https://antcheck.info/include/frontend/img/compressed/large/ants/{genus}_{species}.jpeg"
    antcheck_found = False
    
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        head_resp = requests.head(antcheck_url, headers=headers, timeout=3)
        if head_resp.status_code == 200:
            data["image_url"] = antcheck_url
            antcheck_found = True
    except Exception:
        pass

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=7)
        if response.status_code != 200:
            return data

        data["found"] = True
        soup = BeautifulSoup(response.content, "html.parser")

        if not antcheck_found:
            og_image = soup.find("meta", property="og:image")
            if og_image:
                img_link = og_image["content"]
                if img_link.startswith("/"):
                    img_link = "https://antkeeping.info" + img_link
                data["image_url"] = img_link

        size_containers = soup.find_all("div", class_="ant-size-container")
        for container in size_containers:
            title_tag = container.find("h5")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            size_footers = container.find_all("div", class_="size-footer")
            if size_footers:
                min_val = size_footers[0].get_text(strip=True)
                max_val = size_footers[-1].get_text(strip=True)
                size_str = min_val if min_val == max_val else f"{min_val} – {max_val}"

                if "Worker" in title:
                    data["worker_size"] = size_str
                elif "Queen" in title:
                    data["queen_size"] = size_str

        for row in soup.find_all(["tr"]):
            header = row.find("th")
            cell = row.find("td")
            if header and cell:
                header_text = header.get_text(strip=True)
                cell_text = cell.get_text(strip=True)
                
                if "Subfamily:" in header_text:
                    data["subfamily"] = cell_text.split("Tribe")[0].strip()
                if "Nest temperature:" in header_text:
                    data["temp"] = cell_text.split("\n")[0]
                if "Nest humidity:" in header_text:
                    data["humidity"] = cell_text.split("\n")[0]
                if "Colony founding:" in header_text:
                    data["founding"] = cell_text.split("\n")[0]
                if "Colony structure:" in header_text:
                    data["structure"] = cell_text.split("\n")[0]
                if "Worker polymorphism:" in header_text:
                    poly_val = cell_text.split("\n")[0].strip()
                    if poly_val.lower().startswith("yes"):
                        data["polymorphism"] = re.sub(r"^yes", "Ano", poly_val, flags=re.IGNORECASE)
                    elif poly_val.lower().startswith("no"):
                        data["polymorphism"] = re.sub(r"^no", "Ne", poly_val, flags=re.IGNORECASE)
                    elif not poly_val or poly_val.lower() in ["na", "n/a", "unknown"]:
                        data["polymorphism"] = "NA"
                    else:
                        data["polymorphism"] = poly_val
                if "Hibernation required:" in header_text:
                    hib_val = cell_text.split("\n")[0].strip()
                    if hib_val.lower().startswith("yes"):
                        data["hibernation"] = re.sub(r"^yes", "Ano", hib_val, flags=re.IGNORECASE)
                    elif hib_val.lower() == "no":
                        data["hibernation"] = "Ne"
                    elif hib_val.lower() == "no information":
                        data["hibernation"] = "Žádné informace"
                    else:
                        data["hibernation"] = hib_val

        script_content = str(soup)
        match = re.search(r"var chartData\s*=\s*\[(.*?)\];", script_content)
        if match:
            chart_str = match.group(1)
            try:
                chart_data = [int(x.strip()) for x in chart_str.split(",")]
                months_roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
                active_indices = [i for i, x in enumerate(chart_data) if x > 0]
                active_months_strs = []
                max_val = max(chart_data) if chart_data else 0
                
                if active_indices:
                    if len(active_indices) <= 2:
                        for i in active_indices:
                            val = chart_data[i]
                            month_str = months_roman[i]
                            if val == max_val:
                                month_str += "+"
                            active_months_strs.append(month_str)
                    else:
                        for i in active_indices:
                            val = chart_data[i]
                            month_str = months_roman[i]
                            ratio = val / max_val
                            if ratio >= 0.8:
                                month_str += "+++"
                            elif ratio >= 0.5:
                                month_str += "++"
                            elif ratio >= 0.25:
                                month_str += "+"
                            active_months_strs.append(month_str)
                    
                    data["nuptial_flight"] = ", ".join(active_months_strs)
                else:
                    data["nuptial_flight"] = "Žádná data o rojení"
            except Exception as e:
                print(f"Chyba při parsování grafu: {e}")
                data["nuptial_flight"] = "Chyba dat"
    except Exception as e:
        print(f"Chyba při scrapování antkeeping.info: {e}")
    
    return data

@app_commands.command(name="chov", description="Zobrazí podrobné chovatelské informace o konkrétním druhu.")
@app_commands.describe(species="Vědecký název druhu (např. Camponotus ligniperda)")
@app_commands.autocomplete(species=species_autocomplete)
async def chov_command(interaction: discord.Interaction, species: str):
    await interaction.response.defer()

    parts = species.split(" ")
    if len(parts) < 2:
        await interaction.followup.send("Prosím zadej celé vědecké jméno druhu (Rod druh).", ephemeral=True)
        return

    genus = parts[0].capitalize()
    species_name = parts[1].lower() 
    full_name = f"{genus} {species_name}"

    bolton_info = bolton_data.get(full_name, {})
    author_year = bolton_info.get("author_year_full", "Autor neznámý")

    in_czech = False
    if isinstance(checklist_data, list):
        in_czech = full_name in checklist_data
    elif isinstance(checklist_data, dict):
        in_czech = full_name in checklist_data

    loop = asyncio.get_running_loop()
    ak_task = loop.run_in_executor(None, get_antkeeping_data, genus, species_name)
    gbif_task = loop.run_in_executor(None, get_gbif_link_sync, genus, species_name)
    
    ak_data, gbif_url = await asyncio.gather(ak_task, gbif_task)

    embed = discord.Embed(
        title=f"Informace o chovu {genus} {species_name}",
        description=f"*{genus} {species_name}* {author_year}",
        color=discord.Color.dark_green()
    )

    if ak_data["subfamily"] != "NA" and ak_data["subfamily"] != "Neznámá":
        embed.set_author(name=f"Podčeleď: {ak_data['subfamily']}")

    size_info = f"**Dělnice:** {ak_data['worker_size']}\n**Královna:** {ak_data['queen_size']}"
    embed.add_field(name="Velikost", value=size_info, inline=True)
    embed.add_field(name="Hnízdo", value=f"**Teplota:** {ak_data['temp']}\n**Vlhkost:** {ak_data['humidity']}", inline=False)
    
    colony_info = f"**Zakládání:** {ak_data['founding']}\n**Struktura:** {ak_data['structure']}\n**Polymorfismus:** {ak_data['polymorphism']}"
    embed.add_field(name="Kolonie", value=colony_info, inline=True)
    embed.add_field(name="Diapauza", value=ak_data["hibernation"], inline=False)
    embed.add_field(name="Rojení", value=ak_data["nuptial_flight"], inline=False)

    if ak_data["image_url"]:
        embed.set_image(url=ak_data["image_url"])
    
    url_genus = genus
    url_species = species_name
    
    links_col1 = []
    links_col2 = []
    
    links_col1.append(f"[AntMaps](https://antmaps.org/?mode=species&species={url_genus}.{url_species})")
    links_col1.append(f"[AntWiki](https://antwiki.org/wiki/{url_genus}_{url_species})")
    links_col1.append(f"[AntWeb](https://www.antweb.org/description.do?rank=species&genus={url_genus}&species={url_species}&project=worldants)")
    links_col1.append(f"[AntCat](http://www.antcat.org/catalog/search?utf8=%E2%9C%93&st=m&qq={url_genus}%20{url_species}&commit=Go)")
    links_col1.append(f"[AntScout](https://antscout.com/species/{url_genus.lower()}-{url_species})")

    links_col2.append(f"[AntCheck](https://antcheck.info/species/{url_genus}_{url_species})")
    if ak_data["found"]:
        links_col2.append(f"[AntKeeping.info]({ak_data['url']})")
    if gbif_url:
        links_col2.append(f"[GBIF]({gbif_url})")
    links_col2.append(f"[iNaturalist](https://www.inaturalist.org/taxa/{url_genus}%20{url_species})")
    
    target_slug = f"{genus.lower()}-{species_name.lower()}"
    fallback_slug = f"{genus.lower()}-sp"
    formikaristika_url = formikaristika_map.get(target_slug) or formikaristika_map.get(fallback_slug)

    if formikaristika_url:
        links_col2.append(f"[Profil druhu (Formikaristika.cz)]({formikaristika_url})")
    
    if in_czech:
        links_col2.append(f"[Rozšíření v ČR (Nature.cz)](https://portal23.nature.cz/publik_syst/nd_nalez-public.php?akce=view&rfTaxon={url_genus}%20{url_species})")

    embed.add_field(name="Odkazy (Taxonomie & Mapy)", value="\n".join(links_col1), inline=True)
    embed.add_field(name="Odkazy (Chov & Pozorování)", value="\n".join(links_col2), inline=True)
    embed.set_footer(text="Data z antkeeping.info | Uvedené informace mohou být orientační")

    await interaction.followup.send(embed=embed)
