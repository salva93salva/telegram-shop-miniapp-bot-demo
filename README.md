# Telegram Shop Mini App Bot

Bot Telegram modulare per vendere prodotti digitali e fisici, collegato a
una Mini App e-commerce HTTPS. Questa variante rimane separata dal bot classico
e usa token, database e distribuzione propri.

## Funzioni incluse

- catalogo diviso per categorie;
- prodotti digitali in Telegram Stars;
- prodotti fisici in euro;
- carrello persistente separato per ogni utente;
- checkout digitale demo o pagamento reale con Telegram Stars;
- verifica sicura di ordine, utente, valuta e importo;
- consegna automatica dei prodotti digitali;
- checkout guidato dei prodotti fisici con dati di spedizione;
- scorte aggiornate in modo atomico;
- cronologia ordini del cliente;
- pannello amministratore privato;
- statistiche di prodotti, ordini e vendite;
- gestione dello stato delle spedizioni;
- vista predefinita dei soli ordini ancora da gestire;
- filtri per stato e tipo, ricerca e paginazione degli ordini;
- attivazione e disattivazione dei prodotti;
- aumento e diminuzione delle scorte;
- creazione guidata di prodotti dal pannello amministratore;
- modifica di nomi, descrizioni, prezzi, scorte e foto;
- eliminazione confermata dei prodotti con conservazione degli ordini storici;
- caricamento del file digitale da consegnare dopo l'acquisto;
- foto del prodotto mostrate direttamente nel catalogo;
- Mini App e-commerce responsive inclusa nella cartella `webapp`;
- foto intere e proporzionate nella vetrina, senza ritagli;
- trasferimento sicuro del carrello dalla Mini App al bot;
- notifica privata agli amministratori per ogni nuovo ordine;
- controllo dello stato del servizio;
- download privato di un backup SQLite coerente;
- database SQLite con migrazioni automatiche;
- 40 test automatici.

## Avvio su Windows

```powershell
cd $HOME\Documents\telegram-shop-miniapp-bot
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m app.main
```

Non copiare di nuovo `.env.example` sopra `.env` dopo la configurazione: il
token reale verrebbe sostituito.

## Configurazione

Il file `.env` resta soltanto sul computer o nelle variabili private del
servizio di hosting.

```ini
BOT_TOKEN=TOKEN_CREATO_CON_BOTFATHER
ADMIN_IDS=ID_TELEGRAM_NUMERICO
SHOP_NAME="Nome del negozio"
DATABASE_PATH=data/shop.db
PAYMENT_MODE=demo
SUPPORT_CONTACT="@username_assistenza"
MINI_APP_URL=https://indirizzo-pubblico-della-mini-app.example.com
API_HOST=0.0.0.0
```

Valori di `PAYMENT_MODE`:

- `demo`: simula il pagamento e non addebita denaro;
- `stars`: usa realmente Telegram Stars per i prodotti digitali.

Il comando `/admin` è disponibile soltanto in chat privata agli ID elencati
in `ADMIN_IDS`. Più amministratori possono essere separati da virgole.

## Mini App grafica

Il codice completo della vetrina è nella cartella `webapp`. L'indirizzo del
backend non è fisso: ogni cliente può configurare il proprio servizio.

```powershell
cd webapp
Copy-Item .env.example .env.local
notepad .env.local
npm install
npm run dev
```

Nel file `.env.local` inserire l'indirizzo HTTPS pubblico del backend:

```ini
NEXT_PUBLIC_API_BASE_URL=https://backend-del-cliente.example.com
```

Per creare la versione pronta alla pubblicazione usare `npm run build`.

## Test

Con l'ambiente virtuale attivo:

```powershell
python -m unittest discover -v
```

## Pubblicazione su Railway

Il file `railway.json` imposta il comando di avvio `python -m app.main`.

Nelle variabili private del servizio Railway inserire:

- `BOT_TOKEN`;
- `ADMIN_IDS`;
- `SHOP_NAME`;
- `DATABASE_PATH=/data/shop.db`;
- `PAYMENT_MODE=demo` durante il collaudo;
- `SUPPORT_CONTACT`;
- `MINI_APP_URL`, con l'indirizzo HTTPS pubblico della vetrina;
- `RAILPACK_PYTHON_VERSION=3.13`.

Per non perdere ordini, scorte e prodotti dopo un nuovo deploy, collegare un
volume persistente al percorso `/data`. Il file locale `.env` e il database
locale non devono essere caricati su GitHub.

## Pagamenti e costi esterni

- I pagamenti digitali dentro Telegram devono usare Telegram Stars secondo le
  regole della piattaforma.
- Il bot non conserva numeri di carta.
- Hosting, commissioni, rimborsi e conversione delle Stars dipendono dai
  servizi scelti e non sono inclusi nel codice.
- In produzione token, account Telegram, hosting e strumenti di pagamento
  devono appartenere al cliente.
- La spedizione dei prodotti fisici e gli eventuali pagamenti esterni vanno
  configurati in base al paese e all'attività del cliente.

## Sicurezza

Non pubblicare mai `.env`, token, credenziali, database reali o dati di
spedizione dei clienti. Il file `.gitignore` esclude già questi elementi.
