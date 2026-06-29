# Umlaut-Korrektor – Bedienungsanleitung

Dieses Programm prüft Code-Dateien (insbesondere `.php`) auf zwei Arten von
Encoding-Problemen und korrigiert sie auf **Windows-1252** als einheitliches
Zielformat:

1. **Charset-Inkonsistenz**: Die Datei ist tatsächlich anders gespeichert, als
   ihr `<meta charset="...">`-Tag behauptet. Das passiert z. B., wenn eine
   Datei in VS Code mit der Encoding-Einstellung "Windows 1252" geöffnet und
   gespeichert wird, der Quelltext aber noch `<meta charset="UTF-8">` enthält
   (oder umgekehrt). Ergebnis: kaputte Umlaute bei jedem Webseiten-Besucher,
   nicht nur im Editor.

2. **Mojibake** (z. B. `ü` wird zu `Ã¼`) – entsteht, wenn UTF-8-Text
   versehentlich falsch interpretiert und erneut gespeichert wird, zum
   Beispiel beim Kopieren von KI-generiertem Code.

Bei einer erkannten Inkonsistenz werden **Datei-Kodierung und `<meta charset>`-Tag
gemeinsam auf Windows-1252 vereinheitlicht** – passend zur bevorzugten
Arbeitsweise mit VS Code auf "Windows 1252".

---

## 1. Installation

Voraussetzung: Python 3.8 oder neuer (mit tkinter, das bei der offiziellen
Windows-Installation von python.org standardmäßig dabei ist).

Im Ordner mit den Programmdateien folgendes in der Kommandozeile (cmd/PowerShell) ausführen:

```
pip install -r requirements.txt
```

Das installiert die einzige benötigte Bibliothek: `ftfy`.

---

## 2. Programm starten

```
python umlaut_korrektor.py
```

Es öffnet sich ein Fenster im dunklen Design.

---

## 3. Bedienung

1. **"Datei auswählen ..."** klicken und die betroffene Datei wählen
   (`.php` steht an erster Stelle, da das das Hauptformat für die Webseite ist;
   auch `.html`, `.py`, `.js`, `.css` und weitere werden unterstützt).

2. Das Programm liest die Datei automatisch ein und prüft sie. Mögliche Ergebnisse:
   - ✅ **Konsistent** – Datei-Kodierung und `<meta charset>`-Tag passen zusammen,
     keine Mojibake-Stellen gefunden. Nichts wird verändert.
   - ⚠️ **Charset-Inkonsistenz** – Datei-Kodierung und Tag widersprechen sich.
     Die Vorschau zeigt, welches Encoding tatsächlich vorliegt und was das Tag
     behauptet, plus Beispielstellen mit Umlauten.
   - ⚠️ **Mojibake gefunden** – einzelne Stellen wurden vorher falsch kodiert
     (z. B. durch Copy-Paste). Die Vorschau zeigt jede Fundstelle einzeln
     (rot = Fehler, grün = Korrektur).

3. Speicherentscheidung treffen:
   - **"💾 Original überschreiben"** – ersetzt die Datei direkt.
     Es wird automatisch eine Sicherungskopie mit der Endung `.bak` im selben
     Ordner angelegt (z. B. `seite.php.bak`).
   - **"📄 Als neue Datei speichern (_korrigiert)"** – lässt das Original
     unangetastet und erzeugt eine neue Datei (Vorschlag: `seite_korrigiert.php`).

---

## 4. Wichtige Hinweise

- Bei einer Charset-Inkonsistenz wird **immer auf Windows-1252** vereinheitlicht
  (sowohl die Datei-Kodierung als auch der `<meta charset>`-Tag im Code).
- Bei reinem Mojibake (Tag und Datei-Kodierung sind bereits konsistent, z. B.
  beide UTF-8) bleibt das ursprüngliche Encoding erhalten – nur die kaputten
  Stellen werden repariert. Das Tool zwingt also nicht generell UTF-8 oder
  Windows-1252 auf, sondern stellt nur die Konsistenz zwischen Datei und Tag her.
- Das Programm verändert **nur** die Stellen, die wirklich als fehlerhaft
  erkannt wurden.

---

## 5. Warum Konsistenz und nicht ein festes Format?

Ein `<meta charset>`-Tag ist eine Ansage an jeden Browser, wie er die folgenden
Bytes interpretieren soll. Damit Umlaute bei jedem Besucher korrekt erscheinen,
müssen Tag und tatsächliche Datei-Kodierung übereinstimmen – unabhängig davon,
ob das gewählte Format UTF-8 oder Windows-1252 ist. Beide Formate funktionieren
einwandfrei im Web, solange sie konsistent verwendet werden. Dieses Tool stellt
diese Konsistenz her und vereinheitlicht im Konfliktfall auf Windows-1252.
