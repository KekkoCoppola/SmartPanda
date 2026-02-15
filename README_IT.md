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
| **LS-CAN L**| 1 | L (CH 1) | `can1` | **50 kbps** | **B-CAN** (Carrozzeria, Luci, Porte) |
| **LS-CAN H**| 9 | H (CH 1) | `can1` | **50 kbps** | **B-CAN** (Carrozzeria, Luci, Porte) |

> **⚠️ Attenzione:** NON alimentare il Raspberry Pi direttamente dal Pin OBD 12V a meno che tu non abbia un HAT verificato con un regolatore di tensione ad ampio ingresso. La maggior parte degli HAT accetta solo 5V. Usa un convertitore Step-Down dedicato!

---

## 🚀 Guida Rapida

### 1. Installazione

Clona la repository e installa le dipendenze:

```bash
git clone https://github.com/tuousername/SmartPanda.git
cd SmartPanda
pip install -r requirements.txt
```

### 2. Configura Interfacce CAN

Abbiamo fornito uno script per attivare automaticamente le interfacce CAN con i bitrate corretti.

```bash
chmod +x setup_can.sh
./setup_can.sh
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
    - [ ] App Mobile / Dashboard Web
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
