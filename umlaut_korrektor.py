# -*- coding: utf-8 -*-
"""
Umlaut-Korrektor / Encoding-Konsistenz-Prüfer
==============================================
Findet Encoding-Probleme in Code-Dateien und stellt Konsistenz zwischen der
tatsächlichen Datei-Kodierung und dem deklarierten <meta charset> her.

Zielformat ist Windows-1252 (cp1252) - passend zur bevorzugten Arbeitsweise
mit deutschen Umlauten. Das Tool erkennt zwei Fehlerarten:

1. Mojibake: UTF-8-Text wurde fälschlich re-interpretiert/re-encodiert
   (z. B. "Ã¼" statt "ü"). Wird per ftfy erkannt und korrigiert.
2. Charset-Inkonsistenz: Die Datei ist in einem anderen Encoding gespeichert,
   als ihr <meta charset>-Tag behauptet (z. B. Datei ist UTF-8, Tag sagt
   windows-1252, oder umgekehrt). Wird erkannt und auf Windows-1252
   (Datei + Tag) vereinheitlicht.
3. HTML-Entities für Umlaute/&/ß (z. B. "&amp;" statt "&", "&ouml;" statt "ö")
   werden in die rohen Zeichen zurückgewandelt, passend zum bevorzugten
   Schreibstil. Strukturell wichtige Entities wie &lt; &gt; &quot; werden
   bewusst NICHT verändert, da sie oft absichtlich escaped sind.

Autor: Erstellt mit Claude | © Robby Tonn Services 2026
"""

import os
import sys
import re
import shutil
import difflib
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import ftfy

# ----------------------------------------------------------------------------
# Konfiguration / Farbschema (dunkles Theme)
# ----------------------------------------------------------------------------
BG_COLOR = "#1e1e1e"
FG_COLOR = "#e0e0e0"
ACCENT_COLOR = "#4ea8de"
ACCENT_HOVER = "#3d8bc0"
SUCCESS_COLOR = "#4caf50"
WARN_COLOR = "#e0a030"
ERROR_COLOR = "#e05050"
PANEL_COLOR = "#2a2a2a"
ENTRY_BG = "#252525"
FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 9)
FONT_HEADER = ("Segoe UI", 13, "bold")

# Sichere Teilmenge von HTML-Entities, die in rohe Zeichen zurückgewandelt werden.
# Bewusst NICHT enthalten: &lt; &gt; &quot; &apos; &nbsp; - diese sind oft
# absichtlich escaped (z. B. um echten HTML-Code als Text anzuzeigen) und
# eine blinde Rückwandlung könnte Anzeige- oder sogar Sicherheitsprobleme
# verursachen (z. B. &lt;script&gt; -> <script>).
SAFE_ENTITIES = {
    "&amp;": "&",
    "&auml;": "ä", "&ouml;": "ö", "&uuml;": "ü",
    "&Auml;": "Ä", "&Ouml;": "Ö", "&Uuml;": "Ü",
    "&szlig;": "ß",
}


def unescape_safe_entities(text):
    """Wandelt nur die in SAFE_ENTITIES gelisteten Entities zurück in rohe Zeichen."""
    for entity, char in SAFE_ENTITIES.items():
        text = text.replace(entity, char)
    return text

# Unterstützte Code-Dateitypen (.php an erster Stelle, da serverseitige
# PHP-Dateien mit HTML-Inhalt der Hauptanwendungsfall sind)
SUPPORTED_EXTENSIONS = [
    (".php", "*.php"),
    (".html / .htm", "*.html;*.htm"),
    (".py", "*.py"),
    (".js", "*.js"),
    (".css", "*.css"),
    (".json", "*.json"),
    (".xml", "*.xml"),
    (".java", "*.java"),
    (".cs", "*.cs"),
    (".cpp / .c / .h", "*.cpp;*.c;*.h"),
    (".md", "*.md"),
    (".txt", "*.txt"),
    ("Alle unterstützten Typen", "*.php;*.html;*.htm;*.py;*.js;*.css;*.json;*.xml;*.java;*.cs;*.cpp;*.c;*.h;*.md;*.txt"),
]


class MojibakeFixerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Umlaut-Korrektor – Encoding-Fehler beheben")
        self.root.geometry("880x680")
        self.root.configure(bg=BG_COLOR)
        self.root.minsize(700, 550)

        self.current_filepath = None
        self.original_text = None
        self.fixed_text = None
        self.diff_count = 0
        self._pending_encoding_fix = False
        self._actual_encoding_for_save = "utf-8"

        self._build_ui()

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Kopfbereich
        header_frame = tk.Frame(self.root, bg=BG_COLOR)
        header_frame.pack(fill="x", padx=20, pady=(18, 10))

        tk.Label(
            header_frame, text="🔧 Umlaut-Korrektor",
            font=FONT_HEADER, bg=BG_COLOR, fg=FG_COLOR
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="Findet und korrigiert kaputte Umlaute (Mojibake) in Code-Dateien.",
            font=FONT_NORMAL, bg=BG_COLOR, fg="#a0a0a0"
        ).pack(anchor="w", pady=(2, 0))

        # Dateiauswahl-Bereich
        file_frame = tk.Frame(self.root, bg=PANEL_COLOR)
        file_frame.pack(fill="x", padx=20, pady=10)

        inner_file = tk.Frame(file_frame, bg=PANEL_COLOR)
        inner_file.pack(fill="x", padx=15, pady=15)

        self.btn_select = tk.Button(
            inner_file, text="📂 Datei auswählen ...",
            font=FONT_BOLD, bg=ACCENT_COLOR, fg="white",
            activebackground=ACCENT_HOVER, relief="flat",
            cursor="hand2", padx=14, pady=8,
            command=self.select_file
        )
        self.btn_select.pack(side="left")

        self.lbl_filepath = tk.Label(
            inner_file, text="Keine Datei ausgewählt",
            font=FONT_NORMAL, bg=PANEL_COLOR, fg="#a0a0a0",
            anchor="w"
        )
        self.lbl_filepath.pack(side="left", padx=15, fill="x", expand=True)

        # Analyse-Status
        self.lbl_status = tk.Label(
            self.root, text="Bereit. Wähle eine Datei aus, um zu starten.",
            font=FONT_NORMAL, bg=BG_COLOR, fg="#a0a0a0",
            anchor="w"
        )
        self.lbl_status.pack(fill="x", padx=20, pady=(0, 8))

        # Diff-Vorschau (gefundene Fehlerstellen)
        preview_label_frame = tk.Frame(self.root, bg=BG_COLOR)
        preview_label_frame.pack(fill="x", padx=20)
        tk.Label(
            preview_label_frame, text="Gefundene Korrekturen:",
            font=FONT_BOLD, bg=BG_COLOR, fg=FG_COLOR
        ).pack(anchor="w")

        self.txt_preview = scrolledtext.ScrolledText(
            self.root, font=FONT_MONO, bg=ENTRY_BG, fg=FG_COLOR,
            insertbackground=FG_COLOR, relief="flat", height=18,
            wrap="word", padx=10, pady=10, borderwidth=0
        )
        self.txt_preview.pack(fill="both", expand=True, padx=20, pady=(5, 10))
        self.txt_preview.configure(state="disabled")

        # Farb-Tags für die Diff-Anzeige
        self.txt_preview.tag_configure("removed", foreground=ERROR_COLOR, font=FONT_MONO)
        self.txt_preview.tag_configure("added", foreground=SUCCESS_COLOR, font=FONT_MONO)
        self.txt_preview.tag_configure("header", foreground=ACCENT_COLOR, font=("Consolas", 9, "bold"))
        self.txt_preview.tag_configure("info", foreground="#a0a0a0", font=FONT_MONO)

        # Aktionen-Bereich (unten)
        action_frame = tk.Frame(self.root, bg=BG_COLOR)
        action_frame.pack(fill="x", padx=20, pady=(0, 18))

        self.btn_overwrite = tk.Button(
            action_frame, text="💾 Original überschreiben",
            font=FONT_BOLD, bg=WARN_COLOR, fg="white",
            activebackground="#c08820", relief="flat",
            cursor="hand2", padx=14, pady=10,
            state="disabled", command=self.save_overwrite
        )
        self.btn_overwrite.pack(side="left", padx=(0, 10))

        self.btn_save_new = tk.Button(
            action_frame, text="📄 Als neue Datei speichern (_korrigiert)",
            font=FONT_BOLD, bg=SUCCESS_COLOR, fg="white",
            activebackground="#3d8b40", relief="flat",
            cursor="hand2", padx=14, pady=10,
            state="disabled", command=self.save_new_file
        )
        self.btn_save_new.pack(side="left")

        self.lbl_backup_hint = tk.Label(
            action_frame,
            text="ℹ️ Beim Überschreiben wird automatisch ein Backup (.bak) erstellt.",
            font=("Segoe UI", 8), bg=BG_COLOR, fg="#808080"
        )
        self.lbl_backup_hint.pack(side="right")

    # ------------------------------------------------------------------
    # Logik: Datei auswählen & analysieren
    # ------------------------------------------------------------------
    def select_file(self):
        filetypes = SUPPORTED_EXTENSIONS + [("Alle Dateien", "*.*")]
        filepath = filedialog.askopenfilename(
            title="Code-Datei auswählen",
            filetypes=filetypes
        )
        if not filepath:
            return

        self.current_filepath = filepath
        self.lbl_filepath.config(text=filepath, fg=FG_COLOR)
        self.analyze_file(filepath)

    def analyze_file(self, filepath):
        raw_bytes = None
        try:
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
        except Exception as e:
            messagebox.showerror("Fehler beim Lesen", f"Datei konnte nicht gelesen werden:\n{e}")
            return

        # Schritt 1: Datei robust einlesen, um überhaupt einen Text zur Analyse zu haben.
        text, actual_encoding = self._decode_bytes(raw_bytes)
        if text is None:
            messagebox.showerror(
                "Encoding nicht erkannt",
                "Die Datei konnte mit keinem der bekannten Encodings (UTF-8, Windows-1252) "
                "gelesen werden. Bitte prüfe die Datei manuell."
            )
            return

        # Schritt 2: deklariertes <meta charset> aus dem Text auslesen, falls vorhanden.
        declared_charset = self._extract_declared_charset(text)

        # Schritt 3: prüfen, ob tatsächliches Datei-Encoding und deklariertes
        # Charset zusammenpassen. Das ist der eigentliche Fehlerfall, unabhängig
        # davon, ob UTF-8 oder Windows-1252 im Spiel ist.
        mismatch = self._check_charset_mismatch(raw_bytes, actual_encoding, declared_charset)

        if mismatch is not None:
            self.original_text = text
            self.fixed_text = unescape_safe_entities(mismatch["fixed_text"])
            self.diff_count = 0
            self._pending_encoding_fix = True
            self._render_charset_mismatch(mismatch)
            self.lbl_status.config(text=mismatch["status_text"], fg=ERROR_COLOR)
            self.btn_overwrite.config(state="normal")
            self.btn_save_new.config(state="normal")
            return

        self._pending_encoding_fix = False
        self._actual_encoding_for_save = "cp1252" if actual_encoding == "Windows-1252" else "utf-8"

        # Schritt 4: kein Charset-Konflikt -> trotzdem auf klassisches Mojibake
        # prüfen (UTF-8-Text, der vorher schon mal falsch re-encodiert wurde)
        # und sichere HTML-Entities (&amp;, &ouml; usw.) zurückwandeln.
        # uncurl_quotes=False verhindert, dass ftfy deutsche typografische
        # Anführungszeichen („ und ") fälschlich zu geraden Anführungszeichen
        # (") normalisiert - diese sind im Deutschen korrekt und kein Fehler.
        self.original_text = text
        self.fixed_text = unescape_safe_entities(ftfy.fix_text(text, uncurl_quotes=False))
        self._render_diff()

        if self.diff_count == 0:
            self.lbl_status.config(
                text=f"✅ Datei ist konsistent: gespeichert als {actual_encoding}"
                     + (f", deklariert als '{declared_charset}'" if declared_charset else ", kein charset-Tag gefunden")
                     + ". Keine Fehler gefunden.",
                fg=SUCCESS_COLOR
            )
            self.btn_overwrite.config(state="disabled")
            self.btn_save_new.config(state="disabled")
        else:
            self.lbl_status.config(
                text=f"⚠️ {self.diff_count} Korrektur(en) gefunden (gelesen als {actual_encoding}). "
                     f"Prüfe die Vorschau unten und wähle eine Speicheroption.",
                fg=WARN_COLOR
            )
            self.btn_overwrite.config(state="normal")
            self.btn_save_new.config(state="normal")

    @staticmethod
    def _decode_bytes(raw_bytes):
        """
        Versucht, die Bytes sinnvoll zu dekodieren, um den Text inhaltlich lesen
        zu können. Gibt (text, encoding_name) zurück. encoding_name beschreibt,
        wie die Datei TATSÄCHLICH auf der Festplatte kodiert ist.
        """
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            try:
                return raw_bytes.decode("utf-8-sig"), "UTF-8 (BOM)"
            except UnicodeDecodeError:
                pass
        try:
            return raw_bytes.decode("utf-8"), "UTF-8"
        except UnicodeDecodeError:
            pass
        try:
            return raw_bytes.decode("cp1252"), "Windows-1252"
        except UnicodeDecodeError:
            return None, None

    @staticmethod
    def _extract_declared_charset(text):
        """Liest das deklarierte Charset aus <meta charset="..."> bzw. dem
        älteren <meta http-equiv="Content-Type" content="text/html; charset=...">
        Format aus. Gibt den normalisierten Namen zurück (z. B. 'utf-8',
        'windows-1252') oder None, falls keine Deklaration gefunden wurde."""
        m = re.search(r'<meta\s+charset=["\']?([\w-]+)', text, re.IGNORECASE)
        if not m:
            m = re.search(r'charset=["\']?([\w-]+)', text, re.IGNORECASE)
        if not m:
            return None
        return m.group(1).strip().lower().rstrip('"\'>')

    @staticmethod
    def _normalize_charset_name(name):
        """Normalisiert verschiedene Schreibweisen auf 'utf-8' oder 'windows-1252'."""
        if name is None:
            return None
        n = name.lower().replace("_", "-")
        if n in ("utf-8", "utf8"):
            return "utf-8"
        if n in ("windows-1252", "win-1252", "cp1252", "windows1252"):
            return "windows-1252"
        return n

    def _check_charset_mismatch(self, raw_bytes, actual_encoding, declared_charset):
        """
        Prüft, ob die tatsächliche Datei-Kodierung zum deklarierten <meta charset>
        passt. Vereinheitlicht im Fehlerfall auf Windows-1252 (das Zielformat),
        unabhängig davon, in welche Richtung der Konflikt zeigt.

        Gibt None zurück, wenn alles konsistent ist, sonst ein dict mit
        Details für Anzeige und Korrektur.
        """
        actual_norm = self._normalize_charset_name(actual_encoding.replace(" (BOM)", ""))
        declared_norm = self._normalize_charset_name(declared_charset)

        if declared_norm is None:
            # Kein Tag gefunden -> kein Vergleich möglich, kein Fehlerfall hier.
            return None

        if actual_norm == declared_norm:
            return None  # alles konsistent

        # Inkonsistenz gefunden. Ziel: einheitlich Windows-1252 (Datei + Tag).
        if actual_norm == "windows-1252":
            # Datei ist bereits Windows-1252 -> Text direkt damit decodieren.
            text_cp1252 = raw_bytes.decode("cp1252")
        else:
            # Datei ist UTF-8 -> nach cp1252 "umdenken": Text bleibt inhaltlich
            # gleich, wird aber im Anschluss als cp1252 gespeichert werden.
            text_cp1252 = raw_bytes.decode("utf-8-sig" if raw_bytes.startswith(b"\xef\xbb\xbf") else "utf-8")

        # Tag im Text auf windows-1252 umschreiben
        fixed_text = re.sub(
            r'(<meta\s+charset=["\']?)([\w-]+)',
            r'\1windows-1252',
            text_cp1252,
            flags=re.IGNORECASE
        )
        fixed_text = re.sub(
            r'(charset=["\']?)(utf-8|utf8)',
            r'\1windows-1252',
            fixed_text,
            flags=re.IGNORECASE
        )

        return {
            "actual": actual_norm,
            "declared": declared_norm,
            "fixed_text": fixed_text,
            "status_text": (
                f"⚠️ Inkonsistenz gefunden: Datei ist als {actual_encoding} gespeichert, "
                f"aber <meta charset> sagt '{declared_charset}'. Wird auf Windows-1252 "
                f"(Datei + Tag) vereinheitlicht."
            ),
        }

    # ------------------------------------------------------------------
    # Diff-Anzeige
    # ------------------------------------------------------------------
    def _render_diff(self):
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")

        sm = difflib.SequenceMatcher(None, self.original_text, self.fixed_text)
        opcodes = [op for op in sm.get_opcodes() if op[0] != "equal"]
        self.diff_count = len(opcodes)

        if not opcodes:
            self.txt_preview.insert("end", "Keine Unterschiede gefunden – die Datei ist bereits korrekt.\n", "info")
            self.txt_preview.configure(state="disabled")
            return

        self.txt_preview.insert("end", f"{len(opcodes)} Stelle(n) mit Fehlern gefunden:\n\n", "header")

        for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes, 1):
            # Kontext um die Fehlerstelle herum anzeigen (max. 20 Zeichen davor/danach)
            ctx_start = max(0, i1 - 20)
            ctx_end = min(len(self.original_text), i2 + 20)

            before_ctx = self.original_text[ctx_start:i1]
            after_ctx = self.original_text[i2:ctx_end]
            old_part = self.original_text[i1:i2]
            new_part = self.fixed_text[j1:j2]

            self.txt_preview.insert("end", f"#{idx}  ", "header")
            self.txt_preview.insert("end", "…" + before_ctx, "info")
            self.txt_preview.insert("end", old_part if old_part else "∅", "removed")
            self.txt_preview.insert("end", " → ", "info")
            self.txt_preview.insert("end", new_part if new_part else "∅", "added")
            self.txt_preview.insert("end", after_ctx + "…\n", "info")

        self.txt_preview.configure(state="disabled")

    def _render_charset_mismatch(self, mismatch):
        """Zeigt an, dass Datei-Encoding und deklariertes <meta charset> nicht zusammenpassen."""
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", "end")

        self.txt_preview.insert(
            "end",
            "⚠️ Charset-Inkonsistenz gefunden!\n\n",
            "header"
        )
        self.txt_preview.insert(
            "end",
            f"Die Datei ist tatsächlich gespeichert als: {mismatch['actual']}\n"
            f"Das <meta charset>-Tag deklariert aber:      {mismatch['declared']}\n\n"
            "Das ist ein Problem, weil der Browser sich beim Anzeigen nach dem\n"
            "deklarierten Tag richtet, aber die tatsächlichen Bytes anders kodiert sind.\n"
            "Ergebnis: kaputte Umlaute bei jedem Besucher, nicht nur im Editor.\n\n"
            "Diese Datei wird auf Windows-1252 vereinheitlicht (Datei-Kodierung UND\n"
            "<meta charset>-Tag), passend zu deiner bevorzugten Arbeitsweise:\n\n",
            "info"
        )

        # Zeige ein paar Beispielstellen mit deutschen Umlauten zum Gegenchecken.
        # self.fixed_text enthält bereits die finale Version (Encoding-Fix + Entity-Rückwandlung).
        text = self.fixed_text
        german_chars = set("äöüÄÖÜß&")
        positions = [i for i, c in enumerate(text) if c in german_chars]
        shown = 0
        for i in positions:
            if shown >= 8:
                self.txt_preview.insert("end", f"  … und {len(positions) - shown} weitere Stelle(n)\n", "info")
                break
            ctx_start = max(0, i - 20)
            ctx_end = min(len(text), i + 20)
            self.txt_preview.insert("end", "  …" + text[ctx_start:ctx_end] + "…\n", "added")
            shown += 1

        if "&amp;" in mismatch["fixed_text"] or any(e in mismatch["fixed_text"] for e in SAFE_ENTITIES):
            self.txt_preview.insert(
                "end",
                "\nHinweis: Zusätzlich wurden HTML-Entities wie &amp; in rohe Zeichen\n"
                "zurückgewandelt (&amp; → &, &ouml; → ö, usw.).\n",
                "info"
            )


        self.txt_preview.insert(
            "end",
            "\nKlicke unten auf eine Speicheroption, um Datei und Tag konsistent\n"
            "als Windows-1252 zu speichern.\n",
            "info"
        )

        self.txt_preview.configure(state="disabled")

    # ------------------------------------------------------------------
    # Speichern
    # ------------------------------------------------------------------
    def save_overwrite(self):
        if not self.current_filepath or self.fixed_text is None:
            return
        if self.diff_count == 0 and not self._pending_encoding_fix:
            return

        target_encoding = "cp1252" if self._pending_encoding_fix else self._actual_encoding_for_save
        target_label = "Windows-1252" if self._pending_encoding_fix else target_encoding

        if self._pending_encoding_fix:
            dialog_text = (
                f"Die Datei wird überschrieben:\n{self.current_filepath}\n\n"
                "Datei-Kodierung und <meta charset>-Tag werden konsistent auf "
                "Windows-1252 gesetzt. Der Textinhalt bleibt gleich.\n\n"
                "Ein Backup mit der Endung '.bak' wird automatisch erstellt.\n\n"
                "Fortfahren?"
            )
        else:
            dialog_text = (
                f"Die Datei wird überschrieben:\n{self.current_filepath}\n\n"
                "Ein Backup mit der Endung '.bak' wird automatisch erstellt.\n\n"
                "Fortfahren?"
            )

        confirm = messagebox.askyesno("Original überschreiben?", dialog_text)
        if not confirm:
            return

        try:
            backup_path = self.current_filepath + ".bak"
            shutil.copy2(self.current_filepath, backup_path)

            with open(self.current_filepath, "w", encoding=target_encoding, newline="") as f:
                f.write(self.fixed_text)

            self.lbl_status.config(
                text=f"✅ Datei korrigiert und als {target_label} gespeichert. Backup unter: {os.path.basename(backup_path)}",
                fg=SUCCESS_COLOR
            )
            self.btn_overwrite.config(state="disabled")
            self.btn_save_new.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Fehler beim Speichern", f"Datei konnte nicht gespeichert werden:\n{e}")

    def save_new_file(self):
        if not self.current_filepath or self.fixed_text is None:
            return
        if self.diff_count == 0 and not self._pending_encoding_fix:
            return

        target_encoding = "cp1252" if self._pending_encoding_fix else self._actual_encoding_for_save
        target_label = "Windows-1252" if self._pending_encoding_fix else target_encoding

        base, ext = os.path.splitext(self.current_filepath)
        suggested_name = f"{base}_korrigiert{ext}"

        save_path = filedialog.asksaveasfilename(
            title="Korrigierte Datei speichern als ...",
            initialfile=os.path.basename(suggested_name),
            initialdir=os.path.dirname(self.current_filepath),
            defaultextension=ext,
            filetypes=[("Gleicher Typ", f"*{ext}"), ("Alle Dateien", "*.*")]
        )
        if not save_path:
            return

        try:
            with open(save_path, "w", encoding=target_encoding, newline="") as f:
                f.write(self.fixed_text)

            self.lbl_status.config(
                text=f"✅ Korrigierte Datei als {target_label} gespeichert unter: {os.path.basename(save_path)}",
                fg=SUCCESS_COLOR
            )
        except Exception as e:
            messagebox.showerror("Fehler beim Speichern", f"Datei konnte nicht gespeichert werden:\n{e}")


def main():
    root = tk.Tk()
    app = MojibakeFixerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
