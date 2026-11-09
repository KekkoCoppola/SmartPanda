# Animazione "running" — design

Data: 2026-07-25
Stato: approvato

## Obiettivo

Aggiungere al modello `panda_rigged.glb` una animazione che rappresenti l'auto
in marcia: le quattro ruote girano, la marmitta vibra leggermente, e l'intero
veicolo si scuote in modo contenuto. L'animazione deve essere pilotabile sia dal
viewer di sviluppo sia dall'app Android.

## Decisioni

1. **Clip glTF bakeata** nel GLB da `scripts/rig_panda_glb.py`, come le clip
   porte/portellone. L'app Android usa già `animator.applyAnimation(index, t)`,
   quindi non serve logica di animazione per piattaforma.
2. **Niente fumo di scarico.** Scartato: le animazioni glTF non possono pilotare
   i materiali, quindi una nube non può dissolversi in opacità (solo sparire in
   scala) e i quad piatti si leggono male da alcune inquadrature.
3. **Wiring Android incluso** in questo lavoro, non rimandato.

## Modifiche al modello

### Nodi nuovi

| Nodo | Posizione | Ruolo |
| :--- | :--- | :--- |
| `axle_front` | (0, 29.47, 105.56) | pivot rotazione X ruote anteriori |
| `axle_rear` | (0, 29.47, −121.73) | pivot rotazione X ruote posteriori |
| `body_shake` | inserito tra il nodo di scala cm→m e `RootNode` | scuotimento dell'intero veicolo |

Due pivot invece di quattro: le ruote dello stesso asse condividono y e z e
girano nello stesso verso, e la posizione del pivot lungo X non influenza una
rotazione attorno a X. Centri asse e raggio (0.2947 m) sono derivati dai bbox
delle mesh `Rubber*`, non hardcodati.

La marmitta non riceve un pivot: si anima direttamente la translation
dell'holder `Tube`.

### Appartenenza delle ruote

Regola, non lista fissa: gli holder radice il cui nome inizia per `Disc`,
`Rubber`, `BrakeDisk`, `LogoWheel` o `Bolt` finiscono sotto `axle_front` se la
loro translation ha z > 0, sotto `axle_rear` altrimenti. `Support*` (pinza
freno) è escluso esplicitamente: sul veicolo reale non gira. Lo script stampa
l'elenco dei nodi assegnati a ciascun asse, così una mesh non prevista si nota
subito.

### Vincoli glTF da rispettare

- I nodi animati non possono avere `matrix`: gli holder coinvolti vanno
  convertiti a TRS (`matrix = None`, `translation = [...]`), come già fatto per
  il gruppo portellone.
- Le animazioni glTF pilotano solo translation, rotation, scale e morph weights.

## Definizione della clip

Nome `running`, durata 1,0 s, pensata per essere riprodotta in loop.

**Regola di loop-safety:** ogni componente oscillatoria usa frequenze che sono
multipli interi di 1/durata, così il primo e l'ultimo keyframe coincidono e il
loop non ha scatti. I canali oscillatori (`body_shake`, `Tube`) sono campionati
a 120 Hz → 120 keyframe; i canali ruota hanno il proprio set di keyframe, uno
ogni 90° di rotazione.

| Canale | Movimento | Ampiezza |
| :--- | :--- | :--- |
| `axle_front`, `axle_rear` rotation | 4 giri completi per loop, keyframe ogni 90° | — |
| `body_shake` rotation | rollio + beccheggio, somma di armoniche 2/3/5/7/11 Hz | ±0,15° |
| `body_shake` translation | verticale e laterale, stesse armoniche sfasate | ±2,5 mm vert., ±1 mm lat. |
| `Tube` translation | vibrazione motore, armoniche 11/12 Hz | ±1,5 mm |

Le ruote usano keyframe ogni 90° perché un giro completo espresso come singola
coppia di quaternioni degenera con l'interpolazione sferica (0° e 360° sono la
stessa rotazione).

Tutte le ampiezze e il numero di giri sono costanti in cima allo script. Le
ampiezze in tabella sono in unità reali: `body_shake` e `Tube` vivono in spazio
modello (1 unità = 1 cm), quindi ±2,5 mm si scrive come ±0,25 unità.

### Semantica della velocità

4 giri/loop × 1,8517 m di circonferenza = 7,41 m/s ≈ **26,7 km/h apparenti**.
La velocità reale si ottiene scalando il tempo di riproduzione:
`timeScale = v_kmh / 26.7`. Nessun aggancio a un segnale CAN in questa fase: la
velocità non è ancora decodificata.

## Modifiche fuori dal modello

### `scripts/view_rigged.html`

`running` va riprodotta in `LoopRepeat` invece del `LoopOnce` usato dalle clip
porte, e il suo bottone diventa play/stop anziché apri/chiudi.

### `android/app/src/main/java/com/smartpanda/app/ui/VehicleScreen.kt`

Toggle on/off che, quando attivo, fa avanzare la clip nel loop per-frame già
esistente: `animator.applyAnimation(runningIndex, elapsed % duration)`, prima
della `updateBoneMatrices()` che c'è ora. Le clip porte continuano a essere
applicate nello stesso frame senza interferenze, perché agiscono su nodi
disgiunti.

## Verifica

1. `scripts/inspect_glb.py`: la clip `running` esiste e i suoi canali puntano a
   `axle_front`, `axle_rear`, `body_shake` e all'holder `Tube`.
2. Check di loop-safety: per ogni canale il primo e l'ultimo keyframe devono
   coincidere entro tolleranza.
3. Viewer: ruote che girano, pinza freno ferma, scuotimento percepibile ma non
   esagerato, marmitta che vibra.
4. Regressione: le clip `door_FL_open`, `door_FR_open`, `tailgate_open`
   continuano a funzionare, e i materiali luce restano invariati.
5. Android: il progetto non ha il wrapper Gradle in repo (generato da Android
   Studio al primo sync), quindi la compilazione non è verificabile qui. La
   modifica va tenuta minima e rivista a mano.

## Fuori scope

Sterzata delle ruote, escursione sospensioni separata dalla carrozzeria,
densità del movimento legata al regime motore, aggancio a un segnale CAN di
velocità, fumo di scarico.
