# 🐼 Progetto SmartPanda

> **Trasformare una Fiat Panda (169) del 2010 in una Smart Car completamente connessa.**

![Stato Progetto](https://img.shields.io/badge/Stato-In%20Sviluppo-yellow?style=for-the-badge)
![Hardware](https://img.shields.io/badge/Hardware-Raspberry%20Pi_4_%7C_Waveshare_CAN-red?style=for-the-badge&logo=raspberrypi)
![Protocollo](https://img.shields.io/badge/Protocollo-CAN%20Bus%20(ISO%2011898)-blue?style=for-the-badge)
![Linguaggio](https://img.shields.io/badge/Linguaggio-Python%203-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Licenza](https://img.shields.io/badge/Licenza-MIT-green?style=for-the-badge)

## 📖 Informazioni sul Progetto

**SmartPanda** è un'iniziativa open-source per eseguire il reverse engineering e modernizzare la piattaforma Fiat Panda 169. Interfacciandosi direttamente con le reti CAN Bus del veicolo (B-CAN e C-CAN), questo progetto mira ad abilitare il controllo remoto tramite app mobile, telemetria in tempo reale e automazione intelligente.

**Veicolo Target:** Fiat Panda (Modello 169) - Anno 2010

<div align="center">
  <br />
  <img src="assets/img/target_vehicle.png" alt="Veicolo Target" width="300" />
  <br /><br />
</div>

---

## 📂 Struttura della Repository

La repo è un monorepo che ospita entrambi i lati del progetto:

```
SmartPanda/
├── raspberry/          # Tutto ciò che gira sul Raspberry Pi
│   ├── setup_can.sh    #   attivazione interfacce CAN (can0/can1)
│   ├── requirements.txt
│   └── tools/          #   script di sniffing e decodifica live
├── android/            # App Android companion (Kotlin + Jetpack Compose)
├── dbc/                # Definizioni messaggi CAN condivise (file DBC)
├── docs/               # Documentazione condivisa (mappe ID)
└── assets/             # Immagini e loghi
```

`dbc/` e `docs/` stanno alla radice perché descrivono il protocollo dell'auto — conoscenza condivisa tra il middleware sul Pi e l'app.

---

## ⚡ Hardware e Requisiti

### Componenti Hardware
*   **Core:** Raspberry Pi 3B+ / 4 (Con Raspberry Pi OS Lite)
*   **Interfaccia:** Waveshare 2-CH CAN HAT (basato su MCP2515) / CAN Bed
*   **Connessione:** Cavo da OBD-II a DB9 / Cablaggio personalizzato
*   **Alimentazione:** Convertitore Step-Down da 12V a 5V (consigliato minimo 3A)

### Prerequisiti Software
*   Raspberry Pi OS (Lite consigliato)
*   Python 3.7+
*   `can-utils` (per debugging a basso livello)

---

## 🔌 Schema di Cablaggio (da OBD-II a Waveshare HAT)

Ci colleghiamo a entrambe le reti **C-CAN** (Alta Velocità / Motore) e **B-CAN** (Bassa Velocità / Carrozzeria).

| Segnale | Pin Fiat OBD | Terminale Waveshare HAT | ID Rete | Velocità | Descrizione |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **VCC** | 16 | 12V | - | - | Fonte di Alimentazione (Sempre Attiva) |
| **GND** | 4 & 5 | GND | - | - | Massa Segnale e Telaio |
| **CAN H** | 6 | H (CH 0) | `can0` | **500 kbps** | **C-CAN** (Motore, ABS, City) |
| **CAN L** | 14 | L (CH 0) | `can0` | **500 kbps** | **C-CAN** (Motore, ABS, City) |
| **LS-CAN L**| 1 | L (CH 1) | `can1` | **50 kbps** | **B-CAN** (Carrozzeria, Luci, Porte) — ⚠️ vedi avvertenza sotto |
| **LS-CAN H**| 9 | H (CH 1) | `can1` | **50 kbps** | **B-CAN** (Carrozzeria, Luci, Porte) — ⚠️ vedi avvertenza sotto |

> **⚠️ Attenzione:** NON alimentare il Raspberry Pi direttamente dal Pin OBD 12V a meno che tu non abbia un HAT verificato con un regolatore di tensione ad ampio ingresso. La maggior parte degli HAT accetta solo 5V. Usa un convertitore Step-Down dedicato!

> **🔴 Incompatibilità transceiver B-CAN:** Il Waveshare 2-CH CAN HAT monta transceiver **SN65HVD230**, che implementano il livello fisico **high-speed ISO 11898-2**. La B-CAN Fiat è invece una rete **low-speed fault-tolerant ISO 11898-3**, con livelli di tensione diversi (incompatibili) e terminazione per-nodo. In pratica, il CH 1 collegato ai pin OBD 1/9 con ogni probabilità non leggerà nulla (o solo spazzatura/error frame), e la terminazione differenziale da 120 Ω dell'HAT può disturbare la B-CAN dell'auto anche in listen-only (porte bloccate, spie accese, ecc.).
> **Non collegare i pin OBD 1/9 a questo HAT.** Per leggere la B-CAN serve un transceiver fault-tolerant (es. NXP TJA1054/TJA1055) tra il bus e il MCP2515. In alternativa, parti solo dalla C-CAN: il Body Computer fa da gateway e replica molti eventi carrozzeria (porte, luci) sulla C-CAN.

---

## 🚀 Guida Rapida

### 1. Installazione

Clona la repository e installa le dipendenze:

```bash
git clone https://github.com/tuousername/SmartPanda.git
cd SmartPanda
pip install -r raspberry/requirements.txt
```

### 2. Configura Interfacce CAN

Abbiamo fornito uno script per attivare automaticamente le interfacce CAN con i bitrate corretti.

```bash
chmod +x raspberry/setup_can.sh
./raspberry/setup_can.sh
```

*Questo imposta `can0` a 500kbps (C-CAN) e `can1` a 50kbps (B-CAN).*

### 3. Verifica Connessione

Controlla se le interfacce sono attive e funzionanti:

```bash
ifconfig can0
ifconfig can1
```

---

## 🕵️ Reverse Engineering (Sniffing)

Per identificare pacchetti specifici (es. Porta Aperta, Luci Accese), usa `candump` e `cansniffer` dal pacchetto `can-utils`.

**Esempio: Monitorare traffico Body Computer (rimuovendo ID statici)**
```bash
cansniffer -c can1
```

*Nota: `can1` (B-CAN) funziona solo con un transceiver fault-tolerant (vedi avvertenza sopra). Nel frattempo sniffa `can0` (C-CAN) — molti eventi carrozzeria passano anche da lì tramite il gateway.*

Interagisci con l'auto (apri un finestrino, accendi le luci) e osserva i valori esadecimali cambiare!

---

## 🗺️ Roadmap

- [x] **Fase 0: setup**
    - [x] Interfaccia Hardware e Cablaggio
    - [x] Configurazione OS e Rete Attiva (`setup_can.sh`)
- [ ] **Fase 1: Decodifica**
    - [ ] Mappa ID B-CAN (Porte, Luci, Finestrini)
    - [ ] Mappa ID C-CAN (Giri Motore, Velocità, Temp Motore)
- [ ] **Fase 2: Middleware**
    - [ ] Servizio Python per parsing messaggi
    - [ ] Integrazione Database (InfluxDB/SQLite)
- [ ] **Fase 3: Interfaccia Utente**
    - [x] Scaffold app Android (`android/`, Kotlin + Jetpack Compose)
    - [ ] Funzionalità App Mobile / Dashboard Web
- [ ] **Fase 4: Controllo Attivo**
    - [ ] Iniezione messaggi per controllare finestrini/luci

---

## 🤝 Contribuire

I contributi sono ciò che rende la comunità open source un luogo straordinario per imparare, ispirare e creare. Qualsiasi contributo tu faccia è molto apprezzato.

Per favore verifica le tue modifiche su un banco di prova se possibile prima di inviare.

---

## ⚖️ Disclaimer

**USA A TUO RISCHIO E PERICOLO.**

Modificare l'elettronica dell'auto può essere pericoloso. Gli autori non sono responsabili per eventuali danni al tuo veicolo, garanzie invalidate o incidenti.
*   **Testa sempre a motore spento e auto ferma.**
*   **Non inviare messaggi attivi alla C-CAN (Motore/ABS) durante la guida.**
