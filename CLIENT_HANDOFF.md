# Checklist di consegna al cliente

## Dati che deve fornire il cliente

- token del bot creato dal proprio account BotFather;
- ID Telegram degli amministratori;
- nome e testi del negozio;
- catalogo, prezzi, immagini, scorte e file digitali;
- username o contatto di assistenza;
- account Railway o altro hosting intestato al cliente;
- account o servizio di hosting per la Mini App grafica;
- condizioni di vendita, privacy, rimborsi e spedizioni applicabili.

Non chiedere mai al cliente password personali. Il token può essere inserito
dal cliente direttamente nelle variabili private dell'hosting.

## Collaudo prima della consegna

1. Lasciare `PAYMENT_MODE=demo`.
2. Verificare catalogo, carrello e cronologia ordini.
3. Provare un ordine digitale e la consegna del file.
4. Provare un ordine fisico e i dati di spedizione.
5. Provare `/admin`, statistiche, scorte e stati della spedizione.
6. Provare filtri, paginazione e ricerca degli ordini.
7. Creare un prodotto fisico con foto dal pannello amministratore.
8. Creare un prodotto digitale e provarne la consegna del file.
9. Controllare le notifiche private agli amministratori.
10. Eseguire `python -m unittest discover -v`.
11. Verificare il volume persistente `/data` sull'hosting.
12. Fare un backup del database prima della messa online.
13. Verificare che la Mini App usi l'indirizzo del backend del cliente.

## Attivazione dei pagamenti reali

Attivare `PAYMENT_MODE=stars` soltanto dopo l'approvazione del cliente e un
collaudo completo. Eseguire una transazione di importo minimo e verificare
anche il flusso di assistenza e rimborso previsto da Telegram.

## Materiale da consegnare

- codice sorgente senza `.env` e senza database contenente dati reali;
- codice della vetrina grafica nella cartella `webapp`;
- file `.env.example` privo di segreti;
- istruzioni di avvio e distribuzione;
- credenziali e proprietà degli account lasciate al cliente;
- breve video dimostrativo;
- periodo di assistenza e numero di revisioni concordati nell'ordine Fiverr.
