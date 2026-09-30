# Struktura projektu FormiBotV2

Tento dokument detailně popisuje architekturu, adresářové rozložení, konfiguraci a&nbsp;datové toky projektu.

---

## 1. Adresářový strom

```text
FormiBotV2/
├── .env                          # Lokální proměnné prostředí (DISCORD_TOKEN) – ignorováno gitem
├── .gitignore                    # Pravidla pro vyloučení dočasných a tajných souborů
├── AGENTS.md                     # Projektová a globální pravidla pro AI asistenty
├── README.md                     # Hlavní přehled projektu, instalace a seznam příkazů
├── STRUKTURA_PROJEKTU.md         # Tento architektonický přehled
├── config.py                     # Centrální konfigurace, ID rolí, kanálů a cesty k datům
├── main.py                       # Hlavní spouštěcí bod bota, registrace událostí a slash stromu
├── requirements.txt              # Seznam závislostí pro Python
├── utils.py                      # Sdílené komponenty (PaginatorView pro stránkování embedů)
├── commands/                     # Moduly s příkazy (Command Groups a samostatné příkazy)
│   ├── __init__.py               # Inicializace balíčku commands
│   ├── brainrot_startup.py       # Denní ranní souhrn (slova dne, články, fakta)
│   ├── checklist_commands.py     # Příkazy /checklist pro nálezy v terénu
│   ├── chov_commands.py          # Příkaz /chov pro informace o druzích mravenců
│   ├── fauna_commands.py         # Příkaz /fauna pro faunistické čtverce ČR
│   ├── formikaristika_commands.py# Skupina /formikaristika pro články a atlas z webu
│   ├── inzerce_commands.py       # Skupina /inzerce a trvalá tlačítka inzerátů
│   ├── isop_commands.py          # Příkaz /isop pro karty druhů AOPK ČR
│   ├── map_commands.py           # Příkaz /mapa pro zobrazení nálezů
│   ├── patch_notes_commands.py   # Příkazy /patchnotes
│   ├── quiz_commands.py          # Příkazy /kviz, /napoveda, /skore a správa návrhů
│   ├── seznam_commands.py        # Příkazy /seznam pro chované kolonie uživatelů
│   ├── slovnik_commands.py       # Příkazy /slovnik pro výklad myrmekologických pojmů
│   ├── statistiky_commands.py    # Příkazy /statistiky pro grafy a žebříčky chovů
│   ├── udalosti_commands.py      # Příkazy /udalosti pro burzy a výstavy
│   └── wishlist_commands.py      # Příkazy /wishlist pro vysněné druhy chovatelů
├── data/                         # Databáze a perzistentní JSON soubory
│   ├── checklist_species_czsk.json # Master seznam druhů mravenců ČR a SR
│   ├── czech_checklist.json      # Doplňkový taxonomický kontrolní seznam
│   ├── events.json               # Uložené entomologické akce a burzy
│   ├── historical_ants_data.json # Historické snímky počtu kolonií pro časové grafy
│   ├── inzerce.json              # Aktivní a archivované inzeráty
│   ├── patch_notes.json          # Historie verzí bota
│   ├── quiz_questions.json       # Databáze kvízových otázek rozdělená podle kategorií
│   ├── quiz_suggestions.json     # Čekající a schvalované návrhy otázek
│   ├── scores.json               # Celkové a týdenní skóre kvízu
│   ├── user_ants.json            # Chované kolonie jednotlivých uživatelů
│   ├── user_checklist_data.json  # Nálezy uživatelů v checklistu fauny
│   └── wishlists.json            # Uživatelské wishlisty
├── assets/                       # Statická grafika (např. mapa kvadrátů fauna.png)
└── Work/                         # Původní referenční skripty a zdrojové soubory
```

---

## 2. Klíčové role a&nbsp;kanály (Discord ID)

Konfigurace je centralizována v&nbsp;souboru `config.py`:

| Název parametru | ID | Význam |
| :--- | :--- | :--- |
| `RESTART_ROLE_ID` | `661971700556234753` | Oprávnění pro příkaz `/restart` |
| `STARTUP_CHANNEL_ID` | `662424508266840080` | Kanál pro uvítací hlášení po startu |
| `BRAINROT_CHANNEL_ID` | `662424508266840080` | Kanál pro ranní vzdělávací příspěvky |
| `AD_CHANNEL_ID` | `721732364664963103` | Hlavní inzertní kanál pro nabídky a&nbsp;poptávky |
| `AD_NOTIFICATION_CHANNEL_ID` | `662424508266840080` | Kanál pro oznámení nových inzerátů |
| `EVENTS_NOTIFICATION_CHANNEL_ID` | `661958543548612660` | Kanál pro upozornění na blížící se akce |
| `QUIZ_SUGGESTION_CHANNEL_ID` | `1402286144519143554` | Schvalovací kanál pro návrhy nových otázek |

---

## 3. Zásady správy dat

- Veškeré perzistentní soubory jsou ukládány v&nbsp;adresáři `data/` s&nbsp;kódováním `utf-8`.
- Dočasné a&nbsp;citlivé soubory (jako `.env`, `token.txt`, systémové mezipaměti `__pycache__` a&nbsp;složka `1. pokus IDE/`) jsou vyloučeny ze sledování verzí gitem.
- Při volání příkazu `/restart` bot provede bezpečné uložení všech databází před ukončením procesu.
