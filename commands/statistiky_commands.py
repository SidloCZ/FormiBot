import discord
from discord import app_commands
import matplotlib.pyplot as plt
import io
import datetime
import json
import re
import statistics
from typing import Optional

from utils import PaginatorView

statistiky_group = app_commands.Group(name="statistiky", description="Zobrazuje různé statistiky o chovaných mravencích.")

@statistiky_group.command(name="seznamy", description="Zobrazí statistiky aktivních i historických kolonií a druhů.")
async def statistiky_seznamy(interaction: discord.Interaction):
    user_ants_data = getattr(interaction.client, 'user_ants', {})
    
    if not user_ants_data:
        await interaction.response.send_message("Zatím nejsou k dispozici žádné statistiky, nikdo si nepřidal žádné mravence.", ephemeral=True)
        return

    await interaction.response.defer()

    total_colonies_server = 0
    unique_species_active = set()
    unique_species_total = set()
    user_with_ants_count = len(user_ants_data)
    
    species_colony_counts = {}
    user_colony_counts = {}

    colony_counts_per_user_list = []
    species_counts_active_per_user_list = []
    species_counts_total_per_user_list = []

    for user_id, ants_data in user_ants_data.items():
        user_total_colonies = 0
        user_active_species_count = 0
        user_total_species_count = 0

        for ant_name, count in ants_data.items():
            total_colonies_server += count
            unique_species_total.add(ant_name)
            user_total_species_count += 1

            if count > 0:
                unique_species_active.add(ant_name)
                user_active_species_count += 1
            
            species_colony_counts[ant_name] = species_colony_counts.get(ant_name, 0) + count
            user_total_colonies += count

        user_colony_counts[user_id] = user_total_colonies
        
        colony_counts_per_user_list.append(user_total_colonies)
        species_counts_active_per_user_list.append(user_active_species_count)
        species_counts_total_per_user_list.append(user_total_species_count)

    avg_colonies = total_colonies_server / user_with_ants_count if user_with_ants_count > 0 else 0
    median_colonies_per_user = statistics.median(colony_counts_per_user_list) if colony_counts_per_user_list else 0
    try:
        mode_colonies_per_user = statistics.multimode(colony_counts_per_user_list)
        mode_colonies_per_user_str = str(mode_colonies_per_user[0]) if mode_colonies_per_user else "N/A"
    except statistics.StatisticsError:
        mode_colonies_per_user_str = "N/A"

    average_unique_species_per_user = sum(species_counts_active_per_user_list) / user_with_ants_count if user_with_ants_count > 0 else 0
    median_species_per_user = statistics.median(species_counts_active_per_user_list) if species_counts_active_per_user_list else 0
    try:
        mode_species_per_user = statistics.multimode(species_counts_active_per_user_list)
        mode_species_per_user_str = str(mode_species_per_user[0]) if mode_species_per_user else "N/A"
    except statistics.StatisticsError:
        mode_species_per_user_str = "N/A"

    embed = discord.Embed(
        title="Statistiky chovaných mravenců",
        description="Přehled statistik na tomto serveru. Rozlišujeme **Aktivní** (aktuálně chované) a **Celkem** (včetně druhů chovaných v minulosti).",
        color=discord.Color.purple()
    )

    embed.add_field(name="Celkem uživatelů se seznamem", value=str(user_with_ants_count), inline=True)
    embed.add_field(name="Celkem chovaných kolonií", value=str(total_colonies_server), inline=True)
    embed.add_field(
        name="Unikátních druhů", 
        value=f"Aktivních: {len(unique_species_active)}\nCelkem: {len(unique_species_total)}", 
        inline=True
    )
    embed.add_field(name="Kolonií na uživatele", 
                    value=f"Průměr: {avg_colonies:.2f}\nMedián: {median_colonies_per_user}\nModus: {mode_colonies_per_user_str}", 
                    inline=True)
    embed.add_field(name="Druhů na uživatele (Aktivní)", 
                    value=f"Průměr: {average_unique_species_per_user:.2f}\nMedián: {median_species_per_user}\nModus: {mode_species_per_user_str}", 
                    inline=True)
    
    top_10_species = []
    if species_colony_counts:
        active_species_counts = {k: v for k, v in species_colony_counts.items() if v > 0}
        sorted_species_counts = sorted(active_species_counts.items(), key=lambda item: item[1], reverse=True)
        top_10_species = sorted_species_counts[:10]
        
        top_species_text = ""
        for i, (species, count) in enumerate(top_10_species):
            top_species_text += f"{i+1}. {species}: {count} kolonií\n"
        
        if not top_species_text:
            top_species_text = "Žádné aktivní kolonie."
        embed.add_field(name="Top 10 nejčastějších druhů (aktivní)", value=top_species_text, inline=False)
    else:
        embed.add_field(name="Top 10 nejčastějších druhů", value="Zatím nejsou dostupné žádné druhy.", inline=False)

    if user_colony_counts:
        sorted_users_by_colonies = sorted(user_colony_counts.items(), key=lambda item: item[1], reverse=True)
        top_10_users = sorted_users_by_colonies[:10]

        top_users_text = ""
        for i, (user_id, count) in enumerate(top_10_users):
            user = interaction.client.get_user(int(user_id))
            user_display_name = user.display_name if user else f"Neznámý ({user_id})"
            top_users_text += f"{i+1}. {user_display_name}: {count} kolonií\n"
        embed.add_field(name="Top 10 chovatelů (podle počtu kolonií)", value=top_users_text, inline=False)
    else:
        embed.add_field(name="Top 10 chovatelů", value="Zatím nejsou dostupní žádní chovatelé.", inline=False)
        
    if species_colony_counts:
        least_common_species = []
        for species, count in species_colony_counts.items():
            if 0 < count <= 2: 
                least_common_species.append((species, count))
        
        if least_common_species:
            least_common_species_sorted = sorted(least_common_species, key=lambda item: item[0].lower())
            
            least_common_text = ""
            for species, count in least_common_species_sorted[:10]:
                least_common_text += f"- {species}: {count} kolonií\n"
            embed.add_field(name="Nejméně zastoupené druhy (1–2 kolonie)", value=least_common_text, inline=False)
        else:
            embed.add_field(name="Nejméně zastoupené druhy", value="Všechny aktivní druhy mají více než 2 kolonie.", inline=False)

    await interaction.followup.send(embed=embed)

    if top_10_species:
        species_names = [item[0] for item in top_10_species]
        species_counts_values = [item[1] for item in top_10_species]

        plt.figure(figsize=(10, 6))
        plt.bar(species_names, species_counts_values, color='skyblue')
        plt.xlabel('Druh mravence')
        plt.ylabel('Počet kolonií')
        plt.title('Top 10 nejčastějších mravenčích druhů (Aktivní)')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        file = discord.File(buf, filename="top_species_chart.png")
        
        original_message = await interaction.original_response()
        embed.set_image(url="attachment://top_species_chart.png")
        await original_message.edit(embed=embed, attachments=[file])


@statistiky_group.command(name="historie", description="Zobrazí historický vývoj statistik (včetně porovnání aktivních vs. historie).")
async def statistiky_historie(interaction: discord.Interaction):
    await interaction.response.defer()

    historical_data = getattr(interaction.client, 'historical_ants_data', {})

    if not historical_data:
        await interaction.followup.send("Zatím nejsou k dispozici žádná historická data.", ephemeral=True)
        return

    sorted_dates = sorted(historical_data.keys())

    dates = []
    total_colonies_over_time = []
    unique_species_active_over_time = []
    unique_species_total_over_time = []
    users_with_lists_over_time = []
    avg_colonies_per_user_over_time = [] 
    med_colonies_per_user_over_time = [] 
    avg_species_per_user_over_time = []
    med_species_per_user_over_time = []

    TOP_N_SPECIES = 5
    overall_species_counts = {}
    
    for date_str in sorted_dates:
        snapshot = historical_data[date_str]
        for user_id, ants_data in snapshot.items():
            for ant_name, count in ants_data.items():
                if count > 0:
                    overall_species_counts[ant_name] = overall_species_counts.get(ant_name, 0) + count
    
    sorted_overall_species = sorted(overall_species_counts.items(), key=lambda item: item[1], reverse=True)
    top_n_species_names = [species for species, count in sorted_overall_species[:TOP_N_SPECIES]]
    top_n_species_historical_counts = {name: [] for name in top_n_species_names}

    for date_str in sorted_dates:
        snapshot = historical_data[date_str]
        current_total_colonies = 0
        current_active_species_set = set()
        current_total_species_set = set()
        current_users_with_lists = len(snapshot)
        snapshot_colony_counts = []
        snapshot_active_species_counts = []
        current_snapshot_species_counts = {}
        
        for user_id, ants_data in snapshot.items():
            user_colonies = 0
            user_active_species = 0
            
            for ant_name, count in ants_data.items():
                current_total_colonies += count
                current_total_species_set.add(ant_name)
                
                if count > 0:
                    current_active_species_set.add(ant_name)
                    current_snapshot_species_counts[ant_name] = current_snapshot_species_counts.get(ant_name, 0) + count
                    user_active_species += 1
                
                user_colonies += count
            
            snapshot_colony_counts.append(user_colonies)
            snapshot_active_species_counts.append(user_active_species)
        
        dates.append(date_str)
        total_colonies_over_time.append(current_total_colonies)
        unique_species_active_over_time.append(len(current_active_species_set))
        unique_species_total_over_time.append(len(current_total_species_set))
        users_with_lists_over_time.append(current_users_with_lists)

        if current_users_with_lists > 0:
            avg_colonies = current_total_colonies / current_users_with_lists
            avg_species = sum(snapshot_active_species_counts) / current_users_with_lists
        else:
            avg_colonies = 0
            avg_species = 0
        
        avg_colonies_per_user_over_time.append(avg_colonies)
        avg_species_per_user_over_time.append(avg_species)
        
        med_colonies = statistics.median(snapshot_colony_counts) if snapshot_colony_counts else 0
        med_species = statistics.median(snapshot_active_species_counts) if snapshot_active_species_counts else 0
        
        med_colonies_per_user_over_time.append(med_colonies)
        med_species_per_user_over_time.append(med_species)

        for species_name in top_n_species_names:
            top_n_species_historical_counts[species_name].append(current_snapshot_species_counts.get(species_name, 0))

    all_embeds = []
    all_files = []

    # Graf 1: Celkové počty
    plt.figure(figsize=(12, 7))
    plt.plot(dates, total_colonies_over_time, marker='o', linestyle='-', color='blue', label='Celkem kolonií')
    plt.plot(dates, unique_species_total_over_time, marker='x', linestyle='--', color='lightgreen', label='Celkem druhů (vč. historie)')
    plt.plot(dates, unique_species_active_over_time, marker='x', linestyle='-', color='darkgreen', linewidth=2, label='Aktivních druhů')
    plt.plot(dates, users_with_lists_over_time, marker='s', linestyle=':', color='red', label='Uživatelů se seznamem')
    plt.xlabel('Datum')
    plt.ylabel('Počet')
    plt.title('Vývoj počtu kolonií a druhů (Aktivní vs. Historie)')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    buf1 = io.BytesIO()
    plt.savefig(buf1, format='png')
    buf1.seek(0)
    plt.close()

    file1 = discord.File(buf1, filename="history_total_chart.png")
    all_files.append(file1)

    embed1 = discord.Embed(
        title="Historie: Aktivní vs. Celkové počty",
        description="Graf ukazuje rozdíl mezi celkovým počtem zaznamenaných druhů (světle zelená) a aktuálně chovanými druhy (tmavě zelená).",
        color=discord.Color.teal()
    )
    embed1.set_image(url="attachment://history_total_chart.png")
    all_embeds.append(embed1)

    # Graf 2: Průměr na uživatele
    plt.figure(figsize=(12, 7))
    plt.plot(dates, avg_colonies_per_user_over_time, marker='o', linestyle='-', color='purple', label='Průměr kolonií/uživatel')
    plt.plot(dates, med_colonies_per_user_over_time, marker='x', linestyle='--', color='darkviolet', label='Medián kolonií/uživatel')
    plt.plot(dates, avg_species_per_user_over_time, marker='o', linestyle='-', color='orange', label='Průměr (aktivních) druhů/uživatel')
    plt.plot(dates, med_species_per_user_over_time, marker='x', linestyle='--', color='darkorange', label='Medián (aktivních) druhů/uživatel')
    plt.xlabel('Datum')
    plt.ylabel('Počet')
    plt.title('Vývoj průměrného počtu kolonií na uživatele')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    buf2 = io.BytesIO()
    plt.savefig(buf2, format='png')
    buf2.seek(0)
    plt.close()

    file2 = discord.File(buf2, filename="history_avg_chart.png")
    all_files.append(file2)

    embed2 = discord.Embed(
        title="Historie: Průměry na uživatele",
        description="Vývoj průměrného počtu kolonií na jednoho chovatele.",
        color=discord.Color.dark_teal()
    )
    embed2.set_image(url="attachment://history_avg_chart.png")
    all_embeds.append(embed2)

    # Graf 3: Top N druhů
    plt.figure(figsize=(12, 7))
    colors = ['blue', 'green', 'red', 'purple', 'orange']
    markers = ['o', 'x', 's', 'D', '^']

    for i, species_name in enumerate(top_n_species_names):
        plt.plot(dates, top_n_species_historical_counts[species_name], 
                 marker=markers[i % len(markers)], 
                 linestyle='-', 
                 color=colors[i % len(colors)], 
                 label=species_name)

    plt.xlabel('Datum')
    plt.ylabel('Počet kolonií')
    plt.title(f'Vývoj počtu kolonií pro Top {TOP_N_SPECIES} druhů')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()

    buf3 = io.BytesIO()
    plt.savefig(buf3, format='png')
    buf3.seek(0)
    plt.close()

    file3 = discord.File(buf3, filename="history_top_species.png")
    all_files.append(file3)

    embed3 = discord.Embed(
        title=f"Historie: Top {TOP_N_SPECIES} druhů",
        description="Vývoj počtu aktivních kolonií pro nejčastější druhy.",
        color=discord.Color.orange()
    )
    embed3.set_image(url="attachment://history_top_species.png")
    all_embeds.append(embed3)

    await interaction.followup.send(embeds=all_embeds, files=all_files)


@statistiky_group.command(name="zobrazit", description="Zobrazí osobní statistiky chovatele (žebříček, graf, podíl).")
@app_commands.describe(uzivatel="Chovatel, jehož statistiky chceš vidět (volitelné).")
async def statistiky_zobrazit(interaction: discord.Interaction, uzivatel: Optional[discord.Member] = None):
    target_user = uzivatel or interaction.user
    target_id = str(target_user.id)
    
    user_ants_data = getattr(interaction.client, 'user_ants', {})
    
    if target_id not in user_ants_data or not user_ants_data[target_id]:
        msg = "Tento uživatel nemá žádné mravence v seznamu." if uzivatel else "Nemáš žádné mravence v seznamu. Použij `/seznam pridat`."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    await interaction.response.defer()

    my_ants = user_ants_data[target_id]
    active_ants = {k: v for k, v in my_ants.items() if v > 0}
    
    my_total_colonies = sum(active_ants.values())
    my_species_count = len(active_ants)
    
    genera_counts = {}
    for species, count in active_ants.items():
        genus = species.split()[0].capitalize()
        genera_counts[genus] = genera_counts.get(genus, 0) + count
    
    dominant_genus = "N/A"
    if genera_counts:
        dominant_genus = max(genera_counts, key=genera_counts.get)
        dominant_genus_count = genera_counts[dominant_genus]
        dominant_percent = (dominant_genus_count / my_total_colonies) * 100 if my_total_colonies > 0 else 0
        dominant_text = f"{dominant_genus} ({dominant_percent:.1f} %)"
    else:
        dominant_text = "Žádné aktivní kolonie"

    users_by_colonies = []
    users_by_species = []
    server_total_colonies = 0

    for uid, data in user_ants_data.items():
        u_active = {k: v for k, v in data.items() if v > 0}
        u_colonies = sum(u_active.values())
        u_species = len(u_active)
        
        server_total_colonies += u_colonies
        users_by_colonies.append((uid, u_colonies))
        users_by_species.append((uid, u_species))
    
    users_by_colonies.sort(key=lambda x: x[1], reverse=True)
    users_by_species.sort(key=lambda x: x[1], reverse=True)
    
    rank_colonies = next((i + 1 for i, (uid, _) in enumerate(users_by_colonies) if uid == target_id), "-")
    rank_species = next((i + 1 for i, (uid, _) in enumerate(users_by_species) if uid == target_id), "-")
    
    total_users = len(user_ants_data)
    server_share = (my_total_colonies / server_total_colonies * 100) if server_total_colonies > 0 else 0

    embed = discord.Embed(
        title=f"Osobní statistiky: {target_user.display_name}",
        description=f"Detailní přehled chovu uživatele {target_user.mention}.",
        color=target_user.color if target_user.color != discord.Color.default() else discord.Color.blue()
    )
    if target_user.avatar:
        embed.set_thumbnail(url=target_user.avatar.url)

    embed.add_field(name="Kolonie", value=f"**{my_total_colonies}**", inline=True)
    embed.add_field(name="Druhy", value=f"**{my_species_count}**", inline=True)
    embed.add_field(name="Dominantní rod", value=dominant_text, inline=True)
    
    rank_text = (
        f"**#{rank_colonies}** v počtu kolonií\n"
        f"**#{rank_species}** v počtu druhů\n"
        f"*(z celkem {total_users} chovatelů)*"
    )
    embed.add_field(name="Pozice na serveru", value=rank_text, inline=True)
    embed.add_field(name="Podíl na serveru", value=f"Vlastníš **{server_share:.2f} %**\nvšech mravenců na serveru!", inline=True)

    if active_ants:
        sorted_my_ants = sorted(active_ants.items(), key=lambda x: x[1], reverse=True)[:10]
        names = [x[0] for x in sorted_my_ants][::-1]
        values = [x[1] for x in sorted_my_ants][::-1]
        
        plt.figure(figsize=(10, 6))
        
        bar_color = target_user.color.to_rgb() if target_user.color != discord.Color.default() else (0.1, 0.5, 0.7)
        if isinstance(bar_color, tuple) and max(bar_color) > 1:
            bar_color = tuple(c/255 for c in bar_color)
            
        bars = plt.barh(names, values, color=bar_color)
        
        plt.xlabel('Počet kolonií')
        plt.title(f'Top {len(names)} druhů uživatele {target_user.display_name}')
        plt.grid(axis='x', linestyle='--', alpha=0.7)
        
        for bar in bars:
            width = bar.get_width()
            plt.text(width + 0.1, bar.get_y() + bar.get_height()/2, 
                     f'{int(width)}', 
                     ha='left', va='center', fontweight='bold')

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        file = discord.File(buf, filename="user_stats.png")
        embed.set_image(url="attachment://user_stats.png")
        
        await interaction.followup.send(embed=embed, file=file)
    else:
        embed.set_footer(text="Graf nelze vygenerovat (žádné aktivní kolonie).")
        await interaction.followup.send(embed=embed)
