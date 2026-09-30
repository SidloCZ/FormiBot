# FormiBotV2

Discord bot pro komunitu chovatelů mravenců (**AntsCzech**).

---

## 1. Popis projektu

FormiBotV2 je modulární Discord bot postavený na knihovně `discord.py`. Poskytuje komunitě nástroje pro správu chovaných kolonií, checklisty fauny mravenců ČR a&nbsp;SR, entomologické události a&nbsp;burzy, inzerci chovatelských přebytků, vědomostní kvízy, slovník pojmů a&nbsp;propojení s&nbsp;webem Formikaristika.cz.

---

## 2. Technologický stack

- **Jazyk:** Python 3.10+ (testováno na Python 3.14)
- **Klíčové knihovny:** `discord.py`, `requests`, `beautifulsoup4`, `matplotlib`, `tabulate`, `python-dotenv`, `tzdata`
- **Ukládání dat:** JSON databáze v&nbsp;adresáři `data/`
- **Konfigurace:** `.env` soubor a&nbsp;modul `config.py`

---

## 3. Instalace a&nbsp;spuštění

### Požadavky
Nainstalovaný Python a&nbsp;správce balíčků `pip`.

### Instalace závislostí
```bash
python -m pip install -r requirements.txt
```

### Konfigurace prostředí
Vytvořte soubor `.env` v&nbsp;kořenovém adresáři s&nbsp;následujícím obsahem:
```env
DISCORD_TOKEN=vas_tajny_token_bota
BOT_PREFIX=!
```

### Spuštění bota
```bash
python main.py
```

---

## 4. Přehled modulů a&nbsp;příkazů

- **`/seznam`** – Správa vlastních chovaných kolonií (přidat, odebrat, nastavit počet, zobrazit seznam).
- **`/statistiky`** – Přehled aktivních i&nbsp;historických statistik serveru, grafy a&nbsp;osobní profily chovatelů.
- **`/checklist`** – Sledování druhů fauny ČR a&nbsp;SR nalezených v&nbsp;přírodě.
- **`/chov`** – Vyhledávání profilů a&nbsp;chovatelských parametrů jednotlivých druhů mravenců.
- **`/inzerce`** – Podávání a&nbsp;procházení nabídek a&nbsp;poptávek mravenců i&nbsp;vybavení.
- **`/udalosti`** – Přehled a&nbsp;notifikace entomologických burz a&nbsp;výstav.
- **`/formikaristika`** – Procházení článků a&nbsp;atlasu z&nbsp;webu Formikaristika.cz.
- **`/isop`** – Generování odkazů na karty druhů v&nbsp;systému ISOP AOPK ČR.
- **`/fauna`** – Zobrazení mapy kvadrátů faunistického čtvercování ČR.
- **`/mapa`** – Interaktivní přehled nálezů mravenců na mapě.
- **`/slovnik`** – Myrmekologický terminologický výkladový slovník.
- **`/kviz`** – Vědomostní soutěž s&nbsp;bodováním, nápovědami a&nbsp;týdenním žebříčkem.
- **`/wishlist`** – Seznamy vysněných druhů uživatelů.
- **`/patchnotes`** – Historie verzí a&nbsp;změn v&nbsp;botovi.
- **`/ping`** – Měření aktuální odezvy bota.
- **`/help`** – Stránkovaný katalog všech registrovaných příkazů.
- **`/restart`** – Bezpečné uložení všech dat a&nbsp;restart bota (vyhrazeno moderátorům).
