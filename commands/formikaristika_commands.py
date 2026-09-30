import discord
from discord import app_commands
import requests
import xml.etree.ElementTree as ET
import re
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
import math

SITEMAP_URL = "https://formikaristika.wordpress.com/sitemap.xml"
CARE_GUIDE_URL = "https://formikaristika.wordpress.com/mravenci/chov/navod/"
DEFAULT_IMAGE_URL = "https://formikaristika.wordpress.com/wp-content/uploads/2016/06/cropped-logo-1.png"

def clean_html_text(soup_element):
    """
    Převede HTML element na text vhodný pro Discord.
    Zachová odkazy ve formátu [text](url) a obrázky.
    """
    text_parts = []
    for content in soup_element.contents:
        if content.name == "a" and content.get("href"):
            link_text = content.get_text(strip=True)
            if link_text:
                text_parts.append(f"[{link_text}]({content['href']})")
        elif content.name == "img":
            img_src = content.get("src")
            if img_src:
                text_parts.append(f"\n[Obrázek]({img_src})\n")
        elif content.name in ["strong", "b"]:
            text_parts.append(f"**{content.get_text(strip=True)}**")
        elif content.name in ["em", "i"]:
            text_parts.append(f"*{content.get_text(strip=True)}*")
        elif content.name == "br":
            text_parts.append("\n")
        elif isinstance(content, str):
            text_parts.append(content)
        else:
            text_parts.append(content.get_text(strip=True) if hasattr(content, "get_text") else str(content))

    return "".join(text_parts).strip()

def extract_images_from_element(soup_element):
    """Vrátí seznam URL všech obrázků v daném elementu."""
    images = []
    if hasattr(soup_element, "find_all"):
        for a in soup_element.find_all("a"):
            href = a.get("href")
            if href and href.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                images.append(href)
    
    if hasattr(soup_element, "find_all"):
        for img in soup_element.find_all("img"):
            src = img.get("src")
            if src and src not in images:
                images.append(src)
    
    if soup_element.name == "img" and soup_element.get("src"):
        if soup_element.get("src") not in images:
            images.append(soup_element.get("src"))

    return images

class ParagraphSelectorView(discord.ui.View):
    """View pro výběr konkrétních odstavců k odeslání do chatu."""
    def __init__(self, paragraphs, title):
        super().__init__(timeout=180)
        self.paragraphs = paragraphs
        self.title = title

        options = []
        for i, para in enumerate(self.paragraphs[:25]):
            label = (para[:90] + "...") if len(para) > 90 else para
            if not label:
                label = "Obrázek nebo formátování..."
            
            options.append(discord.SelectOption(
                label=f"{i+1}. {label}",
                value=str(i),
                description="Klikni pro výběr"
            ))

        if options:
            self.select = discord.ui.Select(
                placeholder="Vyber odstavce k odeslání (Multi-select)",
                min_values=1,
                max_values=len(options),
                options=options
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        final_text = f"**{self.title}**\n\n"
        selected_values = [int(v) for v in self.select.values]
        selected_values.sort()
        
        for idx in selected_values:
            final_text += self.paragraphs[idx] + "\n\n"

        if len(final_text) > 2000:
            parts = [final_text[i:i+2000] for i in range(0, len(final_text), 2000)]
            for part in parts:
                await interaction.channel.send(part)
        else:
            await interaction.channel.send(final_text)
            
        await interaction.followup.send("Text byl odeslán do kanálu.", ephemeral=True)

class CareGuideView(discord.ui.View):
    """View pro procházení strukturovaného návodu na chov."""
    def __init__(self, guide_data, main_browser_view_class, cog_instance):
        super().__init__(timeout=300)
        self.guide_data = guide_data
        self.main_browser_view_class = main_browser_view_class
        self.cog = cog_instance
        self.current_section = None
        self.page = 0
        self.items_per_page = 25
        self.max_pages = math.ceil(len(self.guide_data) / self.items_per_page) if self.guide_data else 1

        self.update_components()

    def update_components(self):
        self.clear_items()
        
        options = []
        start_idx = self.page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_batch = self.guide_data[start_idx:end_idx]

        for i, section in enumerate(current_batch):
            global_index = start_idx + i
            indent = "  " * (section["level"] - 1) 
            label = f"{indent}{section['title']}"
            if len(label) > 100:
                label = label[:97] + "..."
            
            options.append(discord.SelectOption(
                label=label,
                value=str(global_index),
                description=f"Sekce {global_index + 1}"
            ))

        if options:
            select = discord.ui.Select(
                placeholder=f"Vyber kapitolu (Strana {self.page + 1}/{self.max_pages})",
                options=options,
                custom_id="chapter_select",
                row=0
            )
            select.callback = self.select_callback
            self.add_item(select)

        if self.max_pages > 1:
            prev_btn = discord.ui.Button(
                label="Předchozí", 
                style=discord.ButtonStyle.secondary, 
                custom_id="prev_page", 
                disabled=(self.page == 0),
                row=1
            )
            next_btn = discord.ui.Button(
                label="Další", 
                style=discord.ButtonStyle.secondary, 
                custom_id="next_page", 
                disabled=(self.page >= self.max_pages - 1),
                row=1
            )
            self.add_item(prev_btn)
            self.add_item(next_btn)

        self.add_item(discord.ui.Button(label="Obsah", style=discord.ButtonStyle.primary, custom_id="toc_btn", row=2))
        self.add_item(discord.ui.Button(label="Vybrat text", style=discord.ButtonStyle.success, custom_id="send_text_btn", row=2))
        self.add_item(discord.ui.Button(label="Zpět do menu", style=discord.ButtonStyle.grey, custom_id="back_btn", row=2))

    async def select_callback(self, interaction: discord.Interaction):
        index = int(interaction.data["values"][0])
        self.current_section = self.guide_data[index]
        embed = self.create_section_embed(self.current_section)
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if "custom_id" in interaction.data:
            cid = interaction.data["custom_id"]
            
            if cid == "prev_page":
                self.page -= 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            
            elif cid == "next_page":
                self.page += 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            
            elif cid == "toc_btn":
                lines = ["**Obsah návodu:**"]
                for i, sec in enumerate(self.guide_data):
                    indent = "-" * (sec["level"] - 1)
                    lines.append(f"`{i+1}.` {indent} {sec['title']}")
                
                content = "\n".join(lines)
                if len(content) > 2000:
                    content = content[:1900] + "\n... (a další)"
                
                await interaction.response.send_message(content, ephemeral=True)
                return False

            elif cid == "send_text_btn":
                if not self.current_section or not self.current_section["paragraphs"]:
                    await interaction.response.send_message("Nejdřív vyber kapitolu, která má text.", ephemeral=True)
                    return False
                
                view = ParagraphSelectorView(self.current_section["paragraphs"], self.current_section["title"])
                await interaction.response.send_message("Vyber, které části textu chceš odeslat:", view=view, ephemeral=True)
                return False

            elif cid == "back_btn":
                embed = discord.Embed(
                    title="Formikaristika Prohlížeč",
                    description="Vítej v prohlížeči webu Formikaristika CZ.\nVyber kategorii pro procházení článků nebo použij rychlá tlačítka:",
                    color=discord.Color.green()
                )
                view = self.main_browser_view_class(self.cog)
                await interaction.response.edit_message(embed=embed, view=view)
                return False

        return True

    def create_section_embed(self, section):
        embed = discord.Embed(
            title=section["title"],
            color=discord.Color.dark_green(),
            url=CARE_GUIDE_URL
        )
        
        full_text = "\n\n".join(section["paragraphs"])
        if len(full_text) > 3500:
            description = full_text[:3500] + "\n\n*[Text je příliš dlouhý, pro zbytek použij 'Vybrat text']*..."
        elif len(full_text) == 0:
            description = "*Tato sekce obsahuje pouze podkapitoly, vyberte jednu z nich v menu.*"
        else:
            description = full_text

        embed.description = description
        
        if section.get("images"):
            embed.set_image(url=section["images"][0])
            embed.set_thumbnail(url=DEFAULT_IMAGE_URL)
        else:
            embed.set_thumbnail(url=DEFAULT_IMAGE_URL)

        subsections = section.get("subsections", [])
        if subsections:
            sub_titles = [sub["title"] for sub in subsections]
            embed.add_field(name="Podkapitoly", value="\n".join(f"• {t}" for t in sub_titles), inline=False)
            
        embed.set_footer(text=f"Formikaristika.wordpress.com | Návod na chov | {section['title']}")
        return embed

class CategoryArticlesView(discord.ui.View):
    def __init__(self, articles, category_name, main_view_class, cog):
        super().__init__(timeout=180)
        self.articles = articles
        self.category_name = category_name
        self.main_view_class = main_view_class
        self.cog = cog
        self.page = 0
        self.items_per_page = 25
        self.max_pages = math.ceil(len(articles) / self.items_per_page) if articles else 1
        
        self.update_components()
        
    def update_components(self):
        self.clear_items()
        
        options = []
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        batch = self.articles[start:end]
        
        for i, url in enumerate(batch):
            parsed = urlparse(url)
            slug = parsed.path.strip("/").split("/")[-1]
            label = slug.replace("-", " ").capitalize()
            if len(label) > 100:
                label = label[:97] + "..."
            
            global_index = start + i
            options.append(discord.SelectOption(
                label=label,
                value=str(global_index),
                description="Klikni pro zobrazení"
            ))
            
        if options:
            select = discord.ui.Select(placeholder=f"Vyber článek ({self.page+1}/{self.max_pages})", options=options, custom_id="article_select")
            select.callback = self.article_select_callback
            self.add_item(select)
            
        if self.max_pages > 1:
            self.add_item(discord.ui.Button(label="Předchozí", custom_id="prev", disabled=(self.page == 0), style=discord.ButtonStyle.secondary))
            self.add_item(discord.ui.Button(label="Další", custom_id="next", disabled=(self.page >= self.max_pages - 1), style=discord.ButtonStyle.secondary))
            
        self.add_item(discord.ui.Button(label="Zpět do kategorií", custom_id="back", style=discord.ButtonStyle.grey))

    async def article_select_callback(self, interaction: discord.Interaction):
        index = int(interaction.data["values"][0])
        url = self.articles[index]
        await interaction.response.defer()
        await self.cog.send_article_embed(interaction, url)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if "custom_id" in interaction.data:
            cid = interaction.data["custom_id"]
            if cid == "prev":
                self.page -= 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            elif cid == "next":
                self.page += 1
                self.update_components()
                await interaction.response.edit_message(view=self)
                return False
            elif cid == "back":
                embed = discord.Embed(
                    title="Formikaristika Prohlížeč",
                    description="Vítej v prohlížeči webu Formikaristika CZ.\nVyber kategorii pro procházení článků nebo použij rychlá tlačítka:",
                    color=discord.Color.green()
                )
                view = self.main_view_class(self.cog)
                await interaction.response.edit_message(embed=embed, view=view)
                return False
        return True

class FormikaristikaBrowserView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.add_category_select()

    def add_category_select(self):
        if not self.cog.categories:
            self.add_item(discord.ui.Select(
                placeholder="Načítám kategorie...",
                options=[discord.SelectOption(label="Načítání...", value="loading")],
                disabled=True,
                row=0
            ))
            return

        options = []
        sorted_cats = sorted(self.cog.categories.keys())
        for cat in sorted_cats[:25]:
            count = len(self.cog.categories[cat])
            options.append(discord.SelectOption(
                label=f"{cat} ({count})",
                value=cat[:100]
            ))

        select = discord.ui.Select(
            placeholder="Procházet kategorie webu",
            options=options,
            custom_id="category_select",
            row=0
        )
        select.callback = self.category_callback
        self.add_item(select)

    async def category_callback(self, interaction: discord.Interaction):
        cat_name = interaction.data["values"][0]
        articles = self.cog.categories.get(cat_name, [])
        
        embed = discord.Embed(
            title=f"Kategorie: {cat_name}",
            description=f"Nalezeno {len(articles)} článků. Vyber si jeden ze seznamu níže.",
            color=discord.Color.blue()
        )
        view = CategoryArticlesView(articles, cat_name, FormikaristikaBrowserView, self.cog)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Náhodný článek", style=discord.ButtonStyle.primary, row=1)
    async def random_article(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.cog.sitemap_urls:
            await interaction.followup.send("Sitemap zatím není načtena.", ephemeral=True)
            return
        import random
        url = random.choice(self.cog.sitemap_urls)
        await self.cog.send_article_embed(interaction, url)

    @discord.ui.button(label="Nejnovější článek", style=discord.ButtonStyle.success, row=1)
    async def latest_article(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.cog.sitemap_urls:
            await interaction.followup.send("Sitemap zatím není načtena.", ephemeral=True)
            return
        url = self.cog.sitemap_urls[0] 
        await self.cog.send_article_embed(interaction, url)

    @discord.ui.button(label="Návod na chov", style=discord.ButtonStyle.secondary, row=1)
    async def care_guide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.care_guide_data:
            await interaction.response.send_message("Návod se načítá...", ephemeral=True)
            await self.cog.load_care_guide()
            return

        embed = discord.Embed(
            title="Návod na chov mravenců",
            description="Kompletní průvodce pro začínající i pokročilé chovatele.\n\nVyber si kapitolu z nabídky níže.",
            color=discord.Color.dark_green()
        )
        embed.set_thumbnail(url=DEFAULT_IMAGE_URL)

        view = CareGuideView(self.cog.care_guide_data, FormikaristikaBrowserView, self.cog)
        await interaction.response.edit_message(embed=embed, view=view)

class FormikaristikaCommands(app_commands.Group):
    def __init__(self, bot: discord.Client):
        super().__init__(name="formikaristika", description="Příkazy pro web Formikaristika CZ")
        self.bot = bot
        self.sitemap_urls = []
        self.categories = {}
        self.species_map = {}
        self.care_guide_data = []
        
    async def on_ready(self):
        print("Načítám sitemapu Formikaristika CZ...")
        await self.load_sitemap()
        print("Načítám Návod na chov...")
        await self.load_care_guide()

    async def load_sitemap(self):
        try:
            response = requests.get(SITEMAP_URL, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                
                self.sitemap_urls = []
                self.species_map = {}
                self.categories = {}

                for url_elem in root.findall("sm:url", ns):
                    loc = url_elem.find("sm:loc", ns).text
                    self.sitemap_urls.append(loc)
                    
                    parsed = urlparse(loc)
                    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                    
                    if path_parts:
                        cat = path_parts[0].capitalize()
                        if cat.isdigit() and len(cat) == 4:
                            cat = "Blog (Archiv)"
                        
                        if cat not in self.categories:
                            self.categories[cat] = []
                        self.categories[cat].append(loc)

                    if "mravenci" in path_parts and len(path_parts) >= 3:
                        slug = path_parts[-1]
                        name = slug.replace("-", " ").capitalize()
                        self.species_map[name] = loc

                print(f"Sitemap: {len(self.sitemap_urls)} URL, {len(self.categories)} kategorií.")
            else:
                print(f"Chyba sitemap: {response.status_code}")
        except Exception as e:
            print(f"Výjimka sitemap: {e}")

    async def load_care_guide(self):
        try:
            response = requests.get(CARE_GUIDE_URL, timeout=10)
            if response.status_code != 200:
                return

            soup = BeautifulSoup(response.content, "html.parser")
            content_div = soup.find("div", class_="entry-content")
            if not content_div:
                return

            structure = []
            current_section = {
                "title": "Úvod", "level": 1, "paragraphs": [], "subsections": [], "images": []
            }
            structure.append(current_section)
            section_stack = [current_section]

            elements = content_div.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "figure"])

            for el in elements:
                if el.name in ["h1", "h2", "h3", "h4"]:
                    level = int(el.name[1])
                    title = el.get_text(strip=True)
                    
                    new_section = {
                        "title": title, "level": level, "paragraphs": [], "subsections": [], "images": []
                    }
                    structure.append(new_section)
                    
                    while section_stack and section_stack[-1]["level"] >= level:
                        section_stack.pop()
                    if section_stack:
                        section_stack[-1]["subsections"].append(new_section)
                    section_stack.append(new_section)
                    current_section = new_section
                else:
                    imgs = extract_images_from_element(el)
                    if imgs:
                        current_section["images"].extend(imgs)

                    text = clean_html_text(el)
                    if text:
                        current_section["paragraphs"].append(text)

            self.care_guide_data = structure
            print(f"Návod načten: {len(structure)} sekcí.")
        except Exception as e:
            print(f"Výjimka návod: {e}")

    async def send_article_embed(self, interaction: discord.Interaction, url: str):
        details = await self.fetch_article_details(url)
        embed = discord.Embed(color=discord.Color.green())
        embed.title = details["title"]
        embed.url = details["url"]
        embed.description = details["excerpt"]
        
        if details["image_url"]:
            embed.set_image(url=details["image_url"])
            
        last_modified = details.get("modified_time")
        if last_modified:
            try:
                dt_object = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                formatted_date = dt_object.strftime("%d.%m.%Y")
                embed.add_field(name="Poslední úprava", value=formatted_date, inline=False)
            except ValueError:
                pass
        
        embed.set_footer(text="Data z formikaristika.wordpress.com")
        await interaction.followup.send(embed=embed)

    async def fetch_article_details(self, url: str):
        def blocking_io():
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.content, "html.parser")
                    title = soup.find("meta", property="og:title")
                    title = title["content"] if title else soup.title.string
                    desc = soup.find("meta", property="og:description")
                    excerpt = desc["content"] if desc else "Bez popisu."
                    image = soup.find("meta", property="og:image")
                    image_url = image["content"] if image else None
                    mod_time = soup.find("meta", property="article:modified_time")
                    modified_time = mod_time["content"] if mod_time else None
                    return {"title": title, "url": url, "excerpt": excerpt, "image_url": image_url, "modified_time": modified_time}
            except Exception as e:
                return {"title": "Chyba", "url": url, "excerpt": str(e), "image_url": None, "modified_time": None}
            return {"title": "Neznámý", "url": url, "excerpt": "", "image_url": None, "modified_time": None}
        return await asyncio.to_thread(blocking_io)

    @app_commands.command(name="prochazet", description="Otevře interaktivní prohlížeč webu Formikaristika")
    async def browser(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Formikaristika Prohlížeč",
            description="Vítej v prohlížeči webu Formikaristika CZ.\nVyber kategorii pro procházení článků nebo použij rychlá tlačítka:",
            color=discord.Color.green()
        )
        view = FormikaristikaBrowserView(self)
        await interaction.response.send_message(embed=embed, view=view)

    async def species_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not self.species_map:
            return []
        choices = []
        for name, url in self.species_map.items():
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=url))
                if len(choices) >= 25:
                    break
        return choices

    @app_commands.command(name="profil", description="Zobrazí profil konkrétního druhu mravence")
    @app_commands.autocomplete(url=species_autocomplete)
    @app_commands.describe(url="Začni psát jméno druhu (např. Lasius niger)")
    async def profile(self, interaction: discord.Interaction, url: str):
        if not url.startswith("http"):
            await interaction.response.send_message(f"Druh '{url}' nebyl nalezen. Použij prosím našeptávač.", ephemeral=True)
            return

        await interaction.response.defer()
        
        slug = url.strip("/").split("/")[-1]
        genus_species = slug.split("-")
        
        if len(genus_species) >= 2:
            genus = genus_species[0].capitalize()
            species = genus_species[1]
            antweb_url = f"https://www.antweb.org/description.do?genus={genus.lower()}&species={species.lower()}&rank=species"
            antwiki_url = f"https://www.antwiki.org/wiki/{genus}_{species}"
        else:
            antweb_url = "https://www.antweb.org"
            antwiki_url = "https://www.antwiki.org"

        details = await self.fetch_article_details(url)
        embed = discord.Embed(color=discord.Color.green())
        embed.title = details["title"]
        embed.url = details["url"] 
        embed.description = details["excerpt"]
        
        if details["image_url"]:
            embed.set_image(url=details["image_url"])
        
        last_modified = details.get("modified_time")
        if last_modified:
            try:
                dt_object = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                formatted_date = dt_object.strftime("%d.%m.%Y")
                embed.add_field(name="Poslední úprava", value=formatted_date, inline=False)
            except ValueError:
                embed.add_field(name="Poslední úprava", value=last_modified, inline=False)
    
        links_text = f"[AntWeb]({antweb_url}) | [AntWiki]({antwiki_url})"
        embed.add_field(name="Externí zdroje", value=links_text, inline=False)
        embed.set_footer(text="Data z formikaristika.wordpress.com")
        await interaction.followup.send(embed=embed)
