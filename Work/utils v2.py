import discord
import re

class PaginatorView(discord.ui.View):
    """
    Generická view pro stránkování Discord embedů.
    Umožňuje procházet seznamem embedů pomocí tlačítek.
    """
    def __init__(self, pages: list[discord.Embed], original_interaction: discord.Interaction, timeout=180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.original_interaction = original_interaction
        self.message = None

        self.previous_button = discord.ui.Button(label="Předchozí", style=discord.ButtonStyle.blurple, custom_id="prev_page")
        self.next_button = discord.ui.Button(label="Další", style=discord.ButtonStyle.blurple, custom_id="next_page")
        
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

        self.previous_button.callback = self.go_to_previous_page
        self.next_button.callback = self.go_to_next_page
        
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Kontrola, zda může s paginátorem interagovat pouze původní uživatel.
        """
        if interaction.user != self.original_interaction.user:
            await interaction.response.send_message("Tuto navigaci může ovládat pouze původní uživatel.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        """
        Aktualizuje stav tlačítek (disabled/enabled) a zápatí embedů.
        """
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)
        
        for i, page in enumerate(self.pages):
            footer_text = page.footer.text if page.footer and page.footer.text else ""
            footer_icon_url = page.footer and page.footer.icon_url or None 

            footer_text = re.sub(r" \| Stránka \d+/\d+$", "", footer_text).strip()
            
            page.set_footer(text=f"{footer_text} | Stránka {i + 1}/{len(self.pages)}", 
                            icon_url=footer_icon_url) 

    async def on_timeout(self):
        """
        Zavolá se, když vyprší časový limit pro interakci.
        Odstraní tlačítka ze zprávy.
        """
        if self.message:
            # Zakážeme tlačítka místo jejich odstranění, abychom se vyhnuli chybám
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                # Zpráva byla mezitím smazána, není co dělat
                pass
        # active_paginators je globální v main.py, takže zde ho neřešíme

    async def go_to_previous_page(self, interaction: discord.Interaction):
        # Odložíme odpověď, abychom měli více času
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            # Použijeme edit_original_response, protože jsme odpověď odložili
            await interaction.edit_original_response(embed=self.pages[self.current_page], view=self)

    async def go_to_next_page(self, interaction: discord.Interaction):
        # Odložíme odpověď, abychom měli více času
        await interaction.response.defer()
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            # Použijeme edit_original_response, protože jsme odpověď odložili
            await interaction.edit_original_response(embed=self.pages[self.current_page], view=self)
