# Secret Santa – projektkontext

Familjens Secret Santa 2026. Albin organiserar. Klapparna delas ut på julafton (ingen postning).

## Delar
- `index.html` – statisk sida på GitHub Pages (`https://abbelsin.github.io/secret-santa/`).
  Emoji-knappsats (15 julemojis), 3-teckens kod, snöanimation, paket som öppnas, kort med
  namn/budget/önskemål. All logik inline, inga beroenden.
- `data.json` – krypterade poster, en per deltagare. Innehåller just nu **demodata**
  (koder ⛄🎅🎄 / 🎁⭐🦌 / 🍪🔔🧦). Ersätts av `santa.py lotta`.
- `santa.py` – Python 3.11+, endast stdlib. Läser Google Forms-CSV, lottar, skriver `data.json`,
  mejlar ut koder via Gmail SMTP (app-lösenord) och rensar Skickat via IMAP.
  Kommandon: `kolla`, `testmejl`, `lotta`, `skicka`, `skicka-igen NAMN`.
- `skapa_formular.gs` – Google Apps Script som skapar anmälningsformuläret (namn, e-post,
  budget-flerval 200/300/500/750/annat, önskemål, "vill inte ha").

## Viktiga regler
- **Kryptot i `santa.py` och `index.html` måste matcha exakt.** PBKDF2-SHA256(kodindex joinade
  med ",", salt, iter) → 64 B; första 32 = krypteringsnyckel, sista 32 = MAC-nyckel.
  Keystream = HMAC-SHA256(ek, nonce || uint32be(räknare)), XOR. Tagg = HMAC(mk, nonce||ct)[:16].
  Paletten skickas med i `data.json` så sidan och skriptet alltid är överens.
  Ändrar du något – testa att Python-krypterad data avkrypteras av sidans JS (t.ex. med Node 18+,
  `globalThis.crypto.subtle`).
- **Organisatören får aldrig se vem som har vem.** Skriv aldrig ut par, logga dem inte, och visa
  inte innehållet i `lottning.dat` eller avkrypterad `data.json` för riktiga data.
- **Personuppgifter committas aldrig:** `config.toml`, `*.csv`, `lottning.dat` är gitignorerade.
- Organisatörens mamma ska klara sidan – håll den enkel och mobilvänlig.
