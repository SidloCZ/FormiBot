import discord
from discord import app_commands
import urllib.parse

@app_commands.command(name="map", description="Zobrazí mapu rozšíření a odkazy pro daný rod nebo druh mravence.")
@app_commands.describe(rod="Rod mravence (nebo napiš 'help' pro nápovědu)", druh="Druh mravence (nepovinné)")
async def map_command(interaction: discord.Interaction, rod: str, druh: str = None):
    await interaction.response.defer()

    rod = rod.strip()
    if druh:
        druh = druh.strip()

    # 1. Varianta: Nápověda (rod == "help")
    if rod.lower() == "help":
        embed = discord.Embed(
            description="*Je nutné napsat Rod a druh ve správném formátu a bez chyb.*",
            color=discord.Color.blue()
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/661985293834125342/808308254081417227/acz_map_command.png")
        await interaction.followup.send(embed=embed)
        return

    rod_fmt = rod.capitalize()
    druh_fmt = druh.lower() if druh else None
    rod_safe = urllib.parse.quote(rod_fmt)
    
    # 2. Varianta: Zobrazení pouze rodu (druh není zadán)
    if not druh_fmt:
        antmaps_url = f"https://antmaps.org/?mode=diversity&genus={rod_safe}"
        antweb_url = f"https://www.antweb.org/description.do?rank=genus&genus={rod_safe}&project=worldants"
        antwiki_url = f"https://antwiki.org/wiki/{rod_safe}"
        antcat_url = f"http://www.antcat.org/catalog/search?utf8=%E2%9C%93&st=m&qq={rod_safe}&commit=Go"
        inaturalist_url = f"https://www.inaturalist.org/taxa/{rod_safe}"
        
        image_url = f"https://api.antapi.org/antmaps/{rod_safe}.png"

        description = (
            f"[AntWeb](<{antweb_url}>) | "
            f"[AntWiki](<{antwiki_url}>) | "
            f"[AntCat](<{antcat_url}>) | "
            f"[iNaturalist](<{inaturalist_url}>)"
        )

        embed = discord.Embed(
            title=rod_fmt,
            url=antmaps_url,
            description=description,
            color=discord.Color.green()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Data: AntMaps.org, Image: AntApi.org")
        await interaction.followup.send(embed=embed)

    # 3. Varianta: Zobrazení rodu a druhu
    else:
        druh_safe = urllib.parse.quote(druh_fmt)
        full_name_safe = urllib.parse.quote(f"{rod_fmt} {druh_fmt}")
        
        antmaps_url = f"https://antmaps.org/?mode=species&species={rod_safe}.{druh_safe}"
        antweb_url = f"https://www.antweb.org/description.do?rank=species&genus={rod_safe}&species={druh_safe}&project=worldants"
        antwiki_url = f"https://antwiki.org/wiki/{rod_safe}_{druh_safe}"
        antcat_url = f"http://www.antcat.org/catalog/search?utf8=%E2%9C%93&st=m&qq={full_name_safe}&commit=Go"
        inaturalist_url = f"https://www.inaturalist.org/taxa/{full_name_safe}"
        
        image_url = f"https://api.antapi.org/antmaps/{rod_safe}/{druh_safe}.png"

        description = (
            f"[AntWeb](<{antweb_url}>) | "
            f"[AntWiki](<{antwiki_url}>) | "
            f"[AntCat](<{antcat_url}>) | "
            f"[iNaturalist](<{inaturalist_url}>)"
        )

        embed = discord.Embed(
            title=f"{rod_fmt} {druh_fmt}",
            url=antmaps_url,
            description=description,
            color=discord.Color.green()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Data: AntMaps.org, Image: AntApi.org")
        await interaction.followup.send(embed=embed)
