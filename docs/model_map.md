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
- `FL` = anteriore sinistra (lato guida, auto italiana), `FR` = anteriore destra,
  `RL`/`RR` le posteriori.
- Le parti L/R delle luci sono ancora fuse nel modello sorgente: non pilotabili
  singolarmente (v. Limiti).

## Peso dell'asset e costo a runtime

Il GLB finisce negli asset dell'APK ed è renderizzato da Filament su GPU
mobile, quindi contano due grandezze diverse: i **byte** (download, RAM) e i
**triangoli** (frame time, batteria). Lo script chiude con `compact_scene()`,
che agisce su entrambe: **51,9 → 26,7 MB** e **1,30 M → 1,09 M triangoli**.

| Intervento | Recupero |
| :--- | :--- |
| Scarto di nodi, mesh e accessor irraggiungibili dalla scena | 6,2 MB |
| Rimozione di `TEXCOORD_0` dalle mesh con materiale senza texture | ~7,5 MB |
| Indici da `uint32` a `uint16` | ~7,8 MB |
| Decimazione quadric delle mesh in `DECIMATE` | −213 k triangoli |

Il grosso del risparmio è sui byte. Sui triangoli la decimazione ha reso poco,
perché i due candidati più grassi si rovinano entrambi (v. sotto).

Il rigging lascia dietro gli holder fusi originali e le loro mesh come nodi
orfani. Nessun materiale del modello sorgente campiona una texture, quindi le
UV erano dato morto ovunque tranne sui due quad targa generati dallo script
(gli unici con `baseColorTexture`). Nessuna mesh raggiunge i 65.536 vertici (la
più grande, lo pneumatico, ne ha 65.191), quindi gli indici a 32 bit erano il
doppio del necessario.

### Decimazione: cosa e perché

`DECIMATE` elenca solo **oggetti autonomi** — ruote, interni, corpi lampada,
barre tetto — che non condividono bordi con pannelli vicini: semplificarli non
può aprire una cucitura. I pannelli di carrozzeria sono esclusi di proposito,
sono la superficie che si guarda davvero.

Ogni voce porta anche un'**aggressività**: con quella bassa il decimatore si
ferma prima di rovinare la forma.

Tre trappole trovate per via sperimentale, che vale la pena non ripetere:

- **Normali.** Le mesh sorgente sdoppiano i vertici sugli spigoli (lo
  pneumatico ha 65.155 vertici per 17.520 posizioni distinte). Ricalcolare
  normali semplicemente mediate salda quegli spigoli e la superficie si legge a
  macchie, come se avesse perso una texture. `crease_normals()` dà una copia del
  vertice alle facce che divergono oltre 40° dalla media, e lo spigolo resta
  vivo. Necessario, ma da solo non basta sui pneumatici.
- **Sedili esclusi.** `Chair2`/`Chair3` hanno gusci sottili sovrapposti che
  sotto decimazione si auto-intersecano e macchiano, anche a `0.50`. Verificato
  generando una build senza: le macchie spariscono. 211 k triangoli.
- **Pneumatici esclusi.** Il battistrada è un anello di piccoli tasselli che il
  decimatore fonde in una fascia irregolare e frastagliata, a qualunque rapporto
  utile. Sono in primo piano e ruotano, quindi si nota. 138 k triangoli.

Il metodo che ha risolto entrambi i casi: generare una build **senza** la parte
sospetta e confrontare la stessa inquadratura. Le metriche di deviazione
geometrica non bastano — misurano la distanza dei vertici, non se la topologia
di un pattern ripetuto è sopravvissuta.

### Budget e margini residui

1,09 M triangoli su 142 draw call restano **sopra** il budget comodo per mobile
(100–300 k per un oggetto singolo a 60 fps). Su un telefono recente gira, su
fascia bassa può calare sotto i 60 fps. Ciò che resta è carrozzeria (493 k),
sedili (211 k), vetri (174 k) e pneumatici (138 k): carrozzeria e vetri
intatti perché sono le superfici visibili e condividono bordi tra loro, sedili
e pneumatici perché si rovinano (v. sopra).

Leve non applicate, in ordine di resa:

- **Un decimatore migliore.** `fast-simplification` non espone né la
  preservazione dei bordi aperti (serve ai pannelli di carrozzeria) né il
  controllo della topologia (servirebbe a sedili e battistrada). `pymeshlab` sì:
  è la strada per scendere sotto i 400 k senza difetti visibili.
- **Un modello sorgente più leggero.** Il vero problema è a monte: `panda.glb`
  è un modello da render offline, con dettagli (battistrada, imbottiture
  sedili) che a schermo su un telefono non si distinguono comunque.
- **Draco o meshopt**: forte sui byte (non sui triangoli), richiede tooling
  esterno (Node/gltfpack) non disponibile in questo ambiente.
- **`KHR_mesh_quantization`** (`POSITION` int16, `NORMAL` int8): ~40% di byte
  in meno e meno banda di vertex fetch, ma non tocca il conteggio triangoli.
  Aggiunge un'estensione al file: supportata da Filament e three.js, resta una
  scelta di compatibilità.

## Animation clip

| Clip glTF | Nodo pivot | Evento CAN | Stato mappatura |
| :--- | :--- | :--- | :--- |
| `running` (1 s, loop) | `axle_front`, `axle_rear`, `body_shake`, holder `Tube` | Veicolo in marcia | **Da mappare** |
| `door_FL_open` (1 s) | `door_FL` | Apertura porta anteriore SX | **Da mappare** su B-CAN (target in [`bcan_map.md`](bcan_map.md), "Porte") |
| `door_FR_open` (1 s) | `door_FR` | Apertura porta anteriore DX | **Da mappare** |
| `door_RL_open` (1 s) | `door_RL` | Apertura porta posteriore SX | **Da mappare** |
| `door_RR_open` (1 s) | `door_RR` | Apertura porta posteriore DX | **Da mappare** |
| `tailgate_open` (1 s) | `tailgate` | Apertura portellone | **Da mappare** |
| `window_FL_down` (1 s) | `door_FL_window_neg` | Discesa finestrino ant. SX | **Da mappare** |
| `window_FR_down` (1 s) | `door_FR_window_pos` | Discesa finestrino ant. DX | **Da mappare** |
| `window_RL_down` (1 s) | `door_RL_window_neg` | Discesa finestrino post. SX | **Da mappare** |
| `window_RR_down` (1 s) | `door_RR_window_pos` | Discesa finestrino post. DX | **Da mappare** |

Il pivot `tailgate` è la cerniera alta, sul bordo del tetto (y ≈ 142), calcolata
sul bordo superiore di **tutto** il gruppo: usando solo il pannello inferiore
(`Trunk`, top y ≈ 97) la cerniera finiva a metà altezza e il portellone ruotava
di lato invece che verso l'alto. Il gruppo comprende pannello, lunotto e
cornice, targa, terzo stop (`Stop_Light_*`), stemma FIAT (`Logo_*_B`,
`Logo_Text1`), scritta `Text_Panda` e tergilunotto (`Junitors_Back`). I fanali
posteriori restano sulla scocca (è corretto).

Uso (porte, portellone e finestrini): play in avanti = apertura/discesa;
riproduzione inversa (o progress 1→0) = chiusura/risalita. Stato = booleano da
CAN → progress target 0/1.

Le due file di porte sono rigate dalla stessa funzione (`DOOR_ROWS` +
`rig_door_row`): split L/R per segno di X, pivot cerniera sul bordo anteriore
(max Z locale) del guscio porta. Le posteriori sono solo il pannello fino alla
cintura, la loro cornice finestrino arriva dalle plastiche condivise.

I finestrini traslano verso il basso della propria altezza — 50,8 unità davanti,
45,1 dietro — così il bordo superiore finisce sotto la linea di cintura e il
vetro resta dentro il guscio della porta (davanti vetro y 38…89 in porta y
31…144; dietro vetro y 50…95 in porta y 32…97), quindi sparisce alla vista
senza dover essere reso invisibile. L'holder del vetro è figlio del pivot porta,
perciò un finestrino abbassato ruota comunque con la porta che si apre invece di
restare sospeso a mezz'aria.

### Clip `running`

Ruote, scuotimento carrozzeria e vibrazione marmitta in un'unica clip da 1 s
pensata per il loop. Tutte le oscillazioni usano frequenze multiple intere di
1/durata, così primo e ultimo keyframe coincidono e il loop non ha scatti;
`scripts/check_running_clip.py` lo verifica canale per canale.

Le ruote fanno 4 giri per loop: con una circonferenza di 1,852 m sono ≈26,7
km/h apparenti. Per una velocità diversa si scala il tempo di riproduzione:
`timeScale = v_kmh / 26.7`.

Un pivot per asse, non per ruota: le ruote dello stesso asse condividono y e z
e girano nello stesso verso, e la posizione del pivot lungo X non influenza una
rotazione attorno a X. `Support`/`Support1` (pinze freno) non stanno sotto i
pivot: sul veicolo reale non girano. `body_shake` è un nodo inserito sopra
`RootNode`, perché il nodo che porta la scala cm→m usa una `matrix` e glTF non
consente di animare nodi con matrice.

Ampiezze effettive: carrozzeria 0,14° e ±1,8 mm verticali, marmitta ±1,5 mm.
Regolabili con `SHAKE_ROT_DEG`, `SHAKE_TRANS_MM`, `EXHAUST_TRANS_MM` in
`scripts/rig_panda_glb.py`.

## Materiali luce (emissive)

Riferimento CAN: messaggio **`0x180 STATO_LUCI`** (Body Computer, DLC 6) — v. [`bcan_map.md`](bcan_map.md).

| Materiale glTF | Mesh | Evento CAN | Bit |
| :--- | :--- | :--- | :--- |
| `mat_headlights` | lenti fari anteriori (`HeadLamp_Glas`) | Anabbaglianti / Abbaglianti | byte1 `0x08` / `0x10` |
| `mat_foglights` | lenti fendinebbia nel paraurti (`Anti_Fog_Glas`) | Fendinebbia | byte1 `0x04` |
| `mat_indicators` | lenti frecce laterali (`Wing_LightGlas`) + banda chiara superiore dei fanali posteriori (`HeadLamp_Glass_White_indicator`) | Frecce (v. Limiti) | byte2 `0x20` DX / `0x40` SX |
| `mat_indicator_front` | angolo alto-esterno dei fari (`HeadLamp_Glas_indicator`) | Frecce, **oppure** fari (v. sotto) | byte2 `0x20` / `0x40` |
| `mat_stoplight` | vetri rossi fanali posteriori (`HeadLamp_Glass_Red`) + lampada terzo stop | Pedale freno | **Da mappare** |

Accensione: `emissiveFactor` da `[0,0,0]` al colore pieno (fari bianco caldo,
posteriori rosso, frecce ambra). Spegnimento: di nuovo `[0,0,0]`.

L'emissive va sulla **lente esterna**, non sulla mesh della lampadina: le mesh
`*_Lamp` sono racchiuse dentro il vetro (`clearglass`, `alphaMode` OPAQUE) e
quindi invisibili anche accese.

La freccia anteriore è una sezione del faro (come sul faro reale): il corner
alto-esterno di `HeadLamp_Glas` viene separato in una mesh dedicata e riceve
`mat_indicators`, quindi si accende insieme alle frecce laterali. Dimensione
regolabile con `INDICATOR_OUTER_FRAC` / `INDICATOR_UPPER_FRAC` in
`scripts/rig_panda_glb.py`.

Stesso discorso dietro: `HeadLamp_Glass_White` è un'unica mesh che copre
entrambe le bande chiare del fanale. Viene tagliata sulla cucitura già presente
nel modello (y locale 3,39): la banda **superiore** (y 92,2…97,3) è la freccia
e prende `mat_indicators`, quella **inferiore** (y 75,9…87,7) è la luce di
retromarcia e resta trasparente, non ancora pilotata.

Le mesh che condividono un materiale hanno lo stesso indice glTF, quindi una
sola scrittura di `emissiveFactor` le accende insieme: vale per `mat_indicators`
(ripetitori + banda posteriore) e per `mat_stoplight` (lente rossa + terzo
stop).

### `mat_indicator_front`: pilotato, non commutato

L'angolo freccia è ritagliato dalla lente del faro, quindi da spento deve
sembrare parte della lente e non un buco. Ha un materiale suo e il suo colore è
**derivato**, non un interruttore a sé:

| Freccia | Faro | `mat_indicator_front` |
| :--- | :--- | :--- |
| accesa | — | ambra (vince sempre) |
| spenta | acceso | stesso colore del faro |
| spenta | spento | nero |

Implementato in `refreshLamps()` sia in `scripts/view_rigged.html` sia in
`VehicleScreen.kt`.

## Limiti noti (richiedono split aggiuntivo del modello)

- **Frecce**: le lampade L+R sono un'unica mesh → si accendono solo insieme.
  OK per 4 frecce, non per indicatore singolo. Fix: split `Wing_LightGlas` in
  `scripts/rig_panda_glb.py` (stessa tecnica delle porte).
- **Maniglie porte posteriori**: `DoorHandle1` non ha la controparte serratura
  (`DoorHandle_Key1` non esiste nel modello sorgente), a differenza delle
  anteriori. Nessun impatto: sul veicolo reale la serratura a chiave è solo
  davanti.
- **Retronebbia** (byte1 `0x02`): nessuna mesh dedicata individuata.
- **Retromarcia**: la banda chiara inferiore dei fanali
  (`HeadLamp_Glass_White_reverse`) è già separata ma non ha un materiale
  pilotato. Serve una voce in `lamp_map` quando il segnale sarà mappato.
- **Luci di posizione**: non hanno un materiale proprio, perché sul modello
  sono la stessa lente rossa dello stop. Per distinguerle basta pilotare
  `mat_stoplight` a due intensità (rosso tenue = posizione, pieno = frenata).

## Plastiche nere solidali alle porte

Erano mesh uniche condivise tra i due lati (e tra porte anteriori e posteriori),
quindi restavano sulla scocca e venivano compenetrate all'apertura. La tabella
`DOOR_TRIM` in `scripts/rig_panda_glb.py` le assegna ai pivot porta con tre
modalità: `split` taglia sulla cucitura già presente nel modello e manda la
sezione anteriore alle porte davanti e quella posteriore alle porte dietro;
`front` e `rear` spostano la parte intera su una sola fila.

| Mesh sorgente | Ruolo | Taglio |
| :--- | :--- | :--- |
| `Door_Plst` | modanatura laterale | cucitura (z locale -16.25) |
| `Frame_Window` | bordo sotto i finestrini | cucitura (z locale -9.85) |
| `Window_Frame3` | cornice finestrini | cucitura (z locale -13.09) |
| `Window_Detail` | deflettore/quarter trim | intera (solo porte anteriori) |
| `Stoiki1` | montanti B e C | intera (solo porte posteriori) |
| `Stoiki1_S` | montanti, lato interno | intera (solo porte posteriori) |

I montanti sono due segmenti staccati (z −42…−25 e z −116…−106) e appartengono
entrambi al telaio finestrino della porta **posteriore**: il primo ne chiude il
bordo anteriore, il secondo quello posteriore. Vanno quindi interi alle porte
posteriori, non divisi tra le due file.

Resta sulla scocca la cornice del parabrezza (`Window_Frame1`), che non fa
parte di nessuna porta.
- **Cofano** (`Hood`): mesh singola separata, animabile in futuro (nessun pivot creato).
