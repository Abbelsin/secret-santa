# 🎅 Secret Santa

Familjens Secret Santa. Alla får en emoji-kod (t.ex. ⛄🎅🎄) på mejl, knappar in den på
sidan och får se vem de ska ge en klapp till.

Namnen ligger krypterade i `data.json`. Varje post kan bara öppnas med rätt kod
(PBKDF2-SHA256 + HMAC), så ingen kan läsa dem i källkoden. Med tre emojis ur femton
finns 3 375 koder, så det håller mot tjuvkikande familjemedlemmar men inte mot någon
som är beslutsam. Därför publiceras bara förnamn – heter två likadant läggs så
mycket av efternamnet till som behövs ("Anna S." och "Anna L."). Mejladresser och
budgetröster publiceras aldrig.

**Demo:** sidan har testdata nu. Prova ⛄🎅🎄, 🎁⭐🦌 eller 🍪🔔🧦.

## Gör så här

1. **Formulär:** klistra in `skapa_formular.gs` på <https://script.google.com>, kör, dela länken.
2. **Svar:** ladda ner svaren som CSV, spara som `svar.csv` här.
3. **Config:** `cp config.example.toml config.toml` och fyll i Gmail och vilka som inte får dra varandra.
4. **Kolla:** `python3 santa.py kolla`
5. **Testa mejl:** `python3 santa.py testmejl din@adress.se`
6. **Lotta:** `python3 santa.py lotta` skriver nya `data.json` (visar inget).
7. **Publicera:** `git add data.json && git commit -m "Lottning" && git push`
8. **Skicka koder:** `python3 santa.py skicka` kollar först att sidan har nya datan.
9. **Tappat koden?** `python3 santa.py skicka-igen Mamma`

`config.toml`, `svar.csv` och `lottning.dat` committas aldrig (se `.gitignore`).
Kräver Python 3.11+, inga beroenden. Gmail-kontot behöver ett app-lösenord
(sätt `SANTA_APP_PASSWORD` eller skriv in det när du blir tillfrågad).
