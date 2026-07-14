# B-CAN ID Map (can1, 50 kbps)

Mappa dei messaggi identificati sul B-CAN della Fiat Panda 169 (2010).
Metodo: `candump`/diff con azioni note, veicolo fermo e motore spento.

Sorgente macchina-leggibile: [`dbc/bcan.dbc`](../dbc/bcan.dbc) (caricabile con `cantools`).
Verifica live: `python3 tools/live_decode.py` sul Raspberry Pi.
Scoperta nuovi ID: `python3 tools/sniff_events.py` (vede anche ID estesi 29-bit).

> ⚠️ **Limite cansniffer:** mostra solo ID standard 11-bit. Eventi come
> chiusura/apertura porte su B-CAN Fiat possono usare ID estesi 29-bit e
> risultano **invisibili** in cansniffer. Usare `candump` o `sniff_events.py`.

## 0x180 — STATO_LUCI (Body Computer, DLC 6)

Un solo ID per tutte le luci esterne: il payload è una **bitmask**.

### Byte 1 — luci

| Bit (mask) | Segnale        | Osservazione |
| :--------- | :------------- | :----------- |
| `0x60`     | Posizione      | Entrambi i bit si alzano insieme (`byte1 = 0x60`) |
| `0x08`     | Anabbaglianti  | `0x68` = posizione + anabbaglianti |
| `0x10`     | Abbaglianti    | ⚠️ Osservato `0x10` da solo — probabile lampeggio a luci spente. **Da riverificare** con anabbaglianti accesi (atteso `0x78`) |
| `0x04`     | Fendinebbia    | `0x6C` = `0x68` + fendinebbia |
| `0x02`     | Retronebbia    | `0x6A` = `0x68` + retronebbia |

### Byte 2 — frecce

| Bit (mask) | Segnale    | Osservazione |
| :--------- | :--------- | :----------- |
| `0x20`     | Freccia DX | |
| `0x40`     | Freccia SX | |
| `0x60`     | 4 frecce   | = DX + SX, conferma bitmask |

### Da verificare

- [ ] Abbaglianti con anabbaglianti già accesi → atteso `byte1 = 0x78`
- [ ] Bit freccia: toggla col lampeggio (~500 ms) o resta fisso finché leva attiva?
- [ ] Periodicità del messaggio (ciclico o event-driven?) → `candump -td can1,180:7FF`
- [ ] Byte 0, 3, 4, 5: sempre `0x00`? Provare con quadro acceso / retromarcia

## Prossimi target (stesso metodo diff)

- [ ] Porte (apertura/chiusura — porta singola distinguibile?)
- [ ] Chiusura centralizzata (telecomando vs chiave)
- [ ] Finestrini
- [ ] Quadro / chiave inserita
- [ ] Retromarcia
