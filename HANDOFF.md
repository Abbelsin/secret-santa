# Överlämning – att göra (radera den här filen när det är klart)

Allt i den här mappen är färdigbyggt och testat i en tidigare session som inte hade
skrivrättighet till repot. Läs `CLAUDE.md` för kontext.

Testat:
- Python-kryptering ↔ JS-avkryptering (Node 22, WebCrypto) – rätt kod öppnar rätt post, fel kod ger null
- Hela sidflödet i headless Chrome i mobilvy (fel kod → skak, rätt kod → paket → kort)
- `santa.py lotta` / `skicka` / `skicka-igen` med fejkad CSV och mockad SMTP

Ej testat: riktig Gmail-inloggning och IMAP-rensningen av Skickat (Gmail-specifika X-GM-kommandon).

## Uppgifter
1. Kopiera in filerna i repo-roten för `Abbelsin/secret-santa` (repot är tomt, branch `main`).
   Ta inte med någon `config.toml`, `*.csv` eller `lottning.dat` om sådana dyker upp.
2. Committa och pusha till `main`.
3. Slå på GitHub Pages från `main` / root:
   ```
   gh api -X POST repos/Abbelsin/secret-santa/pages -f "source[branch]=main" -f "source[path]=/"
   ```
   (Om den redan finns: `-X PUT` med samma fält.)
4. Vänta tills bygget är klart (`gh api repos/Abbelsin/secret-santa/pages/builds/latest`) och kolla att
   `https://abbelsin.github.io/secret-santa/` och `.../data.json` svarar 200.
5. Prova gärna sidan med demokoden ⛄🎅🎄 – ska visa "Hej Tomtenisse! … Rudolf".
6. Radera `HANDOFF.md`, committa, pusha. Berätta för Albin att sidan är uppe.

## Albins nästa steg (inte din uppgift om han inte ber om det)
Formulär via `skapa_formular.gs` → CSV → `config.toml` → `santa.py kolla` → `lotta` → push → `skicka`.
Se `README.md`.
