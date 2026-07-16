# Mappa modello 3D ↔ eventi CAN

Il modello usato dall'app Android è [`assets/model/panda_rigged.glb`](../assets/model/panda_rigged.glb),
generato da `assets/model/panda.glb` (export Sketchfab, non modificare) con:

```bash
python scripts/rig_panda_glb.py
```

Anteprima senza Blender: `python -m http.server 8000` dalla radice della repo,
poi apri <http://localhost:8000/scripts/view_rigged.html> (bottoni per clip e luci).

## Convenzioni

- Assi modello: X laterale, Y su, Z avanti (scala: 1 unità glTF = 1 m nel file rigged).
- `FL` = anteriore sinistra (lato guida, auto italiana), `FR` = anteriore destra.
- Le porte **posteriori** e le parti L/R delle luci sono ancora fuse nel modello
  sorgente: non animabili/pilotabili singolarmente (v. Limiti).

## Animation clip (porte)

| Clip glTF | Nodo pivot | Evento CAN | Stato mappatura |
| :--- | :--- | :--- | :--- |
| `door_FL_open` (1 s) | `door_FL` | Apertura porta anteriore SX | **Da mappare** su B-CAN (target in [`bcan_map.md`](bcan_map.md), "Porte") |
| `door_FR_open` (1 s) | `door_FR` | Apertura porta anteriore DX | **Da mappare** |
| `tailgate_open` (1 s) | `tailgate` | Apertura portellone | **Da mappare** |

Uso: play in avanti = apertura; riproduzione inversa (o progress 1→0) = chiusura.
Stato porta = booleano da CAN → progress target 0/1.

## Materiali luce (emissive)

Riferimento CAN: messaggio **`0x180 STATO_LUCI`** (Body Computer, DLC 6) — v. [`bcan_map.md`](bcan_map.md).

| Materiale glTF | Mesh | Evento CAN | Bit |
| :--- | :--- | :--- | :--- |
| `mat_headlights` | lampade fari anteriori | Anabbaglianti / Abbaglianti | byte1 `0x08` / `0x10` |
| `mat_taillights` | vetri rossi fanali posteriori | Luci di posizione | byte1 `0x60` |
| `mat_foglights` | lampade fendinebbia | Fendinebbia | byte1 `0x04` |
| `mat_indicators` | lampade frecce laterali | Frecce (v. Limiti) | byte2 `0x20` DX / `0x40` SX |
| `mat_stoplight` | lampada terzo stop | Pedale freno | **Da mappare** |

Accensione: `emissiveFactor` da `[0,0,0]` al colore pieno (fari bianco caldo,
posteriori rosso, frecce ambra). Spegnimento: di nuovo `[0,0,0]`.

## Limiti noti (richiedono split aggiuntivo del modello)

- **Frecce**: le lampade L+R sono un'unica mesh → si accendono solo insieme.
  OK per 4 frecce, non per indicatore singolo. Fix: split `Wing_Light_Lamp` in
  `scripts/rig_panda_glb.py` (stessa tecnica delle porte).
- **Porte posteriori** (`Door1`, `Door_S1`, `DoorHandle1`, `Window1`): fuse L+R, non animate.
- **Retronebbia** (byte1 `0x02`): nessuna mesh dedicata individuata.
- **Modanatura porte** (`Door_Plst`): copre le 4 porte in un'unica mesh; resta
  solidale alla carrozzeria quando una porta si apre (artefatto visivo minore).
- **Cofano** (`Hood`): mesh singola separata, animabile in futuro (nessun pivot creato).
