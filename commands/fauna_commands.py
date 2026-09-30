import discord
from discord import app_commands
import requests
from bs4 import BeautifulSoup
import urllib.parse
import asyncio
import json

fauna_group = app_commands.Group(name="fauna", description="Vyhledávání inzerátů na prodej mravenců a hmyzu.")

def search_faunaportal(query: str) -> list[dict]:
    base_url = "https://www.faunaportal.cz/inzeraty"
    search_url = f"{base_url}?name={urllib.parse.quote_plus(query)}"
    results = []

    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        ad_listings = soup.find_all("div", class_="chakra-stack css-1l48e7e")

        for ad in ad_listings:
            link_tag = ad.find("a", class_="chakra-linkbox__overlay css-1v8v44t")
            title_tag = ad.find("h3", class_="chakra-heading css-15q0f1v")
            description_tag = ad.find("p", class_="chakra-text css-1g9t404")

            if link_tag and title_tag:
                title = title_tag.get_text(strip=True)
                relative_url = link_tag.get("href")
                full_url = urllib.parse.urljoin("https://www.faunaportal.cz/", relative_url)
                description = (description_tag.get_text(strip=True)[:100] + "...") if description_tag else "Popis není k dispozici."
                results.append({"title": title, "url": full_url, "description": description})
                if len(results) >= 4:
                    break
    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování z Faunaportal.cz pro dotaz '{query}': {e}")
    except Exception as e:
        print(f"Neočekávaná chyba při parsování Faunaportal.cz: {e}")
    
    return results

def search_ifauna(query: str) -> list[dict]:
    base_url = "https://www.ifauna.cz/inzerce/"
    search_url = f"{base_url}?hledat={urllib.parse.quote_plus(query)}"
    results = []

    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        script_tags = soup.find_all("script", type="application/ld+json")
        for script in script_tags:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "CollectionPage" and data.get("mainEntity", {}).get("@type") == "ItemList":
                    for item_list_element in data["mainEntity"].get("itemListElement", []):
                        item = item_list_element.get("item", {})
                        if item.get("@type") == "Product" and item.get("name") and item.get("url"):
                            title = item["name"]
                            url = item["url"]
                            description = (item.get("description", "Popis není k dispozici.")[:100] + "...")
                            results.append({"title": title, "url": url, "description": description})
                            if len(results) >= 4:
                                break
                    if len(results) >= 4:
                        break
            except json.JSONDecodeError:
                continue
        
        if not results:
            ad_listings = soup.find_all("div", class_="if-advertising-item")
            for ad in ad_listings:
                link_tag = ad.find("a", class_="if-advertising-item__link")
                title_tag = ad.find("h3", class_="if-advertising-item__title")
                description_tag = ad.find("div", class_="if-advertising-item__text")

                if link_tag and title_tag:
                    title = title_tag.get_text(strip=True)
                    full_url = link_tag.get("href")
                    description = (description_tag.get_text(strip=True)[:100] + "...") if description_tag else "Popis není k dispozici."
                    results.append({"title": title, "url": full_url, "description": description})
                    if len(results) >= 4:
                        break

    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování z iFauna.cz pro dotaz '{query}': {e}")
    except Exception as e:
        print(f"Neočekávaná chyba při parsování iFauna.cz: {e}")
    
    return results

def search_faunaaflora(query: str) -> list[dict]:
    base_url = "https://faunaaflora.cz/cs/inzeraty"
    search_url = f"{base_url}?se=1&search={urllib.parse.quote_plus(query)}"
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(search_url, timeout=10, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        item_container = soup.find("div", class_="items_list")
        if not item_container:
            item_container = soup

        ad_listings = item_container.find_all("div", class_="item_box")

        for ad in ad_listings:
            title_tag = ad.find("h3", class_="title")
            link_tag = title_tag.find("a") if title_tag else None
            description_tag = ad.find("div", class_="desc")

            if link_tag and title_tag:
                title = link_tag.get_text(strip=True)
                relative_url = link_tag.get("href")
                full_url = urllib.parse.urljoin("https://faunaaflora.cz/", relative_url)
                description = (description_tag.get_text(strip=True)[:100] + "...") if description_tag else "Popis není k dispozici."
                results.append({"title": title, "url": full_url, "description": description})
                if len(results) >= 4:
                    break
    except requests.exceptions.RequestException as e:
        print(f"Chyba při stahování z Faunaaflora.cz pro dotaz '{query}': {e}")
    except Exception as e:
        print(f"Neočekávaná chyba při parsování Faunaaflora.cz: {e}")

    return results

@fauna_group.command(name="hledat", description="Vyhledá inzeráty na Faunaportal.cz, iFauna.cz a Faunaaflora.cz.")
@app_commands.describe(dotaz="Co chceš vyhledat? (např. 'Camponotus ligniperda', 'mravenci')")
async def fauna_hledat(interaction: discord.Interaction, dotaz: str):
    await interaction.response.defer()

    faunaportal_results, ifauna_results, faunaaflora_results = await asyncio.gather(
        asyncio.to_thread(search_faunaportal, dotaz),
        asyncio.to_thread(search_ifauna, dotaz),
        asyncio.to_thread(search_faunaaflora, dotaz)
    )

    embed = discord.Embed(
        title=f"Výsledky vyhledávání inzerátů pro: \"{dotaz}\"",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Hledáno na Faunaportal.cz, iFauna.cz a Faunaaflora.cz")

    def add_results_field(site_name: str, results: list[dict]):
        if not results:
            embed.add_field(name=site_name, value="Žádné výsledky nalezeny.", inline=False)
            return

        field_value = ""
        ads_added = 0
        for ad in results:
            ad_string = f"**{ads_added + 1}. [{ad['title']}]({ad['url']})**\n{ad['description']}\n"
            if len(field_value) + len(ad_string) > 1024:
                break
            field_value += ad_string
            ads_added += 1
        
        embed.add_field(name=site_name, value=field_value, inline=False)

    add_results_field("Faunaportal.cz", faunaportal_results)
    add_results_field("iFauna.cz", ifauna_results)
    add_results_field("Faunaaflora.cz", faunaaflora_results)

    await interaction.followup.send(embed=embed)
