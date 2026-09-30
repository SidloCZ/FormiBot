# AGENTS.md – Pravidla projektu a instrukce pro AI asistenta

Tento soubor slouží jako centrální a závazná sada instrukcí pro AI asistenta v prostředí IDE (Antigravity, Cursor, Windsurf, VS Code, Gemini).

---

# ČÁST I: PRAVIDLA TOHOTO PROJEKTU (Project-Specific)

<!-- 
Tuto sekci upravte podle potřeb konkrétního repozitáře/projektu. 
Níže je připravená šablona pro klíčové parametry.
-->

## 1. Specifikace a technologický stack

- **Název projektu / repozitáře:** FormiBotV2
- **Hlavní účel:** Dicord bot pro chovatele mravenců.
- **Tech stack:** Python, discord.py
- **Spouštěcí a testovací příkazy:**
  - Vývojový server: `[např. npm run dev / python main.py]`
  - Kontrola a build: `[např. npm run build / pytest]`
  - Linter / formátování: `[např. npm run lint]`

## 2. Architektura a specifické konvence projektu

- **Klíčové složky a soubory:**
- **Specifická pravidla pro data a stav:**
  - ignorovat soubory ve složce `E:\1Coding\FormiBotV2\1. pokus IDE`
  - průbězně aktualizovat README.md
  - Při změně struktury webu aktualizovat STRUKTURA_PROJEKTU.md
- **Větvení a deployment pravidla:**
  - Větev `dev` slouží pro vývoj, větev `master` je produkční; před začleněním na master vždy ověřit `npm run build`

---

# ČÁST II: UNIVERZÁLNÍ GLOBÁLNÍ STANDARDY (Global Core)

## 1. Komunikace, minimalismus a kontrola nad změnami

- **Méně je někdy více:**
  - Preferuj jednoduchá, čistá, funkční a věcná řešení.
  - Vyvaruj se překombinovaných návrhů a zbytečného kódu navíc.
- **Audit a transparentnost nepožádaných změn kódu:**
  - Pokud v kódu provedeš jakoukoliv změnu, refaktoring nebo optimalizaci, **o kterou uživatel v zadání výslovně nežádal**, VŽDY tuto změnu v odpovědi zřetelně zdůrazni a vysvětli její důvod.
  - Nápady a návrhy nad rámec původního zadání neimplementuj svévolně – popiš je v chatu jako dotaz či doporučení.
- **Striktní zákaz emoji:**
  - V celém projektu (uživatelské rozhraní, dialogy, toast zprávy, kód, komentáře, commit zprávy, texty i odpovědi asistenta) je **přísně zakázáno používat emoji**.
  - Místo emotikonů používej výhradně **pěkné, minimalistické, jednobarevné inline SVG**.
  - Zákaz Unicode vlaječek států (na Windows se vykreslují jako textová písmena) – vždy nahradit inline SVG vlajkou.
- **Faktická přesnost bez domýšlení:**
  - Nikdy si nevymýšlej neověřené parametry, čísla nebo fakta. Pokud chybí přesný zdroj či data, zeptej se uživatele nebo nastav prvek do stavu konceptu.

---

## 2. Nástroje IDE, Git a verzování

- **Nativní IDE nástroje:**
  - K vyhledávání, čtení a inspekci souborů používej nativní workspace nástroje (file search, read_file, grep).
  - Nepoužívej terminálové zkratky typu `node -e` ani ad-hoc bash skripty pro inspekci souborů.
- **Commit message (Conventional Commits):**
  - Na konci každé zprávy v chatu připrav výstižný návrh commit zprávy v angličtině podle konvence (`feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `refactor(...)`, `style(...)`).
  - Vypiš **pouze čistý text zprávy** bez balení do `git commit -m` a bez uvozovek.
  - Asistent **nikdy nespouští commit ani push automaticky**, pouze navrhne zprávu a čeká na potvrzení uživatelem.
- **Sémantické verzování (SemVer):**
  - Při aktualizaci verzí (`manifest.json`, `package.json` apod.) dodržuj:
    - **PATCH (`x.y.Z+1`):** Opravy chyb, drobný refaktoring, styly, textové úpravy.
    - **MINOR (`x.Y+1.0`):** Nové funkce, nové UI komponenty, rozšíření API.
    - **MAJOR (`X+1.0.0`):** Zlomové změny architektury, nekompatibilní přepracování.
- **Udržování dokumentace:**
  - Při zásadní změně struktury kódu nebo novém prvku adekvátně aktualizuj soubory dokumentace (`README.md`, `STRUKTURA_PROJEKTU.md`).

---

## 3. UI, UX a frontendový design

- **Jednoduchost UI prvků:**
  - Tlačítka, položky navigace a nadpisy formuluj stručně a výstižně (ideálně 1–2 slova).
  - Do UI nepřidávej svévolné dekorativní štítky a odznaky (badges jako „Novinka“, „Báze znalostí“), pokud nebyly vyžádány.
- **Parita světlého a tmavého režimu (Dark / Light mode):**
  - Při jakékoliv úpravě barev nebo motivů zajisti adekvátní kontrast a funkčnost v obou režimech současně.
- **Staging a produkční synchronizace:**
  - Pokud projekt využívá trvalé testovací či staging stránky (`temp-*`), udržuj jejich kód v synchronizovaném stavu s odpovídajícími ostrými verzemi.

---

## 4. Jazyková pravidla a česká mikrotypografie

- **Výchozí jazyk:** Řiď se jazykem promptu (typicky čeština; u webových projektů s `/en/` verzí udržuj překladovou paritu).
- **Zásady české mikrotypografie:**
  - **Pevné mezery (`&nbsp;` / `\u00A0`):** Neslabičné a jednopísmenné předložky a spojky (*k, s, v, z, o, u, a, i*) nesmí zůstávat na konci řádku. Vždy je navaž pevnou mezerou k následujícímu slovu.
  - **České uvozovky:** V českých textech používej výhradně uvozovky 99–66: dole `„` (U+201E) a nahoře `“` (U+201C). Zákaz rovných `""` i anglických `“...”`.
  - **Pomlčka vs. spojovník:**
    - Půlčtverčíková pomlčka (`–`, en-dash): Pro číselné rozsahy bez mezer (*10–15 mm*, *20–25 °C*) a jako větná pomlčka oddělená mezerami po obou stranách.
    - Spojovník (`-`, hyphen): Pouze pro těsně vázaná složená slova (*česko-slovenský*) nebo dělení slov.
  - **Jednotky a procenta:** Mezi číslem a jednotkou je vždy pevná mezera (`12&nbsp;mm`, `24&nbsp;°C`). U procent: `10 %` = deset procent (podstatné jméno), `10%` = desetiprocentní (přídavné jméno).
  - **Desetinná čísla a řády:** V českém textu piš desetinnou čárku (*1,5 mm*), v anglickém tečku (*1.5 mm*). Tisíce a vyšší řády odděluj mezerou (*10 000*).
- **Japonský jazyk (pokud je v projektu použit):**
  - Přepis do latinky uváděj vždy **českým přepisem** (vhodně doplněný o Hepburn). U kandži vždy doplň přepis do kany.

---

# ČÁST III: SPECIALIZOVANÝ MODUL – BIOLOGIE A MYRMEKOLOGIE

<!-- Tento modul je aktivní při tvorbě biologického, taxonomického a chovatelského obsahu -->

## 1. Binomická nomenklatura (Vědecké názvosloví)

- **Rod (Genus):** První písmeno velké, formátováno kurzívou (*Camponotus*, *Odontomachus*, *Lasius*, *Formica*).
- **Druhový přívlastek:** Všechna písmena malá, formátováno kurzívou (*ligniperda*, *tyrannicus*, *niger*).
- **Skupina druhů (Species group):** Pouze druhové jméno kurzívou, slovo „group“ nebo „skupina druhů“ normálním písmem bez kurzívy (*tyrannicus* group, skupina druhů *rufa*).
- **Vyšší taxony (Tribus, Podčeleď, Čeleď):** Velké počáteční písmeno, **normální písmo bez kurzívy** (Camponotini, Formicinae, Formicidae).
- **Zákaz CSS capitalize:** Nikdy nepoužívat CSS vlastnost `capitalize` ani automatické kapitálky na druhy (nepřípustné: *Camponotus Ligniperda*).

## 2. Odborná terminologie a překlady

- **Zákaz překládání molekulárních a genetických termínů:** Termíny jako *COI*, *DNA barcoding*, *Barcoding*, *Barcodes*, *PCR*, *mtDNA* apod. se **NIKDY NEPŘEKLÁDAJÍ** do češtiny (např. nepoužívat výrazy „čárové kódy DNA“). Ponechat standardní vědecké označení. Za nimi však může následovat krátké vysvětlení.
- **Přesná myrmekologická morfologie:**
  - Upřednostňuj exaktní terminologii (*gaster/zadeček*, *petiolus*, *trofalaxe*, *nanitik*, *pleometróza*, *gamergát*, *ergatoid*).
  - Nepřidávat české názvy do závorek za odborné termíny, které se běžně nepřekládají.
  - **Diapauza:** Mravenci mají diapauzu; nepoužívat paušálně termíny „hibernace“ či „zimování“, pokud to není přesně fyziologicky podloženo.
  - **Subkasty a kasty:** Major je subkasta dělnice, voják (soldier) je samostatná kasta s unikátními morfologickými znaky (fragmotická hlava, šavlovitá kusadla). Množné číslo: majoři, minoři, medie (nikoliv „majory“, „minora“).
